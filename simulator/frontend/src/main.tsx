import {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Play,Pause,Square,RotateCcw,Box,Move3d,Layers,Terminal,Download,Upload,Plus,Trash2,ChevronDown,ChevronUp,Target,Scan,Settings2,Hand,Route,BookOpen,X,CheckCircle2,AlertCircle,Loader2,Cable,FolderOpen,Wrench,HelpCircle,Activity,Radio,Cpu,ShieldCheck,Eye} from 'lucide-react';
import {SceneView} from './SceneView';
import {useReachability} from './useReachability';
import {useManualControl} from './useManualControl';
import {api,client,session,setSession} from './api';
import {CommandConsole} from './CommandConsole';
import {FloatingConsole} from './FloatingConsole';
import type {CommandResult} from './CommandConsole';
import type {State,Model,Step,Plan,HardwareState,ServoCalibration} from './types';
import './style.css';

const names=['底座旋转','肩部俯仰','肘部俯仰','腕部旋转','腕部俯仰','夹爪开合'];
type Mode='manual'|'auto';
type HardwareSection='connection'|'servos'|'motion'|'communication'|'vision';
const modes:Record<Mode,string>={manual:'手动控制',auto:'自动运行'};
const tcpPosition=(s:State)=>s.tcp.slice(0,3).map(row=>row[3]*1000);
const defaultCalibration=():ServoCalibration=>({min_us:1300,center_us:1500,max_us:1700,reversed:false,confirmed:false});

