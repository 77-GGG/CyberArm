import asyncio
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
import json
import secrets
import time
from typing import Literal
import uuid
import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .model import Robot, ROOT
from .planner import plan_job, warm_worker, workspace_job
from .reachability import reachability_job, manual_job

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Step(Strict):
    kind:Literal['joint','cartesian','linear','wait']
    q_deg:list[float]|None=Field(default=None,min_length=6,max_length=6)
    position_mm:list[float]|None=Field(default=None,min_length=3,max_length=3)
    direction:list[float]|None=Field(default=None,min_length=3,max_length=3)
    seconds:float=Field(default=1,ge=.02,le=60)
    @model_validator(mode='after')
    def required(self):
        if self.kind=='joint' and self.q_deg is None:raise ValueError('缺少关节角度')
        if self.kind in ('cartesian','linear') and self.position_mm is None:raise ValueError('缺少目标坐标')
        return self
class PlanRequest(Strict):
    steps:list[Step]=Field(min_length=1,max_length=100)
    speed:float=Field(default=.7,ge=.05,le=1)
class Obstacle(Strict):
    name:str=Field(min_length=1,max_length=64)
    center:list[float]=Field(min_length=3,max_length=3)
    size:list[float]=Field(min_length=3,max_length=3)
    @model_validator(mode='after')
    def dimensions(self):
        if any(v<=0 or v>2 for v in self.size) or any(abs(v)>2 for v in self.center):raise ValueError('场景尺寸范围非法')
        return self
class Scene(Strict):
    obstacles:list[Obstacle]=Field(default_factory=list,max_length=20)
class Execute(Strict):
    plan_id:str
class Control(Strict):
    action:Literal['pause','stop','reset']
class Pose(Strict):
    q_deg:list[float]=Field(min_length=6,max_length=6)
class Reachability(Strict):
    position_mm:list[float]=Field(min_length=3,max_length=3)
    seed_deg:list[float]=Field(min_length=6,max_length=6)
    direction:list[float]|None=Field(default=None,min_length=3,max_length=3)
    refine:bool=True
    seq:int
    revision:int
    @model_validator(mode='after')
    def nonzero_direction(self):
        if self.direction is not None and np.linalg.norm(self.direction)<1e-8:raise ValueError('工具方向不能为零')
        return self
class Project(Strict):
    schema_version:Literal[1]
    model_version:str
    steps:list[Step]=Field(max_length=100)
    loops:int=Field(default=1,ge=1,le=10)
    obstacles:list[Obstacle]=Field(default_factory=list,max_length=20)
    speed:float=Field(default=.7,ge=.05,le=1)
    @model_validator(mode='after')
    def count(self):
        if len(self.steps)*self.loops>100:raise ValueError('展开动作不能超过 100 步')
        return self

class Manual(Strict):
    kind:Literal['joint','cartesian']
    q_deg:list[float]|None=Field(default=None,min_length=6,max_length=6)
    position_mm:list[float]|None=Field(default=None,min_length=3,max_length=3)
    direction:list[float]|None=Field(default=None,min_length=3,max_length=3)
    refine:bool=True
    seq:int
    revision:int
    @model_validator(mode='after')
    def target(self):
        if self.kind=='joint' and self.q_deg is None:raise ValueError('缺少关节角度')
        if self.kind=='cartesian' and self.position_mm is None:raise ValueError('缺少目标坐标')
        if self.direction is not None and np.linalg.norm(self.direction)<1e-8:raise ValueError('工具方向不能为零')
        return self

