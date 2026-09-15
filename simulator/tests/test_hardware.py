import copy
import asyncio
import json
import math

import pytest

from cyberarm.hardware import HardwareBridge, HardwareError
from cyberarm import server
from fastapi.testclient import TestClient


class FakePort:
    device = 'COM42'
    description = 'ESP32-S3 USB CDC'
    vid = 0x303A
    pid = 0x1001
    serial_number = 'CYBERARM-TEST'


class FakeSerial:
    def __init__(self, **options):
        self.options = options
        self.responses = []
        self.commands = []
        self.closed = False
        self.state = {
            'firmware_version': 'test-1', 'model_id': 'revc-sim-1',
            'driver_ready': True, 'armed': False, 'outputs_enabled': False,
            'mode': 'DISARMED', 'calibrated': [False] * 6,
            'calibration': [None] * 6, 'commanded_q_deg': [0.0] * 6,
            'measured_q_deg': None, 'measured_feedback': False,
        }
        self.expected = 0
        self.segments = []

    def reset_input_buffer(self):
        self.responses.clear()

    def write(self, encoded):
        command = json.loads(encoded)
        self.commands.append(command)
        name = command['command']
        ok, error = True, None
        if name == 'set_calibration':
            axis = command['axis']
            self.state['calibrated'][axis] = True
            self.state['calibration'][axis] = {
                key: command[key] for key in ('min_us', 'center_us', 'max_us', 'reversed')
            } | {'confirmed': True}
        elif name == 'center_axis':
            self.state.update(mode='SERVICE', outputs_enabled=True)
        elif name == 'arm':
            if not all(self.state['calibrated']):
                ok, error = False, 'not calibrated'
            else:
                self.state.update(mode='ARMED', armed=True, outputs_enabled=True,
                                  commanded_q_deg=command['q_deg'])
        elif name == 'disarm':
            self.state.update(mode='DISARMED', armed=False, outputs_enabled=False)
        elif name == 'target':
            self.state['commanded_q_deg'] = command['q_deg']
        elif name == 'prepare':
            self.expected = command['count']
            self.segments = []
            self.state['mode'] = 'PREPARED'
        elif name == 'segment':
            self.segments.append(command)
        elif name == 'commit':
            if len(self.segments) != self.expected:
                ok, error = False, 'incomplete'
            else:
                self.state['mode'] = 'WAITING'
        elif name == 'pause':
            self.state['mode'] = 'PAUSED' if self.state['mode'] == 'RUNNING' else 'ARMED'
        elif name == 'stop':
            self.state['mode'] = 'ARMED'
        response = {'protocol_version': 1, 'reply_to': command['id'], 'ok': ok,
                    'state': copy.deepcopy(self.state)}
        if error:
            response['error'] = error
        self.responses.append((json.dumps(response) + '\n').encode())
        return len(encoded)

    def flush(self):
        pass

    def readline(self):
        return self.responses.pop(0) if self.responses else b''

    def close(self):
        self.closed = True


def test_safe_connect_calibrate_center_arm_and_mirror_plan():
    asyncio.run(_safe_connect_calibrate_center_arm_and_mirror_plan())


async def _safe_connect_calibrate_center_arm_and_mirror_plan():
    serials = []

    def factory(**options):
        serials.append(FakeSerial(**options))
        return serials[-1]

    bridge = HardwareBridge('revc-sim-1', [[-30, 30]] * 5 + [[-8, 8]],
                            serial_factory=factory, port_lister=lambda: [FakePort()])
    assert (await bridge.list_ports())[0]['device'] == 'COM42'
    state = await bridge.connect('COM42')
    assert state['connected'] and not state['armed'] and not state['outputs_enabled']
    assert serials[0].commands[0]['command'] == 'hello'
    with pytest.raises(HardwareError, match='not calibrated'):
        await bridge.arm([0] * 6, 'SUPPORTED')
    assert bridge.snapshot()['connected']  # A valid firmware rejection keeps the healthy link.

    for axis in range(1, 7):
        state = await bridge.set_calibration(axis, 1000, 1500, 2000, axis % 2 == 0)
    assert all(state['calibrated'])
    state = await bridge.center_axis(1, 'SUPPORTED')
    assert state['mode'] == 'SERVICE' and state['outputs_enabled']
    await bridge.disarm()
    with pytest.raises(HardwareError, match='SUPPORTED'):
        await bridge.arm([0] * 6, 'NO')
    state = await bridge.arm([0] * 6, 'SUPPORTED')
    assert state['armed'] and state['outputs_enabled']
    state = await bridge.target([2, 1, 0, 0, 0, 1])
    assert state['commanded_q_deg'] == [2, 1, 0, 0, 0, 1]

    plan = {'segments': [
        {'start': [math.radians(v) for v in [2, 1, 0, 0, 0, 1]],
         'end': [math.radians(v) for v in [3, 1, 0, 0, 0, 1]], 'duration': .4},
        {'start': [math.radians(v) for v in [3, 1, 0, 0, 0, 1]],
         'end': [math.radians(v) for v in [3, 0, 0, 0, 0, 0]], 'duration': .6},
    ]}
    remaining = await bridge.prepare_plan(plan)
    assert 0 < remaining <= .25
    assert [item['command'] for item in serials[0].commands[-4:]] == [
        'prepare', 'segment', 'segment', 'commit']
    assert serials[0].segments[0]['duration_ms'] == 400
    assert serials[0].segments[1]['end_deg'] == pytest.approx([3, 0, 0, 0, 0, 0])
    serials[0].state['mode'] = 'RUNNING'
    assert (await bridge.control('pause'))['mode'] == 'PAUSED'
    await bridge.disconnect()
    assert serials[0].closed and not bridge.snapshot()['connected']