function App(){
 const [boot,setBoot]=useState<{model:Model;version:string}|null>(null);
 const [state,setState]=useState<State|null>(null),[connected,setConnected]=useState(false);
 const [mode,setMode]=useState<Mode>('manual'),[showPath,setShowPath]=useState(false);
 const [tab,setTab]=useState<'joint'|'cartesian'>('cartesian');
 const [q,setQ]=useState([0,0,0,0,0,0]),[target,setTarget]=useState([272.1,13.025,52.366]);
 const [direction,setDirection]=useState([0,0,1]),[constrained,setConstrained]=useState(false);
 const [plan,setPlan]=useState<Plan|null>(null),[runPlan,setRunPlan]=useState<Plan|null>(null);
 const [speed,setSpeed]=useState(.7),[linear,setLinear]=useState(false),[busy,setBusy]=useState(false);
 const [message,setMessage]=useState('正在连接本地模拟器'),[error,setError]=useState(false);
 const [dragging,setDragging]=useState(false),[trialReset,setTrialReset]=useState(0);
 const [drawer,setDrawer]=useState(''),[steps,setSteps]=useState<Step[]>([]),[loops,setLoops]=useState(1);
 const [openMenu,setOpenMenu]=useState(''),[hardwareSection,setHardwareSection]=useState<HardwareSection>('connection');
 const [points,setPoints]=useState<number[][]>([]),[workspaceLabel,setWorkspaceLabel]=useState('');
 const [view,setView]=useState('perspective'),[modelStatus,setModelStatus]=useState('正在加载模型');
 const [obstacle,setObstacle]=useState({name:'障碍物 1',center:[320,0,80],size:[40,60,100]});
 const [selectedJoint,setSelectedJoint]=useState(0);
 const [commandBusy,setCommandBusy]=useState(false);
 const [hardwareBusy,setHardwareBusy]=useState(false),[ports,setPorts]=useState<{device:string;description:string}[]>([]);
 const [selectedPort,setSelectedPort]=useState(''),[supported,setSupported]=useState(false);
 const [calibration,setCalibration]=useState<ServoCalibration[]>(Array.from({length:6},defaultCalibration));
 const upload=useRef<HTMLInputElement>(null),editVersion=useRef(0),dragRef=useRef(false),menuBar=useRef<HTMLElement>(null);
 const current=useRef({state,q,mode,showPath,tab,busy,connected});current.current={state,q,mode,showPath,tab,busy:busy||commandBusy,connected};
 const receiveState=(next:State)=>setState(old=>old&&(old.seq>next.seq||old.revision>next.revision)?old:next);
 const manual=useManualControl(state,receiveState);
 const running=Boolean(state&&['RUNNING','STOPPING'].includes(state.mode));
 const disabled=busy||commandBusy||running||!connected;
 const liveManual=mode==='manual'&&!showPath;
 const trial=useReachability({enabled:!liveManual&&tab==='cartesian'&&!disabled,target,direction:constrained?direction:undefined,dragging,seq:state?.seq??0,revision:state?.revision??0,actual:state,reset:trialReset},api);

 useEffect(()=>{
  let ws:WebSocket|undefined,alive=true;
  api('bootstrap').then(data=>{
   if(!alive)return;
   setSession(data.session);setBoot(data);setState(data.state);setQ(data.state.q_deg);setTarget(tcpPosition(data.state));setMessage('就绪');
   ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws?session=${encodeURIComponent(session)}&client=${client}`);
   ws.onopen=()=>setConnected(true);
   ws.onmessage=e=>{receiveState(JSON.parse(e.data));ws?.send('ack');};
   ws.onclose=()=>{setConnected(false);setMessage('连接已断开，请重新连接');setError(true);};
  }).catch(e=>{setMessage(e.message);setError(true);});
  return()=>{alive=false;ws?.close();};
 },[]);
 useEffect(()=>{
  if(liveManual&&!manual.busy&&manual.result?.status==='reachable'&&state){
   setQ(state.q_deg);
   if(tab==='joint')setTarget(tcpPosition(state));
  }
 },[manual.busy,manual.result,state?.seq,liveManual,tab]);
 useEffect(()=>{
  if(liveManual&&!manual.busy&&state){setQ(state.q_deg);setTarget(tcpPosition(state));}
 },[state?.seq,liveManual]);
 useEffect(()=>{
  const close=(event:PointerEvent)=>{if(!menuBar.current?.contains(event.target as Node))setOpenMenu('');};
  window.addEventListener('pointerdown',close);
  return()=>window.removeEventListener('pointerdown',close);
 },[]);

 const invalidate=()=>{editVersion.current++;setPlan(null);setRunPlan(null);setError(false);};
 const commandResult=async(result:CommandResult)=>{
  if(!result.ok)return;
  if(['help','status','joints','tcp','limits','events','device','hwstatus','hwports'].includes(result.command))return;
  const next:State=await api('state');receiveState(next);setQ(next.q_deg);setTarget(tcpPosition(next));
  invalidate();setTrialReset(v=>v+1);
  if(result.command==='plan')setPlan(result.data);
  setMessage(`命令 ${result.command} 已接受`);
 };
 const fail=(e:unknown)=>{setError(true);setMessage(e instanceof Error?e.message:String(e));setPlan(null);};
 const changeQ=(i:number,v:number)=>{
  if(disabled)return;
  const next=q.map((value,j)=>i===j?v:value);setQ(next);invalidate();
  if(liveManual)manual.submit({kind:'joint',q_deg:next,refine:true});
 };
 const changeTarget=(next:number[])=>{
  if(disabled)return;
  setTarget(next);invalidate();
  if(liveManual)manual.submit({kind:'cartesian',position_mm:next,...(constrained?{direction}:{}),refine:!dragRef.current});
 };
 const changeDirection=(next:number[],enabled=constrained)=>{
  setDirection(next);setConstrained(enabled);setPoints([]);invalidate();
  if(liveManual)manual.submit({kind:'cartesian',position_mm:target,...(enabled?{direction:next}:{}),refine:true});
 };
 const control=async(action:string)=>{
  editVersion.current++;manual.cancel();
  try{const next=await api('control',{action});receiveState(next);setPlan(null);setRunPlan(null);setTrialReset(v=>v+1);setMessage(action==='reset'?'模拟状态已重置':action==='pause'?'已请求暂停':'已停止');
   if(action==='reset'){setQ(next.q_deg);setTarget(tcpPosition(next));}
  }catch(e){fail(e);}
 };
 const transition=async(nextMode:Mode,nextPath=nextMode==='auto')=>{
  if(disabled||manual.busy)return;
  const previousMode=mode,previousPath=showPath;
  setBusy(true);setMode(nextMode);setShowPath(nextPath);setPlan(null);setRunPlan(null);manual.cancel();editVersion.current++;
  try{
   const next=await api('control',{action:'stop'});receiveState(next);
   setMode(nextMode);setShowPath(nextPath);setPlan(null);setRunPlan(null);setQ(next.q_deg);setTarget(tcpPosition(next));setTrialReset(v=>v+1);setMessage('就绪');setError(false);
   if(nextMode==='auto')setDrawer('actions');else setDrawer('');
  }catch(e){setMode(previousMode);setShowPath(previousPath);fail(e);}finally{setBusy(false);}
 };
 const takeCurrent=async()=>{
  manual.cancel();setBusy(true);invalidate();
  try{const next=await api('control',{action:'stop'});receiveState(next);setQ(next.q_deg);setTarget(tcpPosition(next));setTrialReset(v=>v+1);setMessage('已同步当前位置');}
  catch(e){fail(e);}finally{setBusy(false);}
 };
 const currentStep=():Step=>{
  if(liveManual&&state)return {kind:'joint',q_deg:state.q_deg};
  return tab==='joint'?{kind:'joint',q_deg:q}:{kind:linear?'linear':'cartesian',position_mm:target,...(!linear&&trial.result?.status==='reachable'?{q_deg:trial.result.q_deg}:{}),...(constrained?{direction}:{})};
 };
 const preview=async(items:Step[])=>{
  const version=editVersion.current;setBusy(true);setError(false);setPlan(null);setMessage('正在检查路径');
  try{const result=await api('plan',{steps:items,speed});if(version!==editVersion.current)return;
   setPlan(result);setMessage(`预览通过 · ${result.duration.toFixed(2)} 秒`);
  }catch(e){if(version===editVersion.current)fail(e);}finally{setBusy(false);}
 };
 const execute=async()=>{
  if(!plan)return;
  try{await api('execute',{plan_id:plan.plan_id});setRunPlan(plan);setPlan(null);setMessage('正在执行');}catch(e){fail(e);}
 };
 const saveTarget=()=>{setSteps(old=>[...old,currentStep()]);setDrawer('actions');invalidate();setMessage('姿态已保存到动作序列');};
 const sample=async()=>{
  if(points.length){setPoints([]);return;}
  setBusy(true);try{const result=await api('workspace',{direction:constrained?direction:null});setPoints(result.points);setWorkspaceLabel(result.label);setMessage('已显示可达采样');}catch(e){fail(e);}finally{setBusy(false);}
 };
 const exportProject=()=>{
  const blob=new Blob([JSON.stringify({schema_version:1,model_version:boot?.version,steps,loops,obstacles:state?.obstacles,speed},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='CyberArm-project.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 const importProject=async(file?:File)=>{
  if(!file)return;
  try{
   if(file.size>1000000)throw new Error('项目文件过大');
   const data=JSON.parse(await file.text()),result=await api('validate-project',data);
   const next=await api('scene',{obstacles:result.obstacles});receiveState(next);
   setSteps(result.steps);setLoops(result.loops);setSpeed(result.speed);invalidate();
   setMessage(data.model_version===boot?.version?'项目已载入':'项目已载入，模型版本不同，执行前需重新检查');
  }catch(e){fail(e);}finally{if(upload.current)upload.current.value='';}
 };
 const updateScene=async(obstacles:State['obstacles'])=>{
  try{const next=await api('scene',{obstacles});receiveState(next);manual.cancel();invalidate();setMessage('场景已更新');}catch(e){fail(e);}
 };
 const receiveHardware=(next:HardwareState)=>setState(old=>old?{...old,hardware:next}:old);
 const loadCalibration=(next:HardwareState)=>setCalibration(next.calibration.map(item=>item??defaultCalibration()));
 const refreshPorts=async()=>{
  setHardwareBusy(true);
  try{const result=await api('hardware/ports');setPorts(result.ports);if(!selectedPort&&result.ports.length)setSelectedPort(result.ports[0].device);setMessage(`找到 ${result.ports.length} 个串口`);}
  catch(e){fail(e);}finally{setHardwareBusy(false);}
 };
 const openHardware=async()=>{
  if(drawer==='hardware'){setDrawer('');return;}
  if(running)await control('stop');
  setHardwareSection('connection');setDrawer('hardware');setOpenMenu('');
  if(state?.hardware)loadCalibration(state.hardware);void refreshPorts();
 };
 const hardwareAction=async(path:string,body:unknown={})=>{
  setHardwareBusy(true);
  try{const next:HardwareState=await api(path,body);receiveHardware(next);loadCalibration(next);setError(false);return next;}
  catch(e){fail(e);return null;}finally{setHardwareBusy(false);}
 };
 const connectHardware=async()=>{
  if(!selectedPort)return;
  const next=await hardwareAction('hardware/connect',{port:selectedPort,baud:921600});
  if(next)setMessage('ESP32-S3 已连接；舵机输出仍保持关闭');
 };
 const disconnectHardware=async()=>{if(await hardwareAction('hardware/disconnect')){setSupported(false);setMessage('ESP32-S3 已断开，舵机 PWM 已释放');}};
 const disableHardwareOutput=async()=>{if(await hardwareAction('hardware/disarm'))setMessage('舵机 PWM 已释放，ESP32-S3 保持连接');};
 const saveAxis=async(index:number)=>{
  const item=calibration[index];
  const next=await hardwareAction('hardware/calibration',{axis:index+1,min_us:item.min_us,center_us:item.center_us,max_us:item.max_us,reversed:item.reversed});
  if(next)setMessage(`通道 ${index+1} 校准已保存到 ESP32-S3`);
 };
 const centerAxis=async(index:number)=>{if(await hardwareAction('hardware/center',{axis:index+1,confirmation:'SUPPORTED'}))setMessage(`通道 ${index+1} 正在输出中位；装好舵盘后请关闭输出`);};
 const toggleHardwareArm=async()=>{
  const armed=state?.hardware?.armed;
  const next=await hardwareAction(armed?'hardware/disarm':'hardware/arm',armed?{}:{confirmation:'SUPPORTED'});
  if(next)setMessage(armed?'实机跟随已关闭，PWM 已释放':'实机跟随已使能；仿真运动将同步到机械臂');
 };
 useEffect(()=>{
  const key=(e:KeyboardEvent)=>{
   if(e.key==='Escape'){void control('stop');return;}
   if((e.target as HTMLElement).matches('input,textarea,select'))return;
   const latest=current.current;
   if(latest.busy||!latest.connected||['RUNNING','STOPPING'].includes(latest.state?.mode??''))return;
   if(e.key==='['||e.key===']'){
    e.preventDefault();const limit=boot?.model.limits_deg[selectedJoint];if(!limit)return;
    const next=latest.q.map((v,i)=>i===selectedJoint?Math.max(limit[0],Math.min(limit[1],v+(e.key===']'?1:-1))):v);
    setQ(next);editVersion.current++;setPlan(null);
    if(latest.mode==='manual'&&!latest.showPath)manual.submit({kind:'joint',q_deg:next,refine:true});
   }
  };
  const blur=()=>{if(current.current.state?.mode==='RUNNING')void control('pause');};
  window.addEventListener('keydown',key);window.addEventListener('blur',blur);
  return()=>{window.removeEventListener('keydown',key);window.removeEventListener('blur',blur);};
 },[boot,selectedJoint]);

 if(!boot||!state)return <main className="loading"><div className="brandmark">C</div><h1>CyberArm Studio</h1><p>{message}</p></main>;
 const shownPlan=showPath?(running?runPlan:plan):null;
 const displayState=!liveManual&&!running&&!plan&&trial.pose?{...state,...trial.pose}:state;
 const targetPose=liveManual?state:trial.pose??state;
 const result=liveManual?manual.result:trial.result;
 const solving=liveManual?manual.busy:trial.solving;
 const good=result?.status==='reachable';
 const resultStatus=solving?'solving':result?.status??'idle';
 const deviation=Math.hypot(...target.map((v,i)=>v-targetPose.tcp[i][3]*1000));
 const canPreview=!disabled&&!manual.busy&&!dragging&&(tab==='joint'||trial.result?.status==='reachable');
 const canSave=!disabled&&!manual.busy&&!dragging&&(liveManual||tab==='joint'||trial.result?.status==='reachable');
 const statuses:Record<string,string>={READY:'就绪',RUNNING:'运行中',STOPPING:'正在停止',PAUSED:'已暂停',FAULT:'故障'};
 const statusTitle=solving?'正在更新':result?.status==='collision'?'移动受阻':result?.status==='unsolved'?'未找到有效解':result?.status==='error'?'更新失败':liveManual?'当前位置':good?'目标可达':'目标检查';
 const toggle=(name:string)=>{setDrawer(drawer===name?'':name);setOpenMenu('');};
 const chooseMode=(next:Mode)=>{setOpenMenu('');void transition(next);};
 const drawerTitles:Record<string,string>={actions:'动作序列',scene:'场景编辑',project:'项目内容',logs:'运行记录',settings:'设置',hardware:'实机调试',diagnostics:'运动学诊断',help:'帮助'};
 const closePanel=()=>{if(drawer==='hardware'&&state.hardware?.outputs_enabled&&!state.hardware.armed)void disableHardwareOutput();setDrawer('');};
 return <main>
  <header className="app-header">
   <div className="brand"><span className="brandmark">C</span><span>CyberArm <b>Studio</b></span></div>
   <nav className="menu-bar" aria-label="主菜单" ref={menuBar}>
    <div className="menu-root"><button aria-expanded={openMenu==='project'} onClick={()=>setOpenMenu(openMenu==='project'?'':'project')}><FolderOpen size={16}/>项目<ChevronDown size={13}/></button>{openMenu==='project'&&<div className="menu-popover" role="menu"><button onClick={()=>toggle('project')}><Box size={16}/>项目内容</button><button disabled={disabled||manual.busy} onClick={()=>{setOpenMenu('');upload.current?.click();}}><Upload size={16}/>导入项目</button><button onClick={()=>{setOpenMenu('');exportProject();}}><Download size={16}/>导出项目</button></div>}</div>
    <div className="menu-root"><button aria-expanded={openMenu==='mode'} onClick={()=>setOpenMenu(openMenu==='mode'?'':'mode')}><Hand size={16}/>模式<ChevronDown size={13}/></button>{openMenu==='mode'&&<div className="menu-popover" role="menu"><span className="menu-caption">操作模式</span><button className={mode==='manual'?'checked':''} disabled={disabled||manual.busy} onClick={()=>chooseMode('manual')}><Hand size={16}/>手动控制</button><button className={mode==='auto'?'checked':''} disabled={disabled||manual.busy} onClick={()=>chooseMode('auto')}><Route size={16}/>自动运行</button><span className="menu-caption">执行目标</span><div className="menu-readonly"><i className={state.hardware?.armed?'live':''}/>{state.hardware?.armed?'仿真与实机':'仅仿真'}</div></div>}</div>
    <div className="menu-root"><button aria-expanded={openMenu==='workspace'} onClick={()=>setOpenMenu(openMenu==='workspace'?'':'workspace')}><Layers size={16}/>工作区<ChevronDown size={13}/></button>{openMenu==='workspace'&&<div className="menu-popover" role="menu"><button onClick={()=>toggle('actions')}><BookOpen size={16}/>动作序列<span className="menu-badge">{steps.length}</span></button><button onClick={()=>toggle('scene')}><Layers size={16}/>场景编辑</button></div>}</div>
    <div className="menu-root"><button aria-expanded={openMenu==='debug'} onClick={()=>setOpenMenu(openMenu==='debug'?'':'debug')}><Wrench size={16}/>调试<ChevronDown size={13}/></button>{openMenu==='debug'&&<div className="menu-popover" role="menu"><button onClick={()=>void openHardware()}><Cable size={16}/>实机调试</button><button onClick={()=>toggle('diagnostics')}><Scan size={16}/>运动学诊断</button><button onClick={()=>toggle('console')}><Terminal size={16}/>命令控制台</button><button onClick={()=>toggle('logs')}><Activity size={16}/>运行记录</button></div>}</div>
    <div className="menu-root"><button aria-expanded={openMenu==='settings'} onClick={()=>setOpenMenu(openMenu==='settings'?'':'settings')}><Settings2 size={16}/>设置<ChevronDown size={13}/></button>{openMenu==='settings'&&<div className="menu-popover" role="menu"><button onClick={()=>toggle('settings')}><Settings2 size={16}/>系统设置</button><button disabled={disabled||manual.busy||state.hardware?.armed} onClick={()=>{setOpenMenu('');void control('reset');}}><RotateCcw size={16}/>重置模拟状态</button></div>}</div>
    <div className="menu-root"><button aria-expanded={openMenu==='help'} onClick={()=>setOpenMenu(openMenu==='help'?'':'help')}><HelpCircle size={16}/>帮助<ChevronDown size={13}/></button>{openMenu==='help'&&<div className="menu-popover align-right" role="menu"><button onClick={()=>toggle('help')}><HelpCircle size={16}/>使用说明与更新</button></div>}</div>
   </nav>
   <div className="header-status"><span className="mode-chip">{mode==='manual'?<Hand size={14}/>:<Route size={14}/>}<b>{modes[mode]}</b></span><div className="connection"><i className={connected?'online':''}/>{connected?'本地已连接':'连接断开'}</div><span className={'sim '+(state.hardware?.armed?'hardware-live':'')}>{state.hardware?.armed?'实机跟随':'仅仿真'}</span><button className="global-stop" title="停止 Esc" onClick={()=>void control('stop')}><Square size={14}/>停止</button></div>
  </header>
  <div className="workspace">
   <section className="scene-stage" data-model-status={modelStatus} data-path-visible={Boolean(shownPlan)} aria-label="机械臂工作区">
    <div className="scene-toolbar"><span className="scene-label">{liveManual?'当前位置':'目标预览'}<span className="model-tag">RevC</span></span>
     <div className="view-controls">{[['perspective','透视'],['top','顶'],['front','前'],['side','侧']].map(([value,label])=><button key={value} aria-pressed={view===value} className={view===value?'active':''} onClick={()=>setView(value)}>{label}</button>)}</div>
     <label className="preview-toggle"><input aria-label="显示路径预览" type="checkbox" checked={showPath} disabled={disabled||manual.busy} onChange={e=>mode==='manual'?void transition(mode,e.target.checked):setShowPath(e.target.checked)}/>路径预览</label>
    </div>
    <SceneView state={displayState} model={boot.model} plan={shownPlan} points={points} drag={tab==='cartesian'&&!disabled} target={target} onTarget={changeTarget} onDragging={value=>{dragRef.current=value;setDragging(value);}} trialStatus={resultStatus} view={view} onLoad={setModelStatus}/>
    <FloatingConsole open={drawer==='console'} onClose={()=>setDrawer('')}>
     <CommandConsole connected={connected} onStart={()=>{manual.cancel();setCommandBusy(true);}} onResult={commandResult} onFinish={()=>setCommandBusy(false)}/>
    </FloatingConsole>
    {drawer&&drawer!=='console'&&<section className={'drawer '+(drawer==='actions'?'sequence-drawer':'')+(drawer==='hardware'?' hardware-drawer':'')} role="dialog" aria-label={drawerTitles[drawer]}>
     <div className="drawer-heading"><h2>{drawerTitles[drawer]}</h2><button aria-label="关闭面板" onClick={closePanel}><X size={18}/></button></div>
     {drawer==='actions'&&<>
      <div className="action-toolbar"><button disabled={!canSave} onClick={saveTarget}><Plus size={16}/>保存当前目标</button><button disabled={disabled||manual.busy} onClick={()=>{setSteps(old=>[...old,{kind:'wait',seconds:1}]);invalidate();}}><Plus size={16}/>等待 1 秒</button><label>循环<input aria-label="循环次数" type="number" min="1" max="10" value={loops} onChange={e=>{setLoops(Math.max(1,Math.min(10,Number(e.target.value))));invalidate();}}/></label></div>
      <div className="step-list">{steps.length===0?<div className="empty"><BookOpen size={28}/><p>还没有动作</p><span>调整姿态后，保存到这里。</span></div>:steps.map((step,i)=><div className="step" key={i}><b>{String(i+1).padStart(2,'0')}</b><span>{step.kind==='wait'?`等待 ${step.seconds} 秒`:step.kind==='joint'?`关节姿态 · ${step.q_deg?.slice(0,5).map(v=>v.toFixed(1)).join(' / ')}°`:`${step.kind==='linear'?'直线':'末端'} · ${step.position_mm?.map(v=>v.toFixed(1)).join(', ')} mm`}</span><button disabled={i===0||disabled} aria-label={'上移动作'+(i+1)} onClick={()=>{setSteps(old=>{const next=[...old];[next[i-1],next[i]]=[next[i],next[i-1]];return next;});invalidate();}}><ChevronUp size={16}/></button><button disabled={disabled} aria-label={'删除动作'+(i+1)} onClick={()=>{setSteps(old=>old.filter((_,j)=>j!==i));invalidate();}}><Trash2 size={16}/></button></div>)}</div>
      <button className="solid wide-button" disabled={disabled||manual.busy||!steps.length||steps.length*loops>100} onClick={()=>{if(liveManual){setMode('auto');setShowPath(true);}void preview(Array.from({length:loops},()=>steps).flat());}}><Scan size={17}/>预览整组</button>
     </>}
     {drawer==='scene'&&<>
      <label className="field">名称<input value={obstacle.name} onChange={e=>setObstacle({...obstacle,name:e.target.value})}/></label>
      {(['center','size'] as const).map(key=><div className="field-group" key={key}><h3>{key==='center'?'位置':'尺寸'} <span>mm</span></h3><div className="xyz">{obstacle[key].map((v,i)=><label key={i}>{'XYZ'[i]}<input aria-label={(key==='center'?'障碍位置':'障碍尺寸')+'XYZ'[i]} type="number" value={v} onChange={e=>setObstacle({...obstacle,[key]:obstacle[key].map((x,j)=>i===j?Number(e.target.value):x)})}/></label>)}</div></div>)}
      <button className="solid wide-button" disabled={disabled||manual.busy} onClick={()=>void updateScene([...state.obstacles,{...obstacle,center:obstacle.center.map(v=>v/1000),size:obstacle.size.map(v=>v/1000)}])}><Plus size={16}/>添加障碍物</button>
      <div className="step-list">{state.obstacles.map((o,i)=><div className="step" key={i}><span>{o.name}</span><button aria-label={'删除障碍物'+(i+1)} disabled={disabled||manual.busy} onClick={()=>void updateScene(state.obstacles.filter((_,j)=>j!==i))}><Trash2 size={16}/></button></div>)}</div><p className="hint">障碍物按包络检查。</p>
     </>}
     {drawer==='project'&&<><p>保存场景、动作序列和执行速度。</p><div className="project-actions"><button className="solid" onClick={exportProject}><Download size={18}/>导出项目</button><button disabled={disabled||manual.busy} onClick={()=>upload.current?.click()}><Upload size={18}/>导入项目</button></div><p className="hint">导入的动作在执行前会重新检查。</p></>}
     {drawer==='logs'&&<div className="logs">{state.events.length?state.events.map((event,i)=><p key={i}><time>{event.time}</time>{event.message}</p>):<p>暂无运行记录</p>}</div>}
     {drawer==='diagnostics'&&<div className="diagnostics-panel">
      <div className="diagnostic-summary"><Scan size={20}/><div><b>运动学与工作空间</b><span>检查模型限位、逆解能力与当前工具方向可达范围。</span></div></div>
      <div className="diagnostic-cards"><div><span>模型</span><b>{boot.model.model_id}</b></div><div><span>当前求解</span><b>{solving?'计算中':good?'可达':result?.status==='collision'?'碰撞':result?.status==='unsolved'?'无解':'待检查'}</b></div><div><span>采样点</span><b>{points.length}</b></div></div>
      <button className="solid wide-button" disabled={disabled||manual.busy} onClick={()=>void sample()}>{points.length?'清除可达空间采样':'生成可达空间采样'}</button>
      {workspaceLabel&&<p className="diagnostic-result">{workspaceLabel}</p>}
      <h3>模型关节范围 <span>软件软限位</span></h3><div className="limit-list">{boot.model.limits_deg.map((limit,index)=><div key={index}><b>{index===5?'G':'J'+(index+1)}</b><span>{names[index]}</span><code>{limit[0]}° ～ {limit[1]}°</code></div>)}</div>
      <p className="hint">可达空间是模型计算结果，不代表实体机械臂已经完成机械限位、舵机中位或碰撞环境校准。</p>
     </div>}
     {drawer==='hardware'&&<div className="hardware-panel">
      <div className="hardware-summary"><div><i className={state.hardware?.connected?'online':''}/><b>{state.hardware?.connected?'ESP32-S3 已连接':'未连接控制器'}</b><span>{state.hardware?.connected?`${state.hardware.port} · 固件 ${state.hardware.firmware_version??'未知'}`:'USB CDC 串口 · 921600 baud'}</span></div><span className={state.hardware?.armed?'armed':''}>{state.hardware?.armed?'跟随已使能':state.hardware?.outputs_enabled?'PWM 输出中':'PWM 已关闭'}</span></div>
      <div className="debug-tabs" role="tablist" aria-label="实机调试步骤">{([['connection','连接与安全',ShieldCheck],['servos','回中与限位',Settings2],['motion','运动测试',Activity],['communication','通信',Cpu],['vision','视觉',Eye]] as const).map(([value,label,Icon])=><button key={value} role="tab" aria-selected={hardwareSection===value} className={hardwareSection===value?'selected':''} onClick={()=>setHardwareSection(value)}><Icon size={15}/>{label}</button>)}</div>
      {hardwareSection==='connection'&&<div className="debug-section"><h3>连接与安全 <span>步骤 1</span></h3><p className="hint">连接只完成协议握手，不会输出舵机 PWM。接线、供电和机械支撑确认后再进入回中。</p>{!state.hardware?.connected?<><div className="hardware-connect"><select aria-label="ESP32-S3 串口" value={selectedPort} onChange={e=>setSelectedPort(e.target.value)}><option value="">选择串口</option>{ports.map(port=><option key={port.device} value={port.device}>{port.device}{port.description?` · ${port.description}`:''}</option>)}</select><button disabled={hardwareBusy} onClick={()=>void refreshPorts()}>刷新</button><button className="solid" disabled={hardwareBusy||!selectedPort} onClick={()=>void connectHardware()}>连接</button></div><div className="safety-list"><span>1. 舵机电源与 ESP32-S3 共地</span><span>2. 舵机使用独立电源，不由开发板供电</span><span>3. 机械臂已支撑，工作范围内无人和障碍物</span></div></>:<><div className="device-facts"><div><span>控制器</span><b>{state.hardware.model_id}</b></div><div><span>PWM 驱动</span><b>{state.hardware.driver_ready?'PCA9685 就绪':'未就绪'}</b></div><div><span>协议</span><b>v{state.hardware.protocol_version}</b></div><div><span>输出</span><b>{state.hardware.outputs_enabled?'已开启':'已关闭'}</b></div></div><label className="check hardware-confirm"><input aria-label="确认机械臂已支撑且舵盘已对中" type="checkbox" checked={supported} onChange={e=>setSupported(e.target.checked)}/>机械臂已可靠支撑，舵盘已按中位安装，周围无人和障碍物</label><div className="hardware-actions">{state.hardware.outputs_enabled&&!state.hardware.armed&&<button className="danger" disabled={hardwareBusy} onClick={()=>void disableHardwareOutput()}>立即关闭 PWM</button>}<button disabled={hardwareBusy} onClick={()=>void disconnectHardware()}>断开控制器</button></div></>}</div>}
      {hardwareSection==='servos'&&<div className="debug-section">{!state.hardware?.connected?<div className="debug-locked"><Cable size={24}/><b>请先连接 ESP32-S3</b><span>回中和校准命令不会在离线状态下启用。</span></div>:<><h3>回中、方向与软限位 <span>步骤 2</span></h3><p className="hint">先保存保守脉宽，再逐路测试中位。负/正限位对应模型允许角度，不是舵机标称 0°/180° 的电气端点。</p><label className="check hardware-confirm"><input aria-label="确认机械臂已支撑且舵盘已对中" type="checkbox" checked={supported} onChange={e=>setSupported(e.target.checked)}/>机械臂已支撑；每次只测试一个通道，手可立即切断舵机电源</label><div className="servo-calibration">{calibration.map((item,index)=><div className="servo-row" key={index}><div className="servo-title"><b>{index===5?'G':'J'+(index+1)}</b><span>{names[index]} · {state.hardware?.calibrated[index]?'已保存':'待校准'}</span><label><input aria-label={`通道 ${index+1} 反向`} type="checkbox" checked={item.reversed} disabled={state.hardware?.outputs_enabled} onChange={e=>setCalibration(old=>old.map((v,i)=>i===index?{...v,reversed:e.target.checked}:v))}/>反向</label></div><div className="pulse-fields">{(['min_us','center_us','max_us'] as const).map(key=><label key={key}>{key==='min_us'?'负限位':key==='center_us'?'中位':'正限位'}<input aria-label={`通道 ${index+1} ${key}`} type="number" min="500" max="2500" step="5" value={item[key]} disabled={state.hardware?.outputs_enabled} onChange={e=>setCalibration(old=>old.map((v,i)=>i===index?{...v,[key]:Number(e.target.value)}:v))}/></label>)}</div><div className="servo-actions"><button disabled={hardwareBusy||state.hardware?.outputs_enabled} onClick={()=>void saveAxis(index)}>保存校准</button><button disabled={hardwareBusy||!supported||!state.hardware?.calibrated[index]||state.hardware?.armed} onClick={()=>void centerAxis(index)}>单路测试中位</button></div></div>)}</div>{state.hardware.outputs_enabled&&!state.hardware.armed&&<button className="danger wide-button" disabled={hardwareBusy} onClick={()=>void disableHardwareOutput()}>关闭当前 PWM 输出</button>}</>}</div>}
      {hardwareSection==='motion'&&<div className="debug-section">{!state.hardware?.connected?<div className="debug-locked"><Cable size={24}/><b>请先连接 ESP32-S3</b></div>:<><h3>整机联动测试 <span>步骤 3</span></h3><div className="readiness-list"><div className={state.hardware.driver_ready?'ready':''}><span>PWM 驱动</span><b>{state.hardware.driver_ready?'通过':'未就绪'}</b></div><div className={state.hardware.calibrated.every(Boolean)?'ready':''}><span>六路校准</span><b>{state.hardware.calibrated.filter(Boolean).length}/6</b></div><div className={supported?'ready':''}><span>现场确认</span><b>{supported?'已确认':'待确认'}</b></div></div><label className="check hardware-confirm"><input aria-label="确认机械臂已支撑且舵盘已对中" type="checkbox" checked={supported} onChange={e=>setSupported(e.target.checked)}/>机械臂已支撑并完成逐路中位检查，周围无人和障碍物</label><div className="hardware-actions"><button className={state.hardware.armed?'danger':'solid'} disabled={hardwareBusy||(!state.hardware.armed&&(!supported||!state.hardware.driver_ready||!state.hardware.calibrated.every(Boolean)))} onClick={()=>void toggleHardwareArm()}>{state.hardware.armed?'关闭实机跟随并释放 PWM':'使能仿真与实机跟随'}</button></div><p className="hint">使能后返回“手动控制”，先以小角度、低速度逐关节测试；确认方向和限位后再运行动作序列。</p><div className="telemetry"><h3>角度状态 <span>°</span></h3>{calibration.map((_,index)=><div key={index}><b>{index===5?'G':'J'+(index+1)}</b><span>指令 {state.hardware?.commanded_q_deg?.[index]?.toFixed(1)??'—'}</span><span>实测 {state.hardware?.measured_q_deg?.[index]?.toFixed(1)??'—'}</span></div>)}</div><div className="feedback-note"><b>角度来源</b><p>普通三线 180° 舵机不能回传真实位置。“指令角度”只表示已经发送的目标；实测角度保持为“—”，直到增加绝对编码器或可读位置的总线舵机。</p></div></>}</div>}
      {hardwareSection==='communication'&&<div className="debug-section"><h3>通信监视 <span>ESP32-S3</span></h3><div className="communication-grid"><div><Radio size={17}/><span>链路状态</span><b>{state.hardware?.connected?'在线':'离线'}</b></div><div><Cpu size={17}/><span>固件版本</span><b>{state.hardware?.firmware_version??'—'}</b></div><div><Activity size={17}/><span>最近响应</span><b>{state.hardware?.last_seen?new Date(state.hardware.last_seen*1000).toLocaleTimeString():'—'}</b></div><div><ShieldCheck size={17}/><span>反馈能力</span><b>{state.hardware?.measured_feedback?'真实角度':'仅指令角'}</b></div></div>{state.hardware?.error&&<div className="debug-error"><AlertCircle size={17}/>{state.hardware.error}</div>}<p className="hint">详细收发数据和诊断命令可在“调试 → 命令控制台”中使用 hwstatus、hwports、device 和 events 查看。</p></div>}
      {hardwareSection==='vision'&&<div className="debug-section"><div className="vision-placeholder"><Eye size={30}/><b>K230D 视觉调试</b><span>后续在这里加入设备连接、图像预览、相机内参、手眼标定、坐标转换和检测延迟。</span><em>当前版本暂未启用视觉通信。</em></div></div>}
      </div>}
     {drawer==='help'&&<div className="help-panel"><div className="diagnostic-summary"><HelpCircle size={20}/><div><b>CyberArm Studio</b><span>机械臂仿真、实机调试与运动控制工作台</span></div></div><h3>基本流程</h3><ol><li>在“调试 → 实机调试”完成连接、回中和六路校准。</li><li>在“模式 → 手动控制”小角度验证实体机械臂。</li><li>记录姿态并在“模式 → 自动运行”检查整组路径。</li><li>执行前确认实机状态、场景障碍物和停止按钮可用。</li></ol><h3>软件更新</h3><p>Windows 安装版可通过系统菜单“帮助 → 检查更新”检查新版本。</p><h3>快捷键</h3><p><b>Esc</b> 停止；选中关节后按 <b>[</b> / <b>]</b> 以 1° 微调。</p></div>}
     {drawer==='settings'&&<>
      <h3>模型</h3><p>{boot.model.model_id}</p><p data-testid="model-status">{modelStatus}</p>
      <h3>控制说明</h3><p>手动控制直接更新当前仿真姿态，也可以把姿态记录到动作序列；实机跟随使能后同步下发目标。自动运行用于整组检查、执行、暂停和停止。</p>
      <h3>关节范围</h3><p>五个关节 ±30°，夹爪 ±8°，沿用当前模型配置，尚未经实物标定。</p>
      <h3>视图与快捷键</h3><p>拖动旋转视图，右键平移，滚轮缩放。网格间距 25 mm。选中关节后按 [ / ] 微调，Esc 停止，执行中切出窗口会暂停。</p>
      {workspaceLabel&&<><h3>可达采样</h3><p>{workspaceLabel}</p></>}
      <p className="hint">实机中位、方向和脉宽范围属于硬件校准，请在“调试 → 实机调试”中设置。</p>
     </>}
    </section>}
   </section>
   <aside className="control-panel">
    <div className="panel-heading"><div><h1>{modes[mode]}</h1><span>{liveManual?(state.hardware?.armed?'实时调整仿真与实机':'实时调整仿真位置'):mode==='auto'?'编辑、检查并执行动作序列':'目标与路径'}</span></div><span className="status">{statuses[state.mode]}</span></div>
    <div className="tabs" aria-label="调整方式"><button className={tab==='cartesian'?'selected':''} disabled={disabled||manual.busy} onClick={()=>{setTab('cartesian');setTarget(tcpPosition(state));setTrialReset(v=>v+1);invalidate();}}><Move3d size={17}/>末端</button><button className={tab==='joint'?'selected':''} disabled={disabled||manual.busy} onClick={()=>{setTab('joint');setQ(state.q_deg);invalidate();}}><Settings2 size={17}/>关节</button></div>
    <div className="panel-content">
     {tab==='joint'?<div className="joint-list">{q.map((value,i)=><div className={'joint-row '+(selectedJoint===i?'focused':'')} key={i} onClick={()=>setSelectedJoint(i)}><div className="joint-label"><strong>{i===5?'G':'J'+(i+1)}</strong><label htmlFor={'joint-'+i}>{names[i]}</label><input id={'joint-'+i} aria-label={names[i]+'目标角度'} type="number" step=".5" min={boot.model.limits_deg[i][0]} max={boot.model.limits_deg[i][1]} value={Number(value.toFixed(2))} disabled={disabled} onChange={e=>changeQ(i,Number(e.target.value))}/><span>°</span></div><div className="slider-line"><button disabled={disabled} title="目标减小 1 度" onClick={()=>changeQ(i,Math.max(boot.model.limits_deg[i][0],value-1))}>−</button><input aria-label={names[i]+'滑条'} type="range" min={boot.model.limits_deg[i][0]} max={boot.model.limits_deg[i][1]} step=".1" value={value} disabled={disabled} onChange={e=>changeQ(i,Number(e.target.value))}/><button disabled={disabled} title="目标增大 1 度" onClick={()=>changeQ(i,Math.min(boot.model.limits_deg[i][1],value+1))}>+</button></div></div>)}</div>:<div className="cartesian">
      <div className="field-group"><h3>末端位置 <span>mm · 底座坐标系</span></h3><div className="xyz">{target.map((value,i)=><label key={i} className={'axis-'+i}>{'XYZ'[i]}<input aria-label={'目标'+'XYZ'[i]} type="number" step="1" value={Number(value.toFixed(2))} disabled={disabled} onChange={e=>changeTarget(target.map((v,j)=>i===j?Number(e.target.value):v))}/></label>)}</div></div>
      <div className="reachability-wrap"><div className={'reachability '+resultStatus} role="status" data-testid="reachability-status"><div className="reachability-title">{solving?<Loader2 size={18} className="spin"/>:!result||good?<CheckCircle2 size={18}/>:<AlertCircle size={18}/>}<strong>{statusTitle}</strong></div>{result&&!good&&!solving&&<p>{result.message}</p>}{!!result?.near_limits?.length&&<p>接近限位：{result.near_limits.join('、')}</p>}<div className="error-value"><span>位置误差</span><b data-testid="target-deviation">{deviation.toFixed(2)}</b><span>mm</span></div>{result?.status==='error'&&<button onClick={()=>liveManual?changeTarget(target):setTrialReset(v=>v+1)}>重新求解</button>}</div></div>
      <div className="field-group"><h3>{liveManual?'当前关节':'目标关节'} <span>°</span></h3><div className="trial-joints">{targetPose.q_deg.slice(0,5).map((v,i)=><div key={i}><span>J{i+1}</span><b data-testid={'trial-joint-'+i}>{v.toFixed(1)}°</b></div>)}</div></div>
      <details className="advanced"><summary>方向与运动选项<ChevronDown size={16}/></summary><label className="check"><input type="checkbox" checked={constrained} disabled={disabled} onChange={e=>changeDirection(direction,e.target.checked)}/>约束工具 Z 轴方向</label>{constrained&&<div className="xyz">{direction.map((v,i)=><label key={i}>{'XYZ'[i]}<input aria-label={'方向'+'XYZ'[i]} type="number" step=".1" disabled={disabled} value={v} onChange={e=>changeDirection(direction.map((value,j)=>i===j?Number(e.target.value):value))}/></label>)}</div>}{!liveManual&&<label className="check"><input type="checkbox" checked={linear} disabled={disabled} onChange={e=>{setLinear(e.target.checked);invalidate();}}/>末端直线运动 MoveL</label>}<p className="hint">五轴可约束位置和工具指向，不能保证任意完整姿态。</p></details>
     </div>}
     {tab==='joint'&&liveManual&&<div className={'joint-feedback '+(manual.result&&manual.result.status!=='reachable'?'error':'')} role="status">{manual.busy?'正在更新位置':manual.result?.message??'调整滑条即可移动机械臂'}</div>}
     <div className="current-tcp"><h3>当前 TCP <span>mm</span></h3><div>{tcpPosition(state).map((v,i)=><span key={i}><b>{'XYZ'[i]}</b>{v.toFixed(1)}</span>)}</div></div>
    </div>
    <div className="panel-actions">
     <div className="secondary-actions"><button disabled={disabled} onClick={()=>void takeCurrent()}><Target size={16}/>取当前值</button><button disabled={disabled||manual.busy} onClick={()=>{setQ([0,0,0,0,0,0]);setTab('joint');invalidate();if(liveManual)manual.submit({kind:'joint',q_deg:[0,0,0,0,0,0],refine:true});}}><RotateCcw size={16}/>参考位目标</button></div>
     {liveManual?<button className="solid wide-button" disabled={!canSave} onClick={saveTarget}><Plus size={18}/>记录当前姿态</button>:<><div className="speed"><label htmlFor="speed">执行速度</label><input id="speed" aria-label="运动速度" type="range" min="5" max="100" value={speed*100} disabled={disabled} onChange={e=>{setSpeed(Number(e.target.value)/100);invalidate();}}/><b>{Math.round(speed*100)}%</b></div><div className="primary-actions"><button disabled={!canPreview} onClick={()=>void preview([currentStep()])}><Scan size={17}/>{busy?'检查中…':'预览路径'}</button><button className="solid" disabled={!plan||disabled||plan.seq!==state.seq||plan.revision!==state.revision} onClick={execute}><Play size={17}/>执行</button></div></>}
    </div>
   </aside>
  </div>
  <footer><div className={'feedback '+(error?'error':'')}><i/>{modelStatus.includes('正在')?modelStatus:message}</div><div className="playback"><span>{state.time.toFixed(1)} / {state.duration.toFixed(1)} s</span><button disabled={state.mode!=='RUNNING'} title="暂停" onClick={()=>void control('pause')}><Pause size={17}/></button><button disabled={state.mode!=='PAUSED'||busy} title="重新规划剩余动作" onClick={async()=>{setBusy(true);try{setPlan(await api('resume',{}));setShowPath(true);setMessage('剩余动作已重新验证，点击执行继续');}catch(e){fail(e);}finally{setBusy(false);}}}><Play size={17}/></button><button title="运行记录" onClick={()=>toggle('logs')}><Terminal size={18}/></button></div></footer>
  <input ref={upload} type="file" hidden accept=".json,application/json" onChange={e=>void importProject(e.target.files?.[0])}/>
 </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
