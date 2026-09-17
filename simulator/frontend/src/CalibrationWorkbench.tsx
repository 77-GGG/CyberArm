import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {HardwareState} from './types';

type Point={deg:number;us:number};
type Reading={deg:number;us:number;ticks:number;time:string;direction:string;load:string;target?:number};
type Draft={points:Point[];readings:Reading[];low:number;high:number;load:string};
const empty=():Draft=>({points:[],readings:[],low:-5,high:5,load:'空载'});
const base='hardware/calibration-workbench/';

export function CalibrationWorkbench({hardware,onState}:{hardware:HardwareState;onState:(s:HardwareState)=>void}){
 const [axis,setAxis]=useState(1),[step,setStep]=useState(0),[draft,setDraft]=useState<Draft>(empty);
 const [pulse,setPulse]=useState(1500),[lowUs,setLowUs]=useState(1400),[highUs,setHighUs]=useState(1600),[rate,setRate]=useState(50);
 const [reading,setReading]=useState(0),[target,setTarget]=useState(0),[direction,setDirection]=useState('正向接近');
 const [supported,setSupported]=useState(false),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const [owned,setOwned]=useState(false),[backupMatches,setBackupMatches]=useState(true);
 const live=useRef({owned,onState});live.current={owned,onState};
 const requestBusy=useRef(false),records=useRef<Record<string,Draft>>({});
 const enabled=hardware.capabilities?.axis_calibration===1;
 const test=hardware.test,active=Boolean(test?.active),ownActive=owned&&active&&test?.axis===axis;
 const mapping=hardware.mappings?.[axis-1];
 const locked=busy||active;
 const tick=hardware.tick_us??4.88;

 useEffect(()=>{
  let alive=true;
  if(enabled)api(base+'records').then(data=>{if(alive){records.current=data.axes;setDraft(data.axes['1']??empty());setBackupMatches(data.backup_matches||!data.saved_mappings?.length);}}).catch(e=>setError(String(e.message)));
  return()=>{alive=false;};
 },[hardware.device_id,hardware.wiring_hash,enabled]);
 useEffect(()=>{
  if(!owned)return;
  let pending=false;
  const timer=setInterval(async()=>{
   if(pending||!live.current.owned)return;pending=true;
   try{const state=await api(base+'test',{action:'renew'});live.current.onState(state);}
   catch(e){setOwned(false);setError('调试会话已结束：'+(e as Error).message);}
   finally{pending=false;}
  },300);
  return()=>{clearInterval(timer);};
 },[owned]);
 useEffect(()=>()=>{if(live.current.owned)void api(base+'test',{action:'end'}).catch(()=>{});},[]);
 useEffect(()=>{setConfirmed(false);},[draft]);
 async function run(action:()=>Promise<void>){
  if(requestBusy.current)return;requestBusy.current=true;setBusy(true);setError('');
  try{await action();}catch(e){setError((e as Error).message);}finally{requestBusy.current=false;setBusy(false);}
 }
 async function command(action:string,extra:object={}){
  const state:HardwareState=await api(base+'test',{action,axis,...extra});onState(state);
  if(action==='begin'){setOwned(true);setMessage('单路输出已开启，其他通道关闭');}
  if(action==='end'){setOwned(false);setMessage('单路输出已关闭');}
  if(state.test)setPulse(state.test.target_us);
 }
 async function saveDraft(){await api(base+'draft',{axis,data:draft});records.current[String(axis)]=draft;setMessage('测量草稿已保存到电脑');}
 function record(zero=false){
  if(!ownActive||test?.moving||!test)return;
  const deg=zero?0:reading;
  const row:Reading={deg,us:test.nominal_us,ticks:test.ticks,time:new Date().toISOString(),direction,load:draft.load,...(step===3?{target}:{})};
  setDraft(d=>({...d,readings:[...d.readings,row],points:step===3?d.points:[...d.points.filter(p=>p.deg!==deg),{deg,us:row.us}].sort((a,b)=>a.deg-b.deg)}));
  setMessage(zero?'已记录关节零位；尚未写入固件':'人工读数已记录；不代表实时反馈');
 }
 async function selectAxis(next:number){await saveDraft();setAxis(next);setDraft(records.current[String(next)]??empty());setSupported(false);setStep(0);}
 async function saveMapping(){
  await saveDraft();
  const result=await api(base+'save',{axis,points:draft.points,low_deg:draft.low,high_deg:draft.high,
   confirmed:true,device_id:hardware.device_id,wiring_hash:hardware.wiring_hash,expected_revision:mapping?.revision??0});
  onState(result.state);setBackupMatches(true);setMessage(result.warning||'固件保存成功，读回一致；下次连接自动加载');
 }
 async function exportRecords(){await saveDraft();const data=await api(base+'records');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='CyberArm-标定记录.json';a.click();URL.revokeObjectURL(url);}
 async function importRecords(file:File){
  if(file.size>500000)throw Error('导入文件过大');
  const data=JSON.parse(await file.text());
  if(data.schema_version!==1||!data.axes)throw Error('标定记录格式不正确');
  const next=data.axes[String(axis)];
  if(!next||!Array.isArray(next.points)||next.points.length>7||!Array.isArray(next.readings)||!Number.isFinite(next.low)||!Number.isFinite(next.high)||next.points.some((p:Point)=>!Number.isFinite(p.deg)||!Number.isFinite(p.us)))throw Error('当前轴草稿无效');
  setDraft(next);setMessage('仅导入当前轴草稿；请在当前设备复核后确认保存');
 }
 const validation=draft.readings.filter(r=>r.target!==undefined);
 const maxError=validation.length?Math.max(...validation.map(r=>Math.abs(r.deg-r.target!))):null;
 if(!enabled)return <div className="debug-locked"><b>单轴标定需要固件 0.3.0 或更新版本</b><span>请先编译烧录支持 axis_calibration 的固件。旧版保存值不会自动认证为实测标定。</span></div>;
 return <div className="calibration-workbench">
  <div className="calibration-toolbar"><label>调试关节<select aria-label="调试关节" value={axis} disabled={locked} onChange={e=>void run(()=>selectAxis(Number(e.target.value)))}>{['J1','J2','J3','J4','J5','G'].map((n,i)=><option key={n} value={i+1}>{n} · PWM{hardware.wiring?.axes[i].channel??i}</option>)}</select></label><b>{active?`PWM 输出中 · 通道 ${test?.axis}`:'PWM 已关闭'}</b><button disabled={!ownActive||busy} onClick={()=>void run(()=>command('hold'))}>保持当前位置</button><button className="danger" disabled={!active||busy} onClick={()=>void run(async()=>{if(owned)await command('end');else onState(await api('hardware/disarm'));})}>关闭输出</button></div>
  <div className="calibration-steps">{['1 试转与零位','2 角度采样','3 范围与保存','4 角度验证'].map((name,i)=><button key={name} className={step===i?'selected':''} onClick={()=>setStep(i)}>{name}</button>)}</div>
  {!backupMatches&&<p className="debug-error">电脑备份与设备当前标定不同。设备值用于控制；草稿不会自动覆盖设备。</p>}
  <p className="hint">{['先断开传动或支撑机构。初始脉宽是第一帧指令，软件不知道舵机当前位置。零位按机械设计参考确定。','在可用小范围测负向、零位、正向三个点。读数为相邻连杆的相对角度；误差明显时再增加到七点。','工作范围必须被测量点覆盖，缩小范围不会改变角度比例。保存前关闭输出。','使用已经保存的映射输入目标角，再填写量具读数。往返重复测量可比较方向相关偏差。'][step]}</p>
  <fieldset disabled={locked||hardware.armed}><legend>单路测试窗口</legend><div className="pulse-fields">{([['下限 μs',lowUs,setLowUs],['初始 μs',pulse,setPulse],['上限 μs',highUs,setHighUs],['变化速度 μs/s',rate,setRate]] as const).map(([label,value,set])=><label key={label}>{label}<input aria-label={label} type="number" value={value} onChange={e=>set(Number(e.target.value))}/></label>)}</div><label className="check"><input type="checkbox" checked={supported} onChange={e=>setSupported(e.target.checked)}/>已断开传动或支撑机构，确认第一帧脉宽</label><button className="solid" disabled={!supported} onClick={()=>void run(()=>command('begin',{pulse_us:pulse,low_us:lowUs,high_us:highUs,rate_us_s:rate,confirmation:'SUPPORTED'}))}>开启选中舵机</button></fieldset>
  <div className="calibration-live"><span>输出计数 <b>{ownActive?test?.ticks:'—'}</b></span><span>名义脉宽 <b>{ownActive?test?.nominal_us.toFixed(2):'—'} μs</b></span><span>{test?.moving?'正在过渡':'保持/关闭'}</span></div>
  <div className="hardware-actions">{[-5,-1,1,5].map(n=><button key={n} disabled={!ownActive||busy||test?.moving} onClick={()=>void run(()=>command('target',{pulse_us:Math.max(lowUs,Math.min(highUs,(test?.nominal_us??pulse)+n*tick))}))}>{n>0?'+':''}{n} 计数</button>)}</div>
  <p className="hint">每计数约 {tick.toFixed(3)} μs；这是按时钟参数计算的名义值，不是波形实测值。禁止自动寻找机械极限。</p>
  {step===0&&<button disabled={!ownActive||busy||test?.moving} onClick={()=>record(true)}>记录当前位置为关节 0°</button>}
  {(step===1||step===3)&&<><div className="pulse-fields"><label>人工角度读数 °<input aria-label="人工角度读数" type="number" step="0.1" value={reading} onChange={e=>setReading(Number(e.target.value))}/></label><label>接近方向<select value={direction} onChange={e=>setDirection(e.target.value)}><option>正向接近</option><option>反向接近</option></select></label><label>负载/备注<input value={draft.load} onChange={e=>setDraft(d=>({...d,load:e.target.value}))}/></label></div><button disabled={!ownActive||test?.moving||!Number.isFinite(reading)||Math.abs(reading)>180|| (step===1&&draft.points.length>=7&&!draft.points.some(p=>p.deg===reading))} onClick={()=>record()}>记录人工测量</button></>}
  {step===3&&<><div className="hardware-actions"><label>目标角度 °<input aria-label="标定试转角度" type="number" value={target} onChange={e=>setTarget(Number(e.target.value))}/></label><button disabled={!ownActive||busy||!mapping?.confirmed} onClick={()=>void run(()=>command('angle',{angle_deg:target}))}>按已保存标定试转</button></div><p>实时实测角：—（未接位置反馈）。验证记录 {validation.length} 次，最大绝对误差 {maxError===null?'—':maxError.toFixed(2)+'°'}。</p></>}
  <h3>当前轴标定点 <span>{draft.points.length}/7 · {draft.points.length>1?(draft.points.at(-1)!.us>draft.points[0].us?'脉宽增大 → 正向':'脉宽增大 → 反向'):'方向待测'}</span></h3>
  <table><thead><tr><th>实测关节角 °</th><th>名义脉宽 μs</th><th>操作</th></tr></thead><tbody>{draft.points.map((p,i)=><tr key={i}><td>{p.deg}</td><td>{p.us.toFixed(2)}</td><td><button disabled={busy} onClick={()=>setDraft(d=>({...d,points:d.points.filter((_,j)=>j!==i)}))}>移除</button></td></tr>)}</tbody></table>
  {step===2&&<><div className="pulse-fields"><label>工作负限位 °<input aria-label="工作负限位" type="number" value={draft.low} onChange={e=>setDraft(d=>({...d,low:Number(e.target.value)}))}/></label><label>工作正限位 °<input aria-label="工作正限位" type="number" value={draft.high} onChange={e=>setDraft(d=>({...d,high:Number(e.target.value)}))}/></label></div><p>设备当前版本 {mapping?.revision??0}；已确认 {mapping?.confirmed?'是':'否'}。保存后仍受模型范围限制。</p><label className="check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>这些点为当前设备人工实测，方向、零位及范围已复核</label><button className="solid" disabled={locked||!confirmed||draft.points.length<3} onClick={()=>void run(saveMapping)}>确认保存到 ESP32 并读回</button></>}
  <details><summary>设备当前标定 / 人工记录 ({draft.readings.length})</summary><pre>{JSON.stringify({mapping,readings:draft.readings},null,2)}</pre></details>
  <div className="hardware-actions"><button disabled={busy} onClick={()=>void run(saveDraft)}>保存电脑草稿</button><button disabled={busy} onClick={()=>void run(exportRecords)}>导出记录 JSON</button><label className="calibration-import">导入当前轴草稿<input type="file" accept=".json" disabled={locked} onChange={e=>{const file=e.target.files?.[0];if(file)void run(()=>importRecords(file));e.target.value='';}}/></label></div>
  {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="debug-error">{error}</p>}
 </div>;
}