def test_host_side_limits_and_calibration_guards_do_not_write():
    asyncio.run(_host_side_limits_and_calibration_guards_do_not_write())


async def _host_side_limits_and_calibration_guards_do_not_write():
    serial = FakeSerial()
    bridge = HardwareBridge('revc-sim-1', [[-30, 30]] * 5 + [[-8, 8]],
                            serial_factory=lambda **_: serial)
    await bridge.connect('COM42')
    before = len(serial.commands)
    with pytest.raises(HardwareError, match='min < center < max'):
        await bridge.set_calibration(1, 1600, 1500, 2000, False)
    with pytest.raises(HardwareError, match='超出模型限位'):
        await bridge.target([31, 0, 0, 0, 0, 0])
    with pytest.raises(HardwareError, match='1..512'):
        await bridge.prepare_plan({'segments': []})
    assert len(serial.commands) == before


class MirrorStub:
    def __init__(self):
        self.calls = []
        self.state = {
            'available': True, 'connected': True, 'armed': True,
            'outputs_enabled': True, 'mode': 'ARMED', 'port': 'FAKE',
            'baud': 921600, 'protocol_version': 1, 'firmware_version': 'test',
            'model_id': 'revc-sim-1', 'driver_ready': True,
            'calibrated': [True] * 6, 'calibration': [None] * 6,
            'commanded_q_deg': [0] * 6, 'measured_q_deg': None,
            'measured_feedback': False, 'last_seen': 1, 'error': '',
        }

    def snapshot(self):
        return copy.deepcopy(self.state)

    async def heartbeat(self):
        return self.snapshot()

    async def target(self, q_deg, duration_ms=120):
        self.calls.append(('target', q_deg, duration_ms))
        self.state['commanded_q_deg'] = q_deg
        return self.snapshot()

    async def prepare_plan(self, plan):
        self.calls.append(('prepare_plan', plan['plan_id']))
        return 0

    async def control(self, action):
        self.calls.append(('control', action))
        return self.snapshot()

    async def disconnect(self):
        self.state.update(connected=False, armed=False, outputs_enabled=False)
        return self.snapshot()


def test_server_mirrors_manual_plan_and_stop(monkeypatch):
    with TestClient(server.app) as client:
        stub = MirrorStub()
        monkeypatch.setattr(server, 'hardware', stub)
        boot = client.get('/api/bootstrap').json()
        headers = {'X-Session': boot['session'], 'X-Client': 'mirror-test'}
        manual = client.post('/api/manual', headers=headers, json={
            'kind': 'joint', 'q_deg': [2, 0, 0, 0, 0, 0],
            'seq': boot['state']['seq'], 'revision': boot['state']['revision'],
        })
        assert manual.status_code == 200, manual.text
        assert stub.calls[-1][0] == 'target'
        planned = client.post('/api/plan', headers=headers, json={
            'steps': [{'kind': 'joint', 'q_deg': [3, 0, 0, 0, 0, 0]}], 'speed': .7,
        })
        assert planned.status_code == 200, planned.text
        plan = planned.json()
        executed = client.post('/api/execute', headers=headers, json={'plan_id': plan['plan_id']})
        assert executed.status_code == 200, executed.text
        assert ('prepare_plan', plan['plan_id']) in stub.calls
        stopped = client.post('/api/control', headers=headers, json={'action': 'stop'})
        assert stopped.status_code == 200, stopped.text
        assert ('control', 'stop') in stub.calls
        reset = client.post('/api/control', headers=headers, json={'action': 'reset'})
        assert reset.status_code == 409
