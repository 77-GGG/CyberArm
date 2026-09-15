import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {TransformControls} from 'three/addons/controls/TransformControls.js';
import {Play,Pause,Square,RotateCcw,Box,Move3d,Layers,Terminal,Download,Upload,Plus,Trash2,ChevronDown,ChevronUp,Target,Scan,PanelBottom,Settings2} from 'lucide-react';
import './style.css';
import {useReachability} from './useReachability';

type Obstacle={name:string;center:number[];size:number[]};
type State={mode:string;q_deg:number[];matrices:number[][];tcp:number[][];seq:number;revision:number;time:number;duration:number;events:{time:string;message:string}[];planning:boolean;error:string;obstacles:Obstacle[]};
type Model={limits_deg:number[][];model_id:string;source_sha256:string;meshes:{bounds:number[][]}[]};
type Step={kind:'joint'|'cartesian'|'linear'|'wait';q_deg?:number[];position_mm?:number[];direction?:number[];seconds?:number};
type Plan={plan_id:string;duration:number;end:number[];path:number[][];checks:number;seq:number;revision:number};
let session='';const client=crypto.randomUUID();
async function api(path:string,body?:unknown){
 const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Session':session,'X-Client':client},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}
const names=['底座旋转','肩部俯仰','肘部俯仰','腕部旋转','腕部俯仰','夹爪联动'];
function SceneView({state,model,plan,points,drag,target,onTarget,onDragging,trialStatus,view,onLoad}:{state:State;model:Model;plan:Plan|null;points:number[][];drag:boolean;target:number[];onTarget:(p:number[])=>void;onDragging:(v:boolean)=>void;trialStatus:string;view:string;onLoad:(message:string)=>void}){
 const host=useRef<HTMLDivElement>(null);const live=useRef({state,plan,points,drag,target,onTarget,onDragging,trialStatus});live.current={state,plan,points,drag,target,onTarget,onDragging,trialStatus};
 const system=useRef<{camera:THREE.PerspectiveCamera;controls:OrbitControls}|null>(null);
 useEffect(()=>{
  const element=host.current!;const scene=new THREE.Scene();scene.background=new THREE.Color('#192736');scene.fog=new THREE.Fog('#192736',1.3,3.8);
  const camera=new THREE.PerspectiveCamera(40,element.clientWidth/element.clientHeight,.001,10);camera.up.set(0,0,1);camera.position.set(.50,-.63,.38);
  const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setSize(element.clientWidth,element.clientHeight);renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.35;element.appendChild(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(.12,0,.115);controls.enableDamping=true;controls.minDistance=.15;controls.maxDistance=1.8;system.current={camera,controls};
  scene.add(new THREE.HemisphereLight('#d4e6ff','#738295',2));const light=new THREE.DirectionalLight('#fff4df',3.1);light.position.set(.4,-.35,.85);light.castShadow=true;light.shadow.mapSize.set(2048,2048);Object.assign(light.shadow.camera,{left:-.5,right:.5,top:.5,bottom:-.5,near:.01,far:2});light.shadow.bias=-.00015;scene.add(light);
  const fill=new THREE.DirectionalLight('#8dcfff',1.5);fill.position.set(-.4,.5,.3);scene.add(fill);
  const floor=Math.min(...model.meshes.map(m=>m.bounds[0][2]))-.002;
  const ground=new THREE.Mesh(new THREE.PlaneGeometry(4,4),new THREE.MeshStandardMaterial({color:'#253747',roughness:.95}));ground.position.z=floor;ground.receiveShadow=true;scene.add(ground);
  const grid=new THREE.GridHelper(2,80,'#516779','#364959');grid.rotation.x=Math.PI/2;grid.position.z=floor+.0001;scene.add(grid);
  const baseAxes=new THREE.AxesHelper(.065);baseAxes.position.z=floor+.001;scene.add(baseAxes);
  let robot:THREE.Group|undefined,ghost:THREE.Group|undefined;let disposed=false;
  const loader=new GLTFLoader();loader.load('/models/robot.glb',g=>{
   if(disposed)return;robot=g.scene;robot.traverse(o=>{if(o instanceof THREE.Mesh){o.castShadow=true;o.receiveShadow=true;}if(typeof o.userData.frame_index==='number')o.matrixAutoUpdate=false;});scene.add(robot);
   ghost=robot.clone(true);ghost.traverse(o=>{if(o instanceof THREE.Mesh){o.material=new THREE.MeshBasicMaterial({color:'#66ecd0',transparent:true,opacity:.19,depthWrite:false});o.castShadow=false;}});scene.add(ghost);onLoad('RevC 模型已载入 · 87 个零件');
  },undefined,()=>onLoad('模型加载失败，请检查本地服务与模型文件'));
  const targetObject=new THREE.Object3D();scene.add(targetObject);const axes=new THREE.AxesHelper(.05);targetObject.add(axes);
  const gizmo=new TransformControls(camera,renderer.domElement);gizmo.setMode('translate');gizmo.setSize(.75);gizmo.attach(targetObject);scene.add(gizmo.getHelper());let dragging=false;
  gizmo.addEventListener('dragging-changed',e=>{dragging=Boolean(e.value);controls.enabled=!dragging;live.current.onDragging(dragging);if(!dragging)live.current.onTarget(targetObject.position.toArray().map(x=>x*1000));});
  gizmo.addEventListener('objectChange',()=>{if(dragging)live.current.onTarget(targetObject.position.toArray().map(x=>x*1000));});
  const tcp=new THREE.Mesh(new THREE.SphereGeometry(.003,12,12),new THREE.MeshBasicMaterial({color:'#66ecd0'}));scene.add(tcp);
  const tcpAxes=new THREE.AxesHelper(.025);scene.add(tcpAxes);
  const targetDot=new THREE.Mesh(new THREE.SphereGeometry(.004,12,12),new THREE.MeshBasicMaterial({color:'#e6b86d'}));targetObject.add(targetDot);
  const deviation=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(),new THREE.Vector3()]),new THREE.LineDashedMaterial({color:'#e6b86d',dashSize:.004,gapSize:.002}));scene.add(deviation);
  let line:THREE.Line|undefined,cloud:THREE.Points|undefined,oldPlan:Plan|null|undefined,oldPoints:number[][]|undefined,oldScene='';const obstacles=new THREE.Group();scene.add(obstacles);
  const frameMatrices=(object:THREE.Group,matrices:number[][])=>object.traverse(o=>{const index=o.userData.frame_index;if(typeof index==='number'&&index>=0){o.matrix.fromArray(matrices[index]).transpose();o.matrixWorldNeedsUpdate=true;}});
  // A ghost is updated with authoritative transforms from a separate FK endpoint.
  let ghostMatrices:number[][]|undefined;let requestId=0;
  const resize=()=>{camera.aspect=element.clientWidth/element.clientHeight;camera.setViewOffset(element.clientWidth,element.clientHeight,element.clientWidth>900?110:0,0,element.clientWidth,element.clientHeight);camera.updateProjectionMatrix();renderer.setSize(element.clientWidth,element.clientHeight);};const observer=new ResizeObserver(resize);observer.observe(element);
  let raf=0;const animate=()=>{
   if(disposed)return;raf=requestAnimationFrame(animate);const data=live.current;
   if(robot)frameMatrices(robot,data.state.matrices);
   const p=data.state.tcp;tcp.position.set(p[0][3],p[1][3],p[2][3]);
   tcpAxes.position.copy(tcp.position);tcpAxes.quaternion.setFromRotationMatrix(new THREE.Matrix4().set(...p.flat() as Parameters<THREE.Matrix4['set']>));tcpAxes.visible=data.drag;
   targetDot.visible=data.drag;targetDot.material.color.set(data.trialStatus==='reachable'?'#66ecd0':data.trialStatus==='solving'?'#e6b86d':'#ef8e87');
   gizmo.enabled=data.drag;gizmo.getHelper().visible=data.drag;axes.visible=data.drag;
   if(!dragging)targetObject.position.fromArray(data.target.map(x=>x/1000));
   deviation.visible=data.drag&&!data.plan&&tcp.position.distanceTo(targetObject.position)>.0005;
   if(deviation.visible){const positions=deviation.geometry.getAttribute('position') as THREE.BufferAttribute;positions.setXYZ(0,tcp.position.x,tcp.position.y,tcp.position.z);positions.setXYZ(1,targetObject.position.x,targetObject.position.y,targetObject.position.z);positions.needsUpdate=true;deviation.geometry.computeBoundingSphere();deviation.computeLineDistances();}
   if(data.plan!==oldPlan){oldPlan=data.plan;const id=++requestId;ghostMatrices=undefined;if(line){scene.remove(line);line.geometry.dispose();(line.material as THREE.Material).dispose();line=undefined;}
    if(data.plan){line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(data.plan.path.map(p=>new THREE.Vector3(...p as [number,number,number]))),new THREE.LineBasicMaterial({color:'#6be1c1'}));scene.add(line);api('pose',{q_deg:data.plan.end.map(x=>x*180/Math.PI)}).then(r=>{if(id===requestId)ghostMatrices=r.matrices;}).catch(()=>{});}}
   if(ghost){ghost.visible=Boolean(data.plan&&ghostMatrices);if(ghostMatrices)frameMatrices(ghost,ghostMatrices);}
   if(data.points!==oldPoints){oldPoints=data.points;if(cloud){scene.remove(cloud);cloud.geometry.dispose();(cloud.material as THREE.Material).dispose();}cloud=new THREE.Points(new THREE.BufferGeometry().setFromPoints(data.points.map(p=>new THREE.Vector3(...p as [number,number,number]))),new THREE.PointsMaterial({color:'#6adfc6',size:.0018,transparent:true,opacity:.25,depthWrite:false}));scene.add(cloud);}
   const sceneKey=JSON.stringify(data.state.obstacles);if(sceneKey!==oldScene){oldScene=sceneKey;for(const child of [...obstacles.children]){obstacles.remove(child);if(child instanceof THREE.Mesh){child.geometry.dispose();child.material.dispose();}}for(const o of data.state.obstacles){const mesh=new THREE.Mesh(new THREE.BoxGeometry(...o.size as [number,number,number]),new THREE.MeshStandardMaterial({color:'#e9ae64',transparent:true,opacity:.6}));mesh.position.fromArray(o.center);mesh.castShadow=true;obstacles.add(mesh);}}
   controls.update();renderer.render(scene,camera);
  };animate();
  return()=>{disposed=true;cancelAnimationFrame(raf);observer.disconnect();gizmo.dispose();controls.dispose();scene.traverse(o=>{if(o instanceof THREE.Mesh||o instanceof THREE.Line||o instanceof THREE.Points){o.geometry.dispose();const materials=Array.isArray(o.material)?o.material:[o.material];materials.forEach(m=>m.dispose());}});renderer.dispose();element.removeChild(renderer.domElement);};
 },[]);
 useEffect(()=>{const s=system.current;if(!s)return;const positions:Record<string,number[]>={perspective:[.50,-.63,.38],top:[.12,-.001,.8],front:[.12,-.8,.13],side:[.9,0,.13]};s.camera.position.fromArray(positions[view]||positions.perspective);s.controls.target.set(.12,0,.115);},[view]);
 return <div className="viewport" ref={host}/>;
}