class Controller:
    def __init__(self):
        self.r=Robot();self.q=np.zeros(6);self.mode='READY';self.seq=0;self.revision=0
        self.obstacles=[];self.plans={};self.active=None;self.t=0.;self.stop_t=0.;self.stop_duration=.1
        self.pause_requested=False;self.paused=None;self.events=[];self.clients={};self.owner=None
        self.generation=0;self.busy=False;self.last_error='';self.last_dt=.02
    def log(self,message):
        self.events.append({'time':time.strftime('%H:%M:%S'),'message':message});self.events=self.events[-60:]
    def current_segment(self):
        for segment in self.active['segments']:
            if self.t<segment['at']+segment['duration']-1e-10:return segment
        return self.active['segments'][-1]
    def evaluate(self):
        s=self.current_segment();u=self.r.curve(min(s['duration'],max(0,self.t-s['at'])),s['duration'])[0]
        self.q=np.array(s['start'])+(np.array(s['end'])-s['start'])*u
    def stop(self,pause=False):
        self.generation+=1
        self.plans.clear()
        if self.mode=='STOPPING':
            if not pause:self.pause_requested=False
            return
        if self.mode!='RUNNING':
            if not pause:self.paused=None;self.mode='READY'
            return
        self.pause_requested=pause;self.stop_t=0.;self.mode='STOPPING'
        velocities=[1.875*np.abs(np.array(s['end'])-s['start'])/s['duration'] for s in self.active['segments']]
        self.stop_duration=max(.08,float(np.max(np.max(velocities,axis=0)/(self.r.amax*.5))))
        self.log('沿已验证路径减速'+('并暂停' if pause else '停止'))
    def advance(self,dt):
        if not self.active or self.mode not in ('RUNNING','STOPPING'):return
        if self.mode=='RUNNING':self.t+=dt
        else:
            old=self.stop_t;new=min(self.stop_duration,old+dt)
            self.t+=(new-old)-(new*new-old*old)/(2*self.stop_duration);self.stop_t=new
        self.t=min(self.t,self.active['duration']);self.evaluate();self.seq+=1
        if self.t>=self.active['duration']-1e-9:
            self.q=np.array(self.active['end']);self.mode='READY';self.active=None;self.paused=None;self.log('动作完成')
        elif self.mode=='STOPPING' and self.stop_t>=self.stop_duration:
            self.paused=self.active if self.pause_requested else None
            self.mode='PAUSED' if self.pause_requested else 'READY';self.active=None;self.log('已暂停' if self.pause_requested else '已停止')
    def snapshot(self):
        matrices,tcp=self.r.transforms(self.q)
        return {'mode':self.mode,'q_deg':np.degrees(self.q).tolist(),'matrices':matrices,'tcp':tcp,
                'seq':self.seq,'revision':self.revision,'time':self.t,'duration':self.active['duration'] if self.active else 0,
                'events':self.events[-12:],'planning':self.busy,'error':self.last_error,'obstacles':self.obstacles}

c=None;pool=None;trial_busy=False;manual_busy=False;token=secrets.token_urlsafe(32)
async def ticker():
    previous=time.monotonic();accumulator=0.
    while True:
        await asyncio.sleep(.01);now=time.monotonic();dt=now-previous;previous=now
        if dt>.3:
            c.stop(True);c.log('系统时钟停顿：已冻结追赶并请求暂停');accumulator=0.;continue
        accumulator+=dt
        if c.mode=='RUNNING' and c.owner and now-c.clients.get(c.owner,0)>1.5:c.stop(True);c.log('操控端失联，自动暂停')
        while accumulator>=.02:c.advance(.02);accumulator-=.02

@asynccontextmanager
async def lifespan(app):
    global c,pool
    c=Controller();pool=ProcessPoolExecutor(max_workers=2);c.log('RevC 模拟器就绪；临时关节限制，未连接实机')
    # Every worker pays about a second of import and collision-archive
    # decompression on its first job. Both are cached for the life of the
    # process, so warming each worker now moves that cost into startup instead
    # of leaving it on the first preview. The pool starts its workers eagerly,
    # so two queued warm-ups land on two distinct processes.
    def report(future):
        if not future.cancelled() and future.exception():c.log('规划进程预热失败：'+repr(future.exception()))
    loop=asyncio.get_running_loop()
    for _ in range(2):loop.run_in_executor(pool,warm_worker).add_done_callback(report)
    task=asyncio.create_task(ticker())
    yield
    task.cancel();pool.shutdown(wait=False,cancel_futures=True)

