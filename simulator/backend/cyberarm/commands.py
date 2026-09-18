"""Versioned command gateway. All motion goes through the simulator's guards.

Text is parsed as data, never evaluated as Python or a system shell.
The registry is also the source of console help and machine-readable schemas.
"""
from dataclasses import dataclass
import json
import shlex
import time
from typing import Literal
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class CommandRequest(Strict):
    protocol_version: Literal[1] = 1
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=1, max_length=128)
    text: str | None = Field(default=None, min_length=1, max_length=16384)
    command: str | None = Field(default=None, min_length=1, max_length=64)
    args: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def one_form(self):
        if (self.text is None) == (self.command is None) or (self.text is not None and self.args):
            raise ValueError('只提供 text 或 command + args')
        return self


class Empty(Strict):
    pass


class Help(Strict):
    name: str | None = None


class Joint(Strict):
    index: int = Field(ge=1, le=6)
    angle_deg: float


class Grip(Strict):
    angle_deg: float


class Pose(Strict):
    q_deg: list[float] = Field(min_length=6, max_length=6)


class MoveJ(Pose):
    speed: float = Field(default=.7, ge=.05, le=1)


class MoveTo(Strict):
    position_mm: list[float] = Field(min_length=3, max_length=3)
    direction: list[float] | None = Field(default=None, min_length=3, max_length=3)
    speed: float = Field(default=.7, ge=.05, le=1)

    @model_validator(mode='after')
    def nonzero(self):
        if self.direction is not None and sum(x*x for x in self.direction) < 1e-16:
            raise ValueError('工具方向不能为零')
        return self


class Execute(Strict):
    plan_id: str = Field(min_length=1, max_length=128)


class HardwareConnect(Strict):
    port: str = Field(min_length=1, max_length=128)
    baud: int = Field(default=921600, ge=9600, le=3000000)


class HardwareCalibration(Strict):
    axis: int = Field(ge=1, le=6)
    min_us: int = Field(ge=500, le=2500)
    center_us: int = Field(ge=500, le=2500)
    max_us: int = Field(ge=500, le=2500)
    reversed: bool = False

    @model_validator(mode='after')
    def ordered(self):
        if not self.min_us < self.center_us < self.max_us:
            raise ValueError('脉宽必须满足 min < center < max')
        return self


class HardwareAxis(Strict):
    axis: int = Field(ge=1, le=6)
    confirmation: Literal['SUPPORTED']


class HardwareArm(Strict):
    confirmation: Literal['SUPPORTED']


@dataclass(frozen=True)
class Spec:
    model: type[BaseModel]
    usage: str
    description: str
    mutates: bool = False


def registry():
    from .server import PlanRequest
    from .calibration_api import TestCommand, Mapping, Draft
    return {
        'help': Spec(Help, 'help [命令]', '查看命令及参数'),
        'status': Spec(Empty, 'status', '当前状态、关节、TCP、规划与错误'),
        'joints': Spec(Empty, 'joints', '查询 J1–J5 和夹爪角度（度）'),
        'tcp': Spec(Empty, 'tcp', '查询 TCP 位置（mm）和工具方向，底座坐标系'),
        'limits': Spec(Empty, 'limits', '查询模型限位与六路实机校准状态'),
        'events': Spec(Empty, 'events', '最近运行记录'),
        'device': Spec(Empty, 'device', '通信能力、状态来源与已连接设备'),
        'hwtest': Spec(TestCommand, 'hwtest {"action":"begin","axis":1,"confirmation":"SUPPORTED"}', '单轴调试：begin/target/angle/hold/renew/end；测试时每 0.3 秒续约', True),
        'hwmapping': Spec(Mapping, 'hwmapping <JSON>', '确认保存实测角度映射并读回', True),
        'hwdraft': Spec(Draft, 'hwdraft <JSON>', '保存当前设备单轴测量草稿', True),
        'hwrecords': Spec(Empty, 'hwrecords', '读取测量记录和固件标定'),
        'hwstatus': Spec(Empty, 'hwstatus', '查询 ESP32-S3、PWM、校准和实机跟随状态'),
        'hwports': Spec(Empty, 'hwports', '列出可用串口'),
        'hwconnect': Spec(HardwareConnect, 'hwconnect <串口> [波特率]', '连接 ESP32-S3；连接不会使舵机动作', True),
        'hwdisconnect': Spec(Empty, 'hwdisconnect', '关闭 PWM 并断开 ESP32-S3', True),
        'hwcal': Spec(HardwareCalibration, 'hwcal <1..6> <min_us> <center_us> <max_us> [true|false]', '保存一路舵机脉宽和方向校准', True),
        'hwcenter': Spec(HardwareAxis, 'hwcenter <1..6> SUPPORTED', '机械臂已支撑时，仅输出一路舵机中位', True),
        'hwarm': Spec(HardwareArm, 'hwarm SUPPORTED', '确认机械臂已支撑并使能实机跟随', True),
        'hwdisarm': Spec(Empty, 'hwdisarm', '关闭实机跟随并释放全部 PWM', True),
        'joint': Spec(Joint, 'joint <1..6> <角度>', '检查路径后更新一个关节；实机使能时同步，6 为夹爪', True),
        'grip': Spec(Grip, 'grip <角度>', '检查后更新夹爪驱动角；实机使能时同步，非开口毫米数', True),
        'pose': Spec(Pose, 'pose <J1 J2 J3 J4 J5 G>', '检查后更新整组姿态；实机端做短时平滑跟随', True),
        'movej': Spec(MoveJ, 'movej <J1 J2 J3 J4 J5 G> [速度0.05..1]', '规划并立即执行关节运动', True),
        'moveto': Spec(MoveTo, 'moveto <X Y Z> [速度0.05..1]', '逆解、检查后立即执行点到点运动（mm）', True),
        'movel': Spec(MoveTo, 'movel <X Y Z> [速度0.05..1]', '检查后立即执行 TCP 直线运动（mm）', True),
        'plan': Spec(PlanRequest, 'plan {"steps":[{"kind":"joint","q_deg":[3,0,0,0,0,0]}]}', '只规划；返回 plan_id，120 秒有效', True),
        'execute': Spec(Execute, 'execute <plan_id>', '执行当前客户端的有效规划', True),
        'pause': Spec(Empty, 'pause', '沿验证路径减速暂停', True),
        'stop': Spec(Empty, 'stop', '停止并取消待执行/正在计算的结果', True),
        'resume': Spec(Empty, 'resume', '重新规划剩余动作并立即执行', True),
        'reset': Spec(Empty, 'reset', '重置仿真状态；不是实物回零', True),
    }