function App(){
 const [boot,setBoot]=useState<{model:Model;version:string}|null>(null),[state,setState]=useState<State|null>(null),[connected,setConnected]=useState(false);
 const [q,setQ]=useState([0,0,0,0,0,0]),[target,setTarget]=useState([272.1,13.025,52.366]),[direction,setDirection]=useState([0,0,1]),[constrained,setConstrained]=useState(false);
 const [tab,setTab]=useState('cartesian'),[plan,setPlan]=useState<Plan|null>(null),[speed,setSpeed]=useState(.7),[linear,setLinear]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('正在连接本地模拟器…'),[error,setError]=useState(false);
 const [dragging,setDragging]=useState(false),[trialReset,setTrialReset]=useState(0);
 const running=Boolean(state&&['RUNNING','STOPPING'].includes(state.mode)),disabled=busy||running||!connected;
 const trial=useReachability({enabled:tab==='cartesian'&&!disabled,target,direction:constrained?direction:undefined,dragging,seq:state?.seq??0,revision:state?.revision??0,actual:state,reset:trialReset},api);
 const editVersion=useRef(0);
 const [drawer,setDrawer]=useState(''),[steps,setSteps]=useState<Step[]>([]),[loops,setLoops]=useState(1),[points,setPoints]=useState<number[][]>([]),[workspaceLabel,setWorkspaceLabel]=useState(''),[view,setView]=useState('perspective'),[modelStatus,setModelStatus]=useState('正在加载 RevC 模型…');
 const [obstacle,setObstacle]=useState({name:'障碍物 1',center:[320,0,80],size:[40,60,100]});
 const upload=useRef<HTMLInputElement>(null);const latest=useRef({state,q});latest.current={state,q};const [selectedJoint,setSelectedJoint]=useState(0);
 useEffect(()=>{let ws:WebSocket|undefined;let alive=true;api('bootstrap').then(data=>{if(!alive)return;session=data.session;setBoot(data);setState(data.state);setQ(data.state.q_deg);setTarget(data.state.tcp.slice(0,3).map((row:number[])=>row[3]*1000));setMessage('就绪 · 拖动末端坐标轴，实时检查目标');
  ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws?session=${encodeURIComponent(session)}&client=${client}`);ws.onopen=()=>setConnected(true);ws.onmessage=e=>{const value=JSON.parse(e.data);setState(value);ws?.send('ack');};ws.onclose=()=>{setConnected(false);setMessage('连接已断开，请刷新页面重新连接');setError(true);};
 }).catch(e=>{setMessage(e.message);setError(true);});return()=>{alive=false;ws?.close();};},[]);
 const fail=(e:unknown)=>{setError(true);setMessage(e instanceof Error?e.message:String(e));setPlan(null);};
 const invalidate=()=>{editVersion.current++;setPlan(null);setError(false);setMessage('目标已修改 · 试摆后可检查路径');};
 const currentStep=():Step=>tab==='joint'?{kind:'joint',q_deg:q}:{kind:linear?'linear':'cartesian',position_mm:target,...(!linear&&trial.result?.status==='reachable'?{q_deg:trial.result.q_deg}:{}),...(constrained?{direction}: {})};
 const preview=async(items:Step[])=>{const version=editVersion.current;setBusy(true);setError(false);setPlan(null);setMessage('正在求解并检查整条路径…');try{const result=await api('plan',{steps:items,speed});if(version!==editVersion.current){setMessage('目标在规划期间已改变，请重新预览');return;}setPlan(result);setMessage(`预览通过 · ${result.duration.toFixed(2)} 秒 · ${result.checks} 个检查区间`);}catch(e){fail(e);}finally{setBusy(false);}};
 const control=async(action:string)=>{try{await api('control',{action});setPlan(null);}catch(e){fail(e);}};
 const execute=async()=>{if(!plan)return;try{await api('execute',{plan_id:plan.plan_id});setPlan(null);setMessage('正在按已验证轨迹运行');}catch(e){fail(e);}};
 const changeQ=(i:number,v:number)=>{setQ(old=>old.map((x,j)=>i===j?v:x));invalidate();};
 useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){void control('stop');return;}if((e.target as HTMLElement).matches('input,textarea,select'))return;if(e.key==='['||e.key===']'){e.preventDefault();const delta=e.key===']'?1:-1;const limit=boot?.model.limits_deg[selectedJoint];if(limit)changeQ(selectedJoint,Math.max(limit[0],Math.min(limit[1],latest.current.q[selectedJoint]+delta)));}};window.addEventListener('keydown',key);const blur=()=>{if(latest.current.state?.mode==='RUNNING')void control('pause');};window.addEventListener('blur',blur);return()=>{window.removeEventListener('keydown',key);window.removeEventListener('blur',blur);};},[boot,selectedJoint]);
 const sample=async()=>{if(points.length){setPoints([]);return;}setBusy(true);try{const r=await api('workspace',{direction:constrained?direction:null});setPoints(r.points);setWorkspaceLabel(r.label);}catch(e){fail(e);}finally{setBusy(false);}};
 const exportProject=()=>{const blob=new Blob([JSON.stringify({schema_version:1,model_version:boot?.version,steps,loops,obstacles:state?.obstacles,speed},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='CyberArm-project.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 const importProject=async(file?:File)=>{if(!file)return;try{if(file.size>1000000)throw new Error('项目文件过大');const data=JSON.parse(await file.text());const r=await api('validate-project',data);await api('scene',{obstacles:r.obstacles});setSteps(r.steps);setLoops(r.loops);setSpeed(r.speed);invalidate();setMessage(data.model_version===boot?.version?'项目已载入，执行前需重新预览':'模型版本不同，项目已载入但所有动作必须重新验证');}catch(e){fail(e);}finally{if(upload.current)upload.current.value='';}};
 if(!boot||!state)return <main className="loading"><div className="brandmark">C</div><h1>CyberArm Studio</h1><p>{message}</p><small>本地机械臂模拟工作台</small></main>;
 const displayState=tab==='cartesian'&&!running&&!plan&&trial.pose?{...state,...trial.pose}:state;
 const trialDisplay=trial.pose??state;
 const deviationMM=Math.hypot(...target.map((v,i)=>v-trialDisplay.tcp[i][3]*1000));
 const trialStatus=trial.solving?'solving':trial.result?.status??'idle';
 const statuses:Record<string,string>={READY:'就绪',RUNNING:'运行中',STOPPING:'减速停止',PAUSED:'已暂停',FAULT:'故障'};
 const changeTarget=(p:number[])=>{setTarget(p);invalidate();};
 const toggle=(value:string)=>setDrawer(drawer===value?'':value);
 return <main>
  <SceneView state={displayState} model={boot.model} plan={plan} points={points} drag={tab==='cartesian'&&!disabled} target={target} onTarget={changeTarget} onDragging={setDragging} trialStatus={trialStatus} view={view} onLoad={setModelStatus}/>
  <header><div className="brand"><span className="brandmark">C</span><div>CyberArm <b>Studio</b><small>ROBOT MOTION WORKSPACE</small></div><span className="version">REV C</span></div><nav><button onClick={()=>toggle('project')}><Box size={15}/>项目</button><button onClick={()=>toggle('scene')}><Layers size={15}/>场景</button><button onClick={sample} disabled={busy}><Scan size={15}/>可达采样</button><button onClick={()=>toggle('settings')}><Settings2 size={15}/>设置</button></nav><div className="connection"><i className={connected?'online':''}/>{connected?'本地已连接':'连接断开'}<span className="sim">模拟模式</span></div></header>
  <div className="scene-title"><span>CYBERARM / REV C · TCP</span><h1>末端交互工作台</h1><p>{running?'正在执行已验证路径':plan?'路径预览 · 实体为起点，半透明为终点':tab==='cartesian'?'实时试摆 · 拖动末端坐标轴，关节自动联动':'关节目标编辑'}</p></div>
  <div className="view-controls"><button className={view==='perspective'?'active':''} onClick={()=>setView('perspective')}>透视</button><button onClick={()=>setView('top')}>顶</button><button onClick={()=>setView('front')}>前</button><button onClick={()=>setView('side')}>侧</button><div className="axis-legend"><b>X</b><b>Y</b><b>Z</b></div></div>
  <div className="scene-caption"><span className="mint-dot"/> {modelStatus}<small>网格 25 mm · 鼠标旋转 / 右键平移 / 滚轮缩放</small>{points.length>0&&<small className="workspace-note">{workspaceLabel}</small>}</div>
  <aside className="control-panel"><div className="panel-heading"><span><i className="mint-dot"/> 手动控制</span><span className="status">{statuses[state.mode]}</span></div><div className="tabs"><button className={tab==='joint'?'selected':''} onClick={()=>{setTab('joint');invalidate();}}><Settings2 size={15}/>关节</button><button className={tab==='cartesian'?'selected':''} onClick={()=>{setTab('cartesian');invalidate();}}><Move3d size={15}/>末端</button></div>
  {tab==='joint'?<div className="joint-list">{q.map((value,i)=><div className={`joint-row ${selectedJoint===i?'focused':''}`} key={i} onClick={()=>setSelectedJoint(i)}><div className="joint-label"><strong>{i===5?'G':'J'+(i+1)}</strong><span>{names[i]}</span><input aria-label={names[i]+'目标角度'} type="number" step=".5" min={boot.model.limits_deg[i][0]} max={boot.model.limits_deg[i][1]} value={Number(value.toFixed(2))} disabled={disabled} onChange={e=>changeQ(i,Number(e.target.value))}/><em>°</em></div><div className="slider-line"><button disabled={disabled} title="目标减小 1 度" onClick={()=>changeQ(i,Math.max(boot.model.limits_deg[i][0],value-1))}>−</button><input aria-label={names[i]+'滑条'} type="range" min={boot.model.limits_deg[i][0]} max={boot.model.limits_deg[i][1]} step=".1" value={value} disabled={disabled} onChange={e=>changeQ(i,Number(e.target.value))}/><button disabled={disabled} title="目标增大 1 度" onClick={()=>changeQ(i,Math.min(boot.model.limits_deg[i][1],value+1))}>+</button><small>{state.q_deg[i].toFixed(1)}°</small></div></div>)}</div>:<div className="cartesian">
   <p>沿 X / Y / Z 箭头或平面手柄拖动，也可输入坐标。参考系：底座。</p>
   <div className="xyz">{target.map((v,i)=><label key={i}>{'XYZ'[i]}<input aria-label={'目标'+'XYZ'[i]} type="number" step="1" value={Number(v.toFixed(2))} disabled={disabled} onChange={e=>changeTarget(target.map((x,j)=>j===i?Number(e.target.value):x))}/><small>mm</small></label>)}</div>
   <div className={'reachability '+trialStatus} role="status" aria-live="polite" data-testid="reachability-status">
    <strong>{running?'执行中':busy?'正在检查路径':trial.solving?'求解中…':trial.result?.status==='reachable'?'目标可达':trial.result?.status==='collision'?'此姿态存在干涉':trial.result?.status==='unsolved'?'未找到有效解':trial.result?.status==='error'?'求解暂不可用':'等待求解'}</strong>
    <span>{plan?'路径预览已通过 · 场景显示执行起点和目标':trial.result?.message??'拖动后自动检查末端目标'}</span>
    {!!trial.result?.near_limits?.length&&<span className="warning">接近限位：{trial.result?.near_limits?.join('、')}</span>}
    <span>试摆末端与目标距离：<b data-testid="target-deviation">{deviationMM.toFixed(2)}</b> mm{trial.result?.error&&constrained?` · 方向误差 ${trial.result.error.direction_deg.toFixed(2)}°`:''}</span>
    {trial.result?.status==='error'&&<button onClick={()=>setTrialReset(v=>v+1)}>重新求解</button>}
   </div>
   <div className="trial-joints" aria-label="试摆关节角度">{trialDisplay.q_deg.slice(0,5).map((v,i)=><span key={i}>J{i+1}<b data-testid={'trial-joint-'+i}>{v.toFixed(1)}°</b></span>)}</div>
   <label className="check"><input type="checkbox" disabled={disabled} checked={constrained} onChange={e=>{setConstrained(e.target.checked);setPoints([]);invalidate();}}/>约束工具 Z 轴方向</label>
   {constrained&&<div className="xyz">{direction.map((v,i)=><label key={i}>{'XYZ'[i]}<input aria-label={'方向'+'XYZ'[i]} type="number" step=".1" value={v} disabled={disabled} onChange={e=>{setDirection(direction.map((x,j)=>j===i?Number(e.target.value):x));invalidate();}}/></label>)}</div>}
   <label className="check"><input type="checkbox" disabled={disabled} checked={linear} onChange={e=>{setLinear(e.target.checked);invalidate();}}/>路径使用末端直线运动 MoveL</label>
   <p className="hint">五轴支持位置和工具方向约束。试摆只检查目标姿态，执行前仍需检查整条路径。</p>
  </div>}
  <div className="tcp"><span>{displayState===state?'执行 TCP':'试摆 TCP'}</span>{displayState.tcp.slice(0,3).map((row,i)=><div key={i}><b>{'XYZ'[i]}</b>{(row[3]*1000).toFixed(1)}<small>mm</small></div>)}</div>
  <div className="speed"><span>运动速度</span><input aria-label="运动速度" type="range" min="5" max="100" value={speed*100} disabled={disabled} onChange={e=>{setSpeed(Number(e.target.value)/100);invalidate();}}/><b>{Math.round(speed*100)}%</b></div><div className="secondary-actions"><button disabled={disabled} onClick={()=>{setQ(state.q_deg);setTarget(state.tcp.slice(0,3).map(r=>r[3]*1000));setTrialReset(v=>v+1);invalidate();}}><Target size={14}/>取当前值</button><button disabled={disabled} onClick={()=>{setQ([0,0,0,0,0,0]);setTab('joint');invalidate();}}><RotateCcw size={14}/>参考位目标</button></div>
  <div className="primary-actions"><button disabled={disabled||dragging||(tab==='cartesian'&&trial.result?.status!=='reachable')} onClick={()=>preview([currentStep()])}><Scan size={16}/>{busy?'检查中…':'预览路径'}</button><button className="primary" disabled={!plan||disabled||plan.seq!==state.seq||plan.revision!==state.revision} onClick={execute}><Play size={15}/>执行</button></div><p className="limit-note">临时模型限位 · 已启用路径与干涉检查</p></aside>
  {drawer&&<section className={'drawer '+(drawer==='actions'?'wide':'')}><div className="drawer-heading"><h2>{{actions:'动作编排',scene:'场景编辑',project:'项目文件',logs:'运行记录',settings:'模拟设置'}[drawer]}</h2><button onClick={()=>setDrawer('')}><ChevronDown size={18}/></button></div>
   {drawer==='actions'&&<><div className="action-toolbar"><button disabled={disabled||dragging||(tab==='cartesian'&&trial.result?.status!=='reachable')} onClick={()=>{setSteps([...steps,currentStep()]);invalidate();}}><Plus size={14}/>保存当前目标</button><button disabled={running} onClick={()=>{setSteps([...steps,{kind:'wait',seconds:1}]);invalidate();}}>＋ 等待 1 秒</button><label>循环<input aria-label="循环次数" type="number" min="1" max="10" value={loops} onChange={e=>{setLoops(Math.max(1,Math.min(10,Number(e.target.value))));invalidate();}}/></label><button disabled={disabled||steps.length===0||steps.length*loops>100} onClick={()=>preview(Array.from({length:loops},()=>steps).flat())}><Scan size={14}/>预览整组</button></div><div className="step-list">{steps.length===0?<p className="empty">保存姿态，再加入夹爪动作与等待，组成你的第一段动作。</p>:steps.map((s,i)=><div className="step" key={i}><b>{String(i+1).padStart(2,'0')}</b><span>{s.kind==='wait'?`等待 ${s.seconds} 秒`:s.kind==='joint'?`关节 → ${s.q_deg?.map(x=>x.toFixed(1)).join(' / ')}°`:`${s.kind==='linear'?'直线':'末端'} → ${s.position_mm?.map(x=>x.toFixed(1)).join(', ')} mm`}</span><button aria-label={'上移动作'+(i+1)} disabled={i===0||running} onClick={()=>setSteps(old=>{const next=[...old];[next[i-1],next[i]]=[next[i],next[i-1]];invalidate();return next;})}><ChevronUp size={14}/></button><button aria-label={'删除动作'+(i+1)} disabled={running} onClick={()=>{setSteps(steps.filter((_,j)=>j!==i));invalidate();}}><Trash2 size={14}/></button></div>)}</div></>}
   {drawer==='scene'&&<><p className="hint">尺寸以 mm 输入。障碍物采用保守包络检查。</p><label className="field">名称<input value={obstacle.name} onChange={e=>setObstacle({...obstacle,name:e.target.value})}/></label>{(['center','size'] as const).map(key=><div className="xyz" key={key}>{obstacle[key].map((v,i)=><label key={i}>{key==='center'?'位置':'尺寸'} {'XYZ'[i]}<input type="number" value={v} onChange={e=>setObstacle({...obstacle,[key]:obstacle[key].map((x,j)=>i===j?Number(e.target.value):x)})}/></label>)}</div>)}<button disabled={running} onClick={async()=>{try{await api('scene',{obstacles:[...state.obstacles,{...obstacle,center:obstacle.center.map(x=>x/1000),size:obstacle.size.map(x=>x/1000)}]});invalidate();}catch(e){fail(e);}}}><Plus size={14}/>添加障碍物</button><div className="step-list">{state.obstacles.map((o,i)=><div className="step" key={i}><span>{o.name}</span><button disabled={running} onClick={async()=>{try{await api('scene',{obstacles:state.obstacles.filter((_,j)=>j!==i)});invalidate();}catch(e){fail(e);}}}><Trash2 size={14}/></button></div>)}</div></>}
   {drawer==='project'&&<><p>场景、动作与速度保存到本地 JSON 文件。</p><div className="action-toolbar"><button onClick={exportProject}><Download size={15}/>导出项目</button><button disabled={running} onClick={()=>upload.current?.click()}><Upload size={15}/>导入项目</button></div><p className="hint">重新打开的动作必须预览检查后才能执行。</p></>}
   {drawer==='logs'&&<div className="logs">{state.events.map((e,i)=><p key={i}><time>{e.time}</time>{e.message}</p>)}</div>}
   {drawer==='settings'&&<><p>模型：{boot.model.model_id}</p><p className="hint">五个关节 ±30°，夹爪联动 ±8°。范围来自模型预览配置，尚未经实物标定。仅放行明确的装配接触和齿轮啮合；其余部件检测表面干涉。软件验证不代表实物标定。</p><p className="hint">选中关节后按 [ / ] 调整目标；Esc 停止。窗口失焦会暂停执行。</p><button disabled={running||busy} onClick={()=>control('reset')}><RotateCcw size={15}/>重置模拟状态</button></>}
  </section>}
  <footer><button className={drawer==='actions'?'active':''} onClick={()=>toggle('actions')}><PanelBottom size={17}/>动作序列<span className="badge">{steps.length}</span></button><div className={'feedback '+(error?'error':'')}><span className="mint-dot"/>{message}</div><div className="playback"><span>{state.time.toFixed(1)} / {state.duration.toFixed(1)} s</span><button disabled={state.mode!=='RUNNING'} title="暂停" onClick={()=>control('pause')}><Pause size={16}/></button><button disabled={state.mode!=='PAUSED'||busy} title="重新规划剩余动作" onClick={async()=>{setBusy(true);try{setPlan(await api('resume',{}));setMessage('剩余动作已重新验证，点击执行继续');}catch(e){fail(e);}finally{setBusy(false);}}}><Play size={16}/></button><button className="stop" title="停止 Esc" onClick={()=>control('stop')}><Square size={15}/>停止</button><button title="运行记录" onClick={()=>toggle('logs')}><Terminal size={17}/></button></div></footer>
  <input ref={upload} type="file" hidden accept=".json,application/json" onChange={e=>void importProject(e.target.files?.[0])}/>
 </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
