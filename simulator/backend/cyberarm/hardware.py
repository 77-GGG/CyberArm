"""ESP32-S3 hardware transport for mirroring validated CyberArm motion.

The transport is deliberately optional: the simulator starts normally when
pyserial is absent or no controller is attached.  Every request is a bounded,
newline-delimited JSON message with a correlation id.  Connecting never
enables PWM; calibration and an explicit arm command are separate operations.
"""
from __future__ import annotations

import asyncio
import json
import math
import threading
import time
from typing import Any, Callable


PROTOCOL_VERSION = 1
DEFAULT_BAUD = 921_600
MAX_SEGMENTS = 512


class HardwareError(RuntimeError):
    """A controller connection or protocol operation failed."""


class HardwareRejected(HardwareError):
    """The link is healthy but the firmware rejected this command."""


class HardwareTimeout(HardwareError):
    """A request timed out without proving that the serial link is gone."""


def _serial_modules():
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        raise HardwareError('未安装串口组件 pyserial；请重新安装上位机或运行 pip install pyserial') from exc
    return serial, list_ports


class HardwareBridge:
    def __init__(self, model_id: str, limits_deg: list[list[float]], *,
                 serial_factory: Callable[..., Any] | None = None,
                 port_lister: Callable[[], list[Any]] | None = None):
        self.model_id = model_id
        self.limits_deg = limits_deg
        self._serial_factory = serial_factory
        self._port_lister = port_lister
        self._serial = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._state: dict[str, Any] = self._empty_state()

    def _empty_state(self) -> dict[str, Any]:
        return {
            'available': True,
            'connected': False,
            'armed': False,
            'mode': 'DISCONNECTED',
            'port': None,
            'baud': None,
            'protocol_version': PROTOCOL_VERSION,
            'firmware_version': None,
            'model_id': self.model_id,
            'driver_ready': False,
            'outputs_enabled': False,
            'calibrated': [False] * 6,
            'calibration': [None] * 6,
            'commanded_q_deg': None,
            'measured_q_deg': None,
            'measured_feedback': False,
            'last_seen': None,
            'error': '',
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            # JSON round-trip gives callers a detached copy of nested lists.
            return json.loads(json.dumps(self._state))

    async def list_ports(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_ports_sync)

    def _list_ports_sync(self) -> list[dict[str, Any]]:
        try:
            if self._port_lister is not None:
                ports = self._port_lister()
            else:
                _, list_ports = _serial_modules()
                ports = list_ports.comports()
        except HardwareError:
            raise
        except Exception as exc:
            raise HardwareError(f'读取串口列表失败：{exc}') from exc
        result = []
        for item in ports:
            result.append({
                'device': str(getattr(item, 'device', item)),
                'description': str(getattr(item, 'description', '') or ''),
                'vid': getattr(item, 'vid', None),
                'pid': getattr(item, 'pid', None),
                'serial_number': getattr(item, 'serial_number', None),
            })
        return result

    async def connect(self, port: str, baud: int = DEFAULT_BAUD) -> dict[str, Any]:
        return await asyncio.to_thread(self._connect_sync, port, baud)

    def _connect_sync(self, port: str, baud: int) -> dict[str, Any]:
        if not port or len(port) > 128:
            raise HardwareError('串口名称非法')
        if baud < 9_600 or baud > 3_000_000:
            raise HardwareError('串口波特率超出 9600..3000000')
        self._disconnect_sync('')
        try:
            if self._serial_factory is not None:
                device = self._serial_factory(port=port, baudrate=baud, timeout=.7, write_timeout=.7)
            else:
                serial, _ = _serial_modules()
                device = serial.Serial(port=port, baudrate=baud, timeout=.7, write_timeout=.7)
            with self._lock:
                self._serial = device
                self._state.update(connected=True, port=port, baud=baud, mode='CONNECTING', error='')
            reset_input = getattr(device, 'reset_input_buffer', None)
            if reset_input:
                reset_input()

            # Native USB starts immediately; UART bridge boards often reset on
            # open. Retry the harmless hello request for a bounded interval.
            deadline = time.monotonic() + 3.5
            last_error: Exception | None = None
            while time.monotonic() < deadline:
                try:
                    response = self._request_on_device(device, 'hello', model_id=self.model_id)
                    self._merge_response(response)
                    if response.get('protocol_version') != PROTOCOL_VERSION:
                        raise HardwareError('ESP32-S3 通信协议版本不兼容')
                    remote_model = response.get('state', response).get('model_id')
                    if remote_model not in (None, '', self.model_id):
                        raise HardwareError(f'固件模型 {remote_model} 与上位机 {self.model_id} 不一致')
                    return self.snapshot()
                except HardwareError as exc:
                    last_error = exc
                    time.sleep(.12)
            raise last_error or HardwareError('ESP32-S3 握手超时')
        except Exception as exc:
            message = str(exc)
            self._disconnect_sync(message)
            if isinstance(exc, HardwareError):
                raise
            raise HardwareError(f'打开串口 {port} 失败：{message}') from exc

    async def disconnect(self) -> dict[str, Any]:
        await asyncio.to_thread(self._disconnect_sync, '')
        return self.snapshot()

    def _disconnect_sync(self, error: str) -> None:
        with self._lock:
            device, self._serial = self._serial, None
        if device is not None:
            try:
                # Disarm is best effort. The firmware watchdog is the second
                # line of defence if the port has already failed.
                self._request_on_device(device, 'disarm')
            except Exception:
                pass
            try:
                device.close()
            except Exception:
                pass
        with self._lock:
            self._state = self._empty_state()
            self._state['error'] = error

    async def heartbeat(self) -> dict[str, Any]:
        # A single delayed USB CDC response is not enough evidence to tear down
        # the link. Correlation ids let a retry safely ignore a late first reply.
        response = await asyncio.to_thread(
            self._request_sync, 'heartbeat', transient_retries=1)
        self._merge_response(response)
        return self.snapshot()

    async def set_calibration(self, axis: int, min_us: int, center_us: int,
                              max_us: int, reversed: bool) -> dict[str, Any]:
        if axis < 1 or axis > 6:
            raise HardwareError('通道编号必须是 1..6')
        if not (500 <= min_us < center_us < max_us <= 2500):
            raise HardwareError('脉宽必须满足 500 ≤ min < center < max ≤ 2500 μs')
        if center_us - min_us < 100 or max_us - center_us < 100:
            raise HardwareError('中位到两端至少保留 100 μs')
        response = await asyncio.to_thread(
            self._request_sync, 'set_calibration', axis=axis - 1, min_us=min_us,
            center_us=center_us, max_us=max_us, reversed=bool(reversed))
        self._merge_response(response)
        return self.snapshot()

    async def center_axis(self, axis: int, confirmation: str) -> dict[str, Any]:
        if confirmation != 'SUPPORTED':
            raise HardwareError('测试中位前需确认机械臂已支撑，并传入 confirmation=SUPPORTED')
        if axis < 1 or axis > 6:
            raise HardwareError('通道编号必须是 1..6')
        response = await asyncio.to_thread(self._request_sync, 'center_axis', axis=axis - 1)
        self._merge_response(response)
        return self.snapshot()

    async def arm(self, q_deg: list[float], confirmation: str) -> dict[str, Any]:
        if confirmation != 'SUPPORTED':
            raise HardwareError('使能前需确认机械臂已支撑、舵盘已对中，并传入 confirmation=SUPPORTED')
        self._validate_q(q_deg)
        response = await asyncio.to_thread(self._request_sync, 'arm', q_deg=q_deg)
        self._merge_response(response)
        return self.snapshot()

    async def disarm(self) -> dict[str, Any]:
        response = await asyncio.to_thread(self._request_sync, 'disarm')
        self._merge_response(response)
        return self.snapshot()

    async def target(self, q_deg: list[float], duration_ms: int = 120) -> dict[str, Any]:
        self._validate_q(q_deg)
        state=self.snapshot()
        if state.get('mode') != 'ARMED':
            raise HardwareError('请等待使能过渡完成，或先退出单轴调试')
        self._validate_q(q_deg)
        if duration_ms < 20 or duration_ms > 5_000:
            raise HardwareError('手动跟随时间必须是 20..5000 ms')
        response = await asyncio.to_thread(
            self._request_sync, 'target', q_deg=q_deg, duration_ms=duration_ms)
        self._merge_response(response)
        return self.snapshot()

    async def prepare_plan(self, plan: dict[str, Any], start_delay_ms: int = 250) -> float:
        segments = plan.get('segments', [])
        if not segments or len(segments) > MAX_SEGMENTS:
            raise HardwareError(f'实机轨迹段数必须是 1..{MAX_SEGMENTS}')
        state=self.snapshot()
        if state.get('motion_busy') or state.get('mode') not in ('ARMED','PAUSED'):
            raise HardwareError('实机尚未停止或使能过渡未完成')
        segments = plan.get('segments', [])
        if not segments or len(segments) > MAX_SEGMENTS:
            raise HardwareError(f'实机轨迹段数必须是 1..{MAX_SEGMENTS}')
        start_deg = [math.degrees(v) for v in segments[0]['start']]
        self._validate_q(start_deg)
        await asyncio.to_thread(self._request_sync, 'prepare', count=len(segments),
                                model_id=self.model_id, start_deg=start_deg)
        try:
            for index, segment in enumerate(segments):
                end_deg = [math.degrees(v) for v in segment['end']]
                self._validate_q(end_deg)
                duration_ms = max(20, round(float(segment['duration']) * 1000))
                await asyncio.to_thread(self._request_sync, 'segment', index=index,
                                        end_deg=end_deg, duration_ms=duration_ms)
            sent = time.monotonic()
            response = await asyncio.to_thread(self._request_sync, 'commit', start_delay_ms=start_delay_ms)
            self._merge_response(response)
            # Caller starts the simulator after this remaining delay, so both
            # sides use the same host-selected epoch within serial RTT.
            return max(0.0, start_delay_ms / 1000 - (time.monotonic() - sent))
        except Exception:
            try:
                await asyncio.to_thread(self._request_sync, 'stop')
            except Exception:
                pass
            raise

    async def control(self, action: str) -> dict[str, Any]:
        if action not in ('pause', 'stop'):
            raise HardwareError('实机仅支持 pause 或 stop')
        response = await asyncio.to_thread(self._request_sync, action)
        self._merge_response(response)
        return self.snapshot()

    async def calibration_command(self, command: str, **payload):
        if self.snapshot().get('capabilities', {}).get('axis_calibration') != 1:
            raise HardwareError('请烧录支持单轴标定的 0.3.0 或更新固件')
        response = await asyncio.to_thread(self._request_sync, command, **payload)
        self._merge_response(response)
        return self.snapshot()

    def model_limits(self):
        state=self.snapshot()
        limits=state.get('model_limits_deg') if state.get('connected') and state.get('capabilities',{}).get('editable_limits')==1 else self.limits_deg
        if not isinstance(limits,list) or len(limits)!=6 or any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) or not -180<=p[0]<0<p[1]<=180 for p in limits):
            raise HardwareError('设备模型软限位无效，请重新连接并核对固件')
        return [list(v) for v in limits]

    def effective_limits(self):
        state=self.snapshot(); limits=self.model_limits()
        for i,m in enumerate(state.get('mappings', [])[:6]):
            if m.get('confirmed'):
                limits[i]=[max(limits[i][0],m['low_deg']),min(limits[i][1],m['high_deg'])]
        return limits

    def _validate_q(self, q_deg: list[float]) -> None:
        if len(q_deg) != 6 or any(not math.isfinite(float(v)) for v in q_deg):
            raise HardwareError('关节角度必须是 6 个有限数值')
        for index, (value, limits) in enumerate(zip(q_deg, self.effective_limits())):
            if value < limits[0] - 1e-6 or value > limits[1] + 1e-6:
                raise HardwareError(f'J{index + 1} 角度 {value:g}° 超出模型限位 {limits}')

    def _request_sync(self, command: str, *, transient_retries: int = 0,
                      **payload: Any) -> dict[str, Any]:
        with self._lock:
            device = self._serial
        if device is None:
            raise HardwareError('ESP32-S3 未连接')
        attempt = 0
        while True:
            try:
                response = self._request_on_device(device, command, **payload)
                with self._lock:
                    self._state['last_seen'] = time.time()
                    self._state['error'] = ''
                return response
            except HardwareRejected as exc:
                with self._lock:
                    self._state['last_seen'] = time.time()
                    self._state['error'] = str(exc)
                raise
            except HardwareTimeout as exc:
                if attempt < transient_retries:
                    attempt += 1
                    continue
                message = str(exc)
                self._disconnect_sync(message)
                raise
            except Exception as exc:
                message = str(exc)
                self._disconnect_sync(message)
                if isinstance(exc, HardwareError):
                    raise
                raise HardwareError(f'ESP32-S3 通信失败：{message}') from exc

    def _request_on_device(self, device: Any, command: str, **payload: Any) -> dict[str, Any]:
        with self._lock:
            self._request_id += 1
            request_id = self._request_id
            message = {'protocol_version': PROTOCOL_VERSION, 'id': request_id,
                       'command': command, **payload}
            encoded = (json.dumps(message, separators=(',', ':'), ensure_ascii=False) + '\n').encode('utf-8')
            if len(encoded) > 2048:
                raise HardwareError('发送给 ESP32-S3 的命令过长')
            device.write(encoded)
            flush = getattr(device, 'flush', None)
            if flush:
                flush()
            for _ in range(8):
                line = device.readline()
                if not line:
                    raise HardwareTimeout(f'ESP32-S3 命令 {command} 响应超时')
                if len(line) > 16384:
                    raise HardwareError('ESP32-S3 响应过长')
                try:
                    response = json.loads(line.decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue  # Ignore boot logs and partial diagnostic lines.
                if response.get('reply_to') != request_id:
                    continue
                if response.get('protocol_version') != PROTOCOL_VERSION:
                    raise HardwareError('ESP32-S3 返回了不兼容的协议版本')
                if not response.get('ok'):
                    raise HardwareRejected(str(response.get('error', 'ESP32-S3 拒绝命令')))
                return response
            raise HardwareTimeout(f'ESP32-S3 命令 {command} 未收到匹配响应')

    def _merge_response(self, response: dict[str, Any]) -> None:
        remote = response.get('state', response)
        allowed = ('armed', 'mode', 'firmware_version', 'model_id', 'driver_ready',
                   'outputs_enabled', 'calibrated', 'calibration', 'commanded_q_deg',
                   'measured_q_deg', 'measured_feedback', 'capabilities', 'device_id', 'wiring',
                   'wiring_hash', 'tick_us', 'test', 'mappings', 'motion_busy', 'model_limits_deg', 'limits_revisions')
        with self._lock:
            for key in allowed:
                if key in remote:
                    self._state[key] = remote[key]
            self._state['connected'] = True
            self._state['last_seen'] = time.time()
            self._state['error'] = ''