def catalogue(name=None):
    specs = registry()
    if name is not None and name not in specs:
        raise ValueError(f'未知命令：{name}；输入 help 查看列表')
    return [{"command": key, "usage": spec.usage, "description": spec.description,
             "mutates": spec.mutates, "args_schema": spec.model.model_json_schema()}
            for key, spec in specs.items() if name is None or key == name]


def parse_text(text):
    head = text.strip().split(maxsplit=1)
    if not head:
        raise ValueError('命令不能为空')
    name = head[0].lower()
    specs = registry()
    if name not in specs:
        raise ValueError(f'未知命令：{name}；输入 help 查看列表')
    tail = head[1] if len(head) > 1 else ''
    # JSON goes directly to the schema validator; shlex would remove JSON quotes.
    if tail.startswith('{'):
        return name, json.loads(tail)
    words = shlex.split(tail)
    if name == 'help' and len(words) <= 1:
        return name, {'name': words[0]} if words else {}
    if specs[name].model is Empty and not words:
        return name, {}
    if name == 'joint' and len(words) == 2:
        return name, dict(index=int(words[0]), angle_deg=float(words[1]))
    if name == 'grip' and len(words) == 1:
        return name, dict(angle_deg=float(words[0]))
    if name in ('pose', 'movej') and len(words) in ((6,) if name == 'pose' else (6, 7)):
        return name, {'q_deg': [float(v) for v in words[:6]], **({'speed': float(words[6])} if len(words) == 7 else {})}
    if name in ('moveto', 'movel') and len(words) in (3, 4):
        return name, {'position_mm': [float(v) for v in words[:3]], **({'speed': float(words[3])} if len(words) == 4 else {})}
    if name == 'execute' and len(words) == 1:
        return name, {'plan_id': words[0]}
    if name == 'hwconnect' and len(words) in (1, 2):
        return name, {'port': words[0], **({'baud': int(words[1])} if len(words) == 2 else {})}
    if name == 'hwcal' and len(words) in (4, 5):
        reverse = words[4].lower() in ('1', 'true', 'yes', 'reverse') if len(words) == 5 else False
        if len(words) == 5 and words[4].lower() not in ('0', '1', 'true', 'false', 'yes', 'no', 'reverse', 'normal'):
            raise ValueError('方向使用 true/false')
        return name, {'axis': int(words[0]), 'min_us': int(words[1]), 'center_us': int(words[2]),
                      'max_us': int(words[3]), 'reversed': reverse}
    if name == 'hwcenter' and len(words) == 2:
        return name, {'axis': int(words[0]), 'confirmation': words[1]}
    if name == 'hwarm' and len(words) == 1:
        return name, {'confirmation': words[0]}
    raise ValueError('用法：' + specs[name].usage)


def device_info():
    from . import server as s
    hardware = s.hardware.snapshot() if s.hardware else {'connected': False, 'measured_feedback': False}
    return {'backend': 'simulator', 'connected': True, 'protocol_version': 1,
            'transport': 'local-http-websocket', 'state_source': 'simulation',
            'hardware_connected': hardware.get('connected', False),
            'hardware_armed': hardware.get('armed', False),
            'measured_feedback': hardware.get('measured_feedback', False),
            'devices': [{'name': 'ESP32-S3', 'connected': hardware.get('connected', False)},
                        {'name': 'PCA9685', 'connected': hardware.get('driver_ready', False)},
                        {'name': 'K230D', 'connected': False},
                        {'name': 'servo-feedback', 'connected': hardware.get('measured_feedback', False)}],
            'units': {'joint': 'degree', 'position': 'mm', 'frame': 'base'},
            'hardware_transports': ['usb-cdc-jsonl-v1'], 'hardware': hardware,
            'commands': list(registry())}