app=FastAPI(title='CyberArm Studio',lifespan=lifespan)
@app.middleware('http')
async def session_guard(request:Request,call_next):
    if request.url.path.startswith('/api/') and request.method!='GET':
        origin=request.headers.get('origin')
        valid_origin=origin is None or origin==str(request.base_url).rstrip('/')
        if not valid_origin or request.headers.get('x-session')!=token:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':'无效本地会话'},status_code=403)
    return await call_next(request)

@app.get('/api/bootstrap')
async def bootstrap():return {'session':token,'model':c.r.data,'version':c.r.version,'state':c.snapshot()}
@app.get('/api/state')
async def state():return c.snapshot()
@app.post('/api/pose')
async def pose(body:Pose):
    q=np.radians(body.q_deg)
    if not c.r.within(q):raise HTTPException(422,'姿态超出模拟限制')
    matrices,tcp=c.r.transforms(q)
    return {'matrices':matrices,'tcp':tcp}
@app.post('/api/validate-project')
async def validate_project(body:Project):return body.model_dump(exclude_none=True)
@app.post('/api/reachability')
async def reachability(body:Reachability):
    global trial_busy
    if c.mode not in ('READY','PAUSED') or c.busy:raise HTTPException(409,'请等待当前运动或规划结束')
    if (body.seq,body.revision)!=(c.seq,c.revision):raise HTTPException(409,'执行状态或场景已改变，请重新求解')
    if trial_busy:raise HTTPException(429,'试摆求解忙，请稍后重试')
    trial_busy=True;generation=c.generation
    try:
        result=await asyncio.get_running_loop().run_in_executor(pool,reachability_job,
                    {**body.model_dump(),'obstacles':c.obstacles})
        if generation!=c.generation or (body.seq,body.revision)!=(c.seq,c.revision):
            raise HTTPException(409,'求解期间状态已改变，请重新求解')
        return {**result,'seq':body.seq,'revision':body.revision}
    except ValueError as exc:raise HTTPException(422,str(exc))
    finally:trial_busy=False
@app.post('/api/heartbeat')
async def heartbeat(request:Request):
    c.clients[request.headers.get('x-client','sdk')]=time.monotonic();return {'ok':True}

@app.post('/api/manual')
async def manual(body:Manual):
    global manual_busy
    if c.mode!='READY' or c.busy:raise HTTPException(409,'请先停止自动动作或等待路径检查完成')
    if manual_busy:raise HTTPException(429,'手动更新正在处理')
    if (body.seq,body.revision)!=(c.seq,c.revision):raise HTTPException(409,'当前位置或场景已改变')
    manual_busy=True;generation=c.generation
    try:
        result=await asyncio.get_running_loop().run_in_executor(pool,manual_job,
            {**body.model_dump(),'seed_deg':np.degrees(c.q).tolist(),'obstacles':c.obstacles})
        if c.mode!='READY' or c.busy or generation!=c.generation or (body.seq,body.revision)!=(c.seq,c.revision):
            raise HTTPException(409,'更新期间状态已改变，未应用手动目标')
        if result['status']=='reachable':
            c.q=np.radians(result['q_deg']);c.seq+=1;c.generation+=1;c.plans.clear();c.paused=None;c.last_error=''
        return {**result,'state':c.snapshot()}
    except ValueError as exc:raise HTTPException(422,str(exc))
    finally:manual_busy=False

