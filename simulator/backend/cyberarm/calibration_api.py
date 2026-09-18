"""Single-axis workbench. Lease is owned by the page, not background heartbeat."""
import asyncio
import json
import secrets
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from .calibration import CalibrationStore, validate_mapping, angle_pulse
from .hardware import HardwareError
from .model import validate_gripper_range

router=APIRouter(prefix='/api/hardware/calibration-workbench')


@router.get('/reference')
async def zero_reference(axis:int=1):
    """Pure FK reference; never changes simulator state or sends serial commands."""
    if not 1<=axis<=6:raise HTTPException(422,'关节编号必须是 1–6')
    import numpy as np
    r=server().c.r
    zero=np.zeros(6);positive=zero.copy();positive[axis-1]=np.radians(5)
    frames,_=r.fk(zero)
    frame=frames[axis-1] if axis<6 else frames[6]
    direction=frame[:3,2] if axis<6 else frames[5,:3,1]
    def pose(q):
        matrices,tcp=r.transforms(q)
        return {'matrices':matrices,'tcp':tcp}
    return {'zero':pose(zero),'positive':pose(positive),'origin':frame[:3,3].tolist(),
            'direction':direction.tolist(),'model_id':r.data['model_id']}


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class TestCommand(Strict):
    action:Literal['begin','target','angle','hold','renew','end']
    axis:int=Field(default=1,ge=1,le=6)
    pulse_us:float=Field(default=1500,ge=500,le=2500)
    low_us:float=Field(default=1400,ge=500,le=2500)
    high_us:float=Field(default=1600,ge=500,le=2500)
    rate_us_s:float=Field(default=50,ge=5,le=200)
    angle_deg:float=0
    confirmation:Literal['SUPPORTED']|None=None


class Point(Strict):
    deg:float=Field(ge=-180,le=180)
    us:float=Field(ge=500,le=2500)


class Mapping(Strict):
    axis:int=Field(ge=1,le=6)
    points:list[Point]=Field(min_length=3,max_length=7)
    low_deg:float
    high_deg:float
    confirmed:Literal[True]
    wiring_hash:str
    device_id:str
    expected_revision:int=Field(ge=0)


class Draft(Strict):
    axis:int=Field(ge=1,le=6)
    data:dict


class Limits(Strict):
    axis:int=Field(ge=1,le=6)
    low_deg:float=Field(ge=-180,lt=0)
    high_deg:float=Field(gt=0,le=180)
    device_id:str
    wiring_hash:str
    expected_revision:int=Field(ge=0)
    confirmed:Literal[True]


def server():
    from . import server as s
    return s


def require_idle():
    s=server()
    if s.c.mode not in ('READY','PAUSED') or s.c.busy or s.manual_busy:
        raise HTTPException(409,'请先停止整机运动或等待规划完成')
    if s.hardware.snapshot().get('armed'):
        raise HTTPException(409,'请先关闭整机跟随')
    return s


def invalidate(s):
    s.c.generation+=1;s.c.seq+=1;s.c.plans.clear();s.c.paused=None


@router.post('/test')
async def test(body:TestCommand,request:Request):
    s=require_idle();client=request.headers.get('x-client','sdk')
    async with s.calibration_lock:
        s=require_idle()
        try:
            if body.action=='begin':
                if body.confirmation!='SUPPORTED':raise ValueError('请确认已断开传动或支撑机构，第一帧位置未知')
                if not body.low_us <= body.pulse_us <= body.high_us or body.low_us>=body.high_us:raise ValueError('初始脉宽必须位于测试窗口内')
                if s.hardware.snapshot().get('outputs_enabled'):raise ValueError('请先关闭当前输出')
                session=secrets.randbelow(2**31-1)+1
                generation=s.c.generation
                s.calibration_owner=(client,session,body.axis)
                state=await s.hardware.calibration_command('test_begin',test_session=session,axis=body.axis-1,
                    pulse_us=body.pulse_us,low_us=body.low_us,high_us=body.high_us,rate_us_s=body.rate_us_s,confirmation='SUPPORTED')
                if generation!=s.c.generation:
                    await s.hardware.disarm();s.calibration_owner=None
                    raise ValueError('开启期间已取消，单路输出已关闭')
                s.calibration_owner=(client,session,body.axis)
                invalidate(s)
            else:
                owner=s.calibration_owner
                if not owner or owner[0]!=client:raise ValueError('当前页面不拥有单轴调试会话')
                payload={'test_session':owner[1]}
                action=body.action
                if action in ('target','angle'):
                    pulse=body.pulse_us
                    if action=='angle':
                        m=s.hardware.snapshot()['mappings'][owner[2]-1]
                        if not m['confirmed']:raise ValueError('请先保存并确认角度标定')
                        pulse=angle_pulse({'points':m['points'],'low_deg':m['low_deg'],'high_deg':m['high_deg']},body.angle_deg)
                    payload['pulse_us']=pulse;action='target'
                state=await s.hardware.calibration_command('test_'+action,**payload)
                if action=='end':s.calibration_owner=None
            return state
        except (HardwareError,ValueError) as exc:
            if body.action=='begin':s.calibration_owner=None
            raise HTTPException(409,str(exc))


