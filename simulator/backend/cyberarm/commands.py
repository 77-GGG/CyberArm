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


@dataclass(frozen=True)
class Spec:
    model: type[BaseModel]
    usage: str
    description: str
    mutates: bool = False


def registry():
    from .server import PlanRequest
    return {
        'help': Spec(Help, 'help [命令]', '查看命令及参数'),
        'status': Spec(Empty, 'status', '当前状态、关节、TCP、规划与错误'),
        'joints': Spec(Empty, 'joints', '查询 J1–J5 和夹爪角度（度）'),
        'tcp': Spec(Empty, 'tcp', '查询 TCP 位置（mm）和工具方向，底座坐标系'),
        'limits': Spec(Empty, 'limits', '查询模型限位（尚未经实物标定）'),
        'events': Spec(Empty, 'events', '最近运行记录'),
        'device': Spec(Empty, 'device', '通信能力与状态来源；当前为仿真'),
        'joint': Spec(Joint, 'joint <1..6> <角度>', '检查整段路径后更新一个仿真关节；6 为夹爪', True),
        'grip': Spec(Grip, 'grip <角度>', '检查后更新仿真夹爪角度，非开口毫米数', True),
        'pose': Spec(Pose, 'pose <J1 J2 J3 J4 J5 G>', '检查后直接更新仿真姿态，无动画', True),
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
    raise ValueError('用法：' + specs[name].usage)


def device_info():
    return {'backend': 'simulator', 'connected': True, 'protocol_version': 1,
            'transport': 'local-http-websocket', 'state_source': 'simulation',
            'hardware_connected': False, 'measured_feedback': False,
            'devices': [{'name': name, 'connected': False} for name in ('ESP32-S3', 'K230D', 'servo')],
            'units': {'joint': 'degree', 'position': 'mm', 'frame': 'base'},
            'hardware_transports': [], 'commands': list(registry())}


async def dispatch(name, args, request):
    from . import server as s
    client = request.headers.get('x-client', 'sdk')
    if name == 'help':
        return catalogue(args.name)
    if name == 'device':
        return device_info()
    if name == 'status':
        return {**s.c.snapshot(), 'state_source': 'simulation', 'hardware_connected': False}
    if name == 'joints':
        return {'q_deg': s.c.snapshot()['q_deg'], 'state_source': 'simulation'}
    if name == 'tcp':
        tcp = s.c.snapshot()['tcp']
        return {'position_mm': [tcp[i][3]*1000 for i in range(3)],
                'direction': [tcp[i][2] for i in range(3)], 'frame': 'base', 'state_source': 'simulation'}
    if name == 'limits':
        return {'limits_deg': s.c.r.data['limits_deg'], 'calibrated': False}
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
    return {'accepted': True, 'plan_id': plan['plan_id'], 'duration': plan['duration'],
            'message': '已开始模拟执行；用 status 查询完成状态'}


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