async def make_plan(body,client):
    if c.mode not in ('READY','PAUSED'):raise HTTPException(409,'请先停止或暂停当前动作')
    if c.busy:raise HTTPException(409,'已有规划任务；可停止取消其结果')
    c.busy=True;generation=c.generation;seq=c.seq;revision=c.revision;start=c.q.copy();begin=time.monotonic()
    try:
        result=await asyncio.get_running_loop().run_in_executor(pool,plan_job,{'start':start.tolist(),'obstacles':c.obstacles,**body.model_dump(exclude_none=True)})
        if (generation,seq,revision)!=(c.generation,c.seq,c.revision):raise HTTPException(409,'规划期间状态已改变，请重新预览')
        result.update(plan_id=uuid.uuid4().hex,seq=seq,revision=revision,version=c.r.version,created=time.monotonic(),owner=client)
        c.plans={result['plan_id']:result};c.last_error='';c.log(f"预览通过：{result['checks']} 个检查区间，耗时 {time.monotonic()-begin:.2f}s")
        return result
    except ValueError as e:
        c.last_error=str(e);c.log('拒绝：'+str(e));raise HTTPException(422,str(e))
    finally:c.busy=False

@app.post('/api/plan')
async def plan(body:PlanRequest,request:Request):return await make_plan(body,request.headers.get('x-client','sdk'))
@app.post('/api/execute')
async def execute(body:Execute,request:Request):
    client=request.headers.get('x-client','sdk');p=c.plans.get(body.plan_id)
    if not p or c.mode not in ('READY','PAUSED') or (p['seq'],p['revision'],p['version'])!=(c.seq,c.revision,c.r.version) or time.monotonic()-p['created']>120 or p['owner']!=client:raise HTTPException(409,'预览已失效、来源不符或控制器忙，请重新预览')
    c.active=p;c.plans.clear();c.paused=None;c.mode='RUNNING';c.t=0.;c.owner=client;c.clients[client]=time.monotonic();c.seq+=1;c.log('开始模拟执行');return {'ok':True}
@app.post('/api/control')
async def control(body:Control):
    if body.action=='reset':
        if c.mode in ('RUNNING','STOPPING'):raise HTTPException(409,'请先停止动作')
        c.q=np.zeros(6);c.seq+=1;c.generation+=1;c.plans.clear();c.paused=None;c.mode='READY';c.log('重置模拟状态，非实物回零')
    else:c.stop(body.action=='pause')
    return c.snapshot()
@app.post('/api/resume')
async def resume(request:Request):
    if not c.paused or c.mode!='PAUSED':raise HTTPException(409,'没有待继续动作')
    remaining=[]
    for s in c.paused['segments']:
        if s['at']+s['duration']<=c.t:continue
        if np.allclose(s['start'],s['end']):remaining.append(Step(kind='wait',seconds=max(.02,s['at']+s['duration']-max(c.t,s['at']))))
        else:remaining.append(Step(kind='joint',q_deg=np.degrees(s['end']).tolist()))
    result=await make_plan(PlanRequest(steps=remaining),request.headers.get('x-client','sdk'))
    return result
@app.post('/api/scene')
async def scene(body:Scene):
    if c.mode in ('RUNNING','STOPPING'):raise HTTPException(409,'请先停止再编辑场景')
    c.obstacles=[o.model_dump() for o in body.obstacles];c.revision+=1;c.generation+=1;c.plans.clear();c.log('场景已更新，旧预览失效');return c.snapshot()
@app.post('/api/workspace')
async def workspace(body:dict):
    direction=body.get('direction')
    if direction is not None and (len(direction)!=3 or not np.isfinite(direction).all() or np.linalg.norm(direction)<1e-8):raise HTTPException(422,'方向非法')
    return await asyncio.get_running_loop().run_in_executor(pool,workspace_job,{'direction':direction})
@app.websocket('/ws')
async def websocket(ws:WebSocket):
    if ws.query_params.get('session')!=token:await ws.close(code=1008);return
    await ws.accept();client=ws.query_params.get('client','browser')
    try:
        while True:
            await ws.send_json(c.snapshot())
            try:
                await asyncio.wait_for(ws.receive_text(),timeout=.25)
                c.clients[client]=time.monotonic()
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect,RuntimeError):
        c.clients.pop(client,None)
        if c.owner==client:c.stop(True)

app.mount('/models',StaticFiles(directory=ROOT/'assets/revc'),name='models')
if (ROOT/'frontend/dist').exists():app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')