@router.get('/records')
async def records():
    s=server()
    try:
        state=s.hardware.snapshot();result=await asyncio.to_thread(s.calibration_store.read,state)
        result['current_mappings']=state.get('mappings',[])
        result['backup_matches']=result.get('saved_mappings')==result['current_mappings']
        return result
    except (ValueError,OSError,json.JSONDecodeError) as exc:raise HTTPException(422,str(exc))


@router.post('/limits')
async def save_limits(body:Limits):
    s=require_idle()
    async with s.calibration_lock:
        s=require_idle()
        try:
            state=s.hardware.snapshot();index=body.axis-1
            if state.get('capabilities',{}).get('editable_limits')!=1:raise ValueError('请烧录支持可调软限位的 0.4.0 或更新固件')
            if state.get('outputs_enabled') or state.get('test',{}).get('active'):raise ValueError('修改模型软限位前请关闭所有输出')
            if (body.device_id,body.wiring_hash)!=(state.get('device_id'),state.get('wiring_hash')):raise ValueError('设备或接线已变化，请重新加载')
            if state['limits_revisions'][index]!=body.expected_revision:raise ValueError('软限位版本已变化，请重新加载设备值')
            q=s.c.snapshot()['q_deg'][index]
            if not body.low_deg<=q<=body.high_deg:raise ValueError('当前仿真姿态在新范围之外，请先在仅仿真模式移回范围内')
            if index==5:validate_gripper_range(body.low_deg,body.high_deg)
            state=await s.hardware.calibration_command('save_limits',axis=index,low_deg=body.low_deg,high_deg=body.high_deg,
                expected_revision=body.expected_revision,confirmed=True,model_id=state['model_id'],wiring_hash=body.wiring_hash)
            invalidate(s)
            actual=state['model_limits_deg'][index]
            if state['limits_revisions'][index]!=body.expected_revision+1 or any(abs(a-b)>.001 for a,b in zip(actual,[body.low_deg,body.high_deg])):
                await s.hardware.disconnect()
                raise ValueError('软限位读回不一致，已断开连接，请重新核对设备')
            warning=''
            try:
                data=await asyncio.to_thread(s.calibration_store.read,state);data['model_limits_deg']=state['model_limits_deg'];data['limits_revisions']=state['limits_revisions']
                data['saved_mappings']=state['mappings'];await asyncio.to_thread(s.calibration_store.write,state,data)
            except (OSError,ValueError,json.JSONDecodeError) as exc:warning='设备已保存，但电脑备份失败：'+str(exc)
            return {'state':state,'warning':warning}
        except (ValueError,KeyError,HardwareError) as exc:raise HTTPException(422,str(exc))


@router.post('/draft')
async def draft(body:Draft):
    s=server()
    if len(json.dumps(body.data,ensure_ascii=False,allow_nan=False))>64000:raise HTTPException(422,'单轴记录过长')
    async with s.calibration_lock:
        try:
            state=s.hardware.snapshot();data=await asyncio.to_thread(s.calibration_store.read,state)
            data['axes'][str(body.axis)]=body.data;await asyncio.to_thread(s.calibration_store.write,state,data)
            return {'ok':True}
        except (ValueError,OSError) as exc:raise HTTPException(422,str(exc))


@router.post('/save')
async def save(body:Mapping):
    s=require_idle()
    async with s.calibration_lock:
        s=require_idle()
        try:
            state=s.hardware.snapshot()
            if state.get('outputs_enabled'):raise ValueError('保存前请关闭单路输出')
            if (body.device_id,body.wiring_hash)!=(state.get('device_id'),state.get('wiring_hash')):raise ValueError('设备或接线配置已变化，请重新加载')
            old=state['mappings'][body.axis-1]
            if body.expected_revision!=old['revision']:raise ValueError('标定版本已变化，请先查看设备当前值')
            m=validate_mapping(body.model_dump())
            state=await s.hardware.calibration_command('save_mapping',axis=body.axis-1,**m,
                    model_id=state['model_id'],wiring_hash=body.wiring_hash,expected_revision=body.expected_revision,confirmed=True)
            invalidate(s)
            actual=state['mappings'][body.axis-1]
            def close(a,b):return abs(a-b)<.001
            if not actual['confirmed'] or actual['revision']!=body.expected_revision+1 or not close(actual['work_low_deg'],m['low_deg']) or not close(actual['work_high_deg'],m['high_deg']) or len(actual['points'])!=len(m['points']) or any(not close(a[k],b[k]) for a,b in zip(actual['points'],m['points']) for k in ('deg','us')):
                raise ValueError('固件标定读回不一致，禁止使能并请重新连接')
            data=await asyncio.to_thread(s.calibration_store.read,state);data['saved_mappings']=state['mappings']
            try:await asyncio.to_thread(s.calibration_store.write,state,data)
            except OSError as exc:
                return {'state':state,'warning':'固件已保存，但电脑备份失败：'+str(exc)}
            return {'state':state,'warning':''}
        except (ValueError,KeyError,HardwareError,OSError) as exc:raise HTTPException(422,str(exc))