async def dispatch(name, args, request):
    from . import server as s
    client = request.headers.get('x-client', 'sdk')
    if name == 'help':
        return catalogue(args.name)
    if name == 'device':
        return device_info()
    if name in ('hwtest','hwmapping','hwdraft','hwrecords'):
        from . import calibration_api as cal
        if name=='hwtest':return await cal.test(args,request)
        if name=='hwmapping':return await cal.save(args)
        if name=='hwdraft':return await cal.draft(args)
        return await cal.records()
    if name == 'hwstatus':
        return s.hardware.snapshot()
    if name == 'hwports':
        try:return {'ports': await s.hardware.list_ports()}
        except Exception as exc:raise HTTPException(503, str(exc))
    if name == 'hwconnect':
        return await s.hardware_connect(s.HardwareConnect(port=args.port, baud=args.baud))
    if name == 'hwdisconnect':
        return await s.hardware_disconnect()
    if name == 'hwcal':
        return await s.hardware_calibration(s.HardwareCalibration(**args.model_dump()))
    if name == 'hwcenter':
        return await s.hardware_center(s.HardwareAxis(**args.model_dump()))
    if name == 'hwarm':
        return await s.hardware_arm(s.HardwareArm(**args.model_dump()))
    if name == 'hwdisarm':
        return await s.hardware_disarm()
    if name == 'status':
        snapshot=s.c.snapshot()
        return {**snapshot, 'state_source': 'simulation',
                'hardware_connected': bool(snapshot.get('hardware', {}).get('connected'))}
    if name == 'joints':
        snapshot=s.c.snapshot();hardware=snapshot.get('hardware') or {}
        return {'q_deg': snapshot['q_deg'], 'state_source': 'simulation',
                'hardware_commanded_q_deg': hardware.get('commanded_q_deg'),
                'hardware_measured_q_deg': hardware.get('measured_q_deg')}
    if name == 'tcp':
        tcp = s.c.snapshot()['tcp']
        return {'position_mm': [tcp[i][3]*1000 for i in range(3)],
                'direction': [tcp[i][2] for i in range(3)], 'frame': 'base', 'state_source': 'simulation'}
    if name == 'limits':
        calibrated=(s.hardware.snapshot().get('calibrated') if s.hardware else [False]*6)
        return {'limits_deg': s.effective_limits(), 'calibrated': calibrated,
                'all_calibrated': all(calibrated)}
    if name == 'events':
        return list(s.c.events)
    if name in ('joint', 'grip', 'pose'):
        q = s.c.snapshot()['q_deg']
        if name == 'pose':
            q = args.q_deg
        else:
            q[args.index-1 if name == 'joint' else 5] = args.angle_deg
        result = await s.manual(s.Manual(kind='joint', q_deg=q, seq=s.c.seq, revision=s.c.revision))
        if result['status'] != 'reachable':
            raise HTTPException(422, result.get('message', result['status']))
        return result
    if name in ('pause', 'stop', 'reset'):
        return await s.control(s.Control(action=name))
    if name == 'plan':
        return await s.make_plan(args, client)
    if name == 'execute':
        return await s.execute(s.Execute(plan_id=args.plan_id), request)
    if name == 'resume':
        plan = await s.resume(request)
    else:
        target = args.model_dump(exclude={'speed'}, exclude_none=True)
        step = s.Step(kind={'movej': 'joint', 'moveto': 'cartesian', 'movel': 'linear'}[name], **target)
        plan = await s.make_plan(s.PlanRequest(steps=[step], speed=args.speed), client)
    await s.execute(s.Execute(plan_id=plan['plan_id']), request)
    mirrored=bool(s.hardware.snapshot().get('armed'))
    return {'accepted': True, 'plan_id': plan['plan_id'], 'duration': plan['duration'],
            'hardware_mirroring': mirrored,
            'message': '已开始'+('实机同步' if mirrored else '模拟')+'执行；用 status 查询完成状态'}


async def run_command(body, request):
    from . import server as s
    name = body.command
    started = time.monotonic()
    result = {'protocol_version': 1, 'request_id': body.request_id, 'ok': False, 'command': name}
    try:
        if body.text is not None:
            name, values = parse_text(body.text)
        else:
            values = body.args
        result['command'] = name
        spec = registry().get(name)
        if spec is None:
            raise ValueError(f'未知命令：{name}；输入 help 查看列表')
        args = spec.model.model_validate(values)
        result['data'] = await dispatch(name, args, request)
        result['ok'] = True
        if spec.mutates:
            s.c.log(f'命令 {name} 已接受')
    except (ValueError, ValidationError, HTTPException) as exc:
        code = exc.status_code if isinstance(exc, HTTPException) else 422
        message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
        result['error'] = {'code': code, 'message': message}
    result['elapsed_ms'] = round((time.monotonic()-started)*1000, 1)
    return result
