import {useEffect,useRef,useState} from 'react';
import './calibration.css';
import {api} from './api';
import type {HardwareState,Model} from './types';
import {JointLimitsEditor} from './JointLimitsEditor';
import {ZeroReference} from './ZeroReference';
import {deviceDraft,emptyDraft,parseDraft,pointProblems,pulseAt,rangeProblems} from './calibrationWorkflow';
import type {Draft,Reading} from './calibrationWorkflow';

const base='hardware/calibration-workbench/';
const axes=['J1','J2','J3','J4','J5','G'];
const steps=['准备输出','确定零位','采集角度','限位与保存','验证角度'];
const instructions=[
 '选择关节，核对实际接线。支撑机构或断开传动后，从窄脉宽窗口开始试转。',
 '小步点动到机械设计规定的零位，用量具对齐后记录。1500 μs 只是初始指令，不自动等于关节 0°。',
 '从零位分别向两侧小步移动，用量具测相邻连杆的相对角度。至少记录负角、零位、正角三个点。',
 '设置已经实测且留有余量的工作范围。先关闭输出，再核对并保存到设备；限位变化不会缩放角度。',
 '按设备已保存的映射小角度试转，再填写量具读数。正反方向重复测量，检查回差和重复性。',
];
const rangeText=(low?:number,high?:number)=>Number.isFinite(low)&&Number.isFinite(high)?`${low!.toFixed(1)}° ～ ${high!.toFixed(1)}°`:'尚未确定';

export function CalibrationWorkbench({hardware,model:robotModel,modelLimits,onState}:{hardware:HardwareState;model:Model;modelLimits:number[][];onState:(s:HardwareState)=>void}){
 const [axis,setAxis]=useState(1),[step,setStep]=useState(0),[draft,setDraft]=useState<Draft>(emptyDraft);
 const [pulse,setPulse]=useState(1500),[lowUs,setLowUs]=useState(1400),[highUs,setHighUs]=useState(1600),[rate,setRate]=useState(50);
 const [reading,setReading]=useState<number>(NaN),[target,setTarget]=useState(0),[direction,setDirection]=useState('正向接近');
 const [supported,setSupported]=useState(false),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [message,setMessage]=useState(''),[error,setError]=useState(''),[source,setSource]=useState('新标定');
 const [owned,setOwned]=useState(false),[backupMatches,setBackupMatches]=useState(true);
 const [verification,setVerification]=useState<{target:number;revision:number;pulse:number}|null>(null);
 const live=useRef({owned,onState});live.current={owned,onState};
 const requestBusy=useRef(false),records=useRef<Record<string,Draft>>({});
 const workbench=useRef<HTMLDivElement>(null);
 const enabled=hardware.capabilities?.axis_calibration===1;
 const test=hardware.test,active=Boolean(test?.active),ownActive=owned&&active&&test?.axis===axis;
 const mapping=hardware.mappings?.[axis-1],model=modelLimits[axis-1];
 const locked=busy||active||loading;
 const tick=hardware.tick_us??4.88;
 const pointsIssues=pointProblems(draft.points),rangeIssues=rangeProblems(draft);
 const hasZero=draft.points.some(p=>p.deg===0);
 const effectiveLow=Math.max(model[0],draft.low,draft.points[0]?.deg??-Infinity);
 const effectiveHigh=Math.min(model[1],draft.high,draft.points.at(-1)?.deg??Infinity);
 const windowValid=[lowUs,highUs,pulse,rate].every(Number.isFinite)&&lowUs>=500&&highUs<=2500&&lowUs<highUs&&pulse>=lowUs&&pulse<=highUs&&rate>=5&&rate<=200;
 const canBegin=!locked&&!hardware.armed&&!hardware.outputs_enabled&&!hardware.motion_busy&&hardware.driver_ready&&supported&&windowValid;
 const settled=ownActive&&!test?.moving&&!busy;
 const sameAsDevice=Boolean(mapping?.confirmed&&mapping.points.length===draft.points.length&&mapping.points.every((p,i)=>Math.abs(p.deg-draft.points[i].deg)<.001&&Math.abs(p.us-draft.points[i].us)<.001)&&Math.abs(mapping.work_low_deg-draft.low)<.001&&Math.abs(mapping.work_high_deg-draft.high)<.001);
 const verificationPulse=mapping?.confirmed&&target>=mapping.low_deg&&target<=mapping.high_deg?pulseAt(mapping.points,target):null;
 const angleIssue=verificationPulse===null?'目标必须位于设备当前有效范围内':verificationPulse<lowUs||verificationPulse>highUs?'目标超出本次脉宽窗口：关闭输出后返回准备页调整':Math.abs(verificationPulse-(test?.pulse_us??pulse))>100?'目标跨度超过 100 μs，请先输入更近的角度，分步接近':'';
 const canRecordValidation=settled&&verification&&verification.target===target&&verification.revision===mapping?.revision&&Math.abs((test?.target_us??0)-verification.pulse)<.01;

 useEffect(()=>{
  let alive=true;
  setLoading(true);setAxis(1);setStep(0);setDraft(emptyDraft());setSupported(false);setConfirmed(false);setVerification(null);setOwned(false);setError('');records.current={};
  if(enabled)api(base+'records').then(data=>{
   if(!alive)return;
   records.current=Object.fromEntries(Object.entries(data.axes??{}).map(([key,value])=>[key,parseDraft(value)]));
   setDraft(records.current['1']??deviceDraft(data.current_mappings?.[0]));
   setSource(records.current['1']?'电脑草稿':data.current_mappings?.[0]?.confirmed?'设备已保存值':'新标定');
   setBackupMatches(data.backup_matches||!data.saved_mappings?.length);
  }).catch(e=>{if(alive)setError('读取草稿失败：'+e.message);}).finally(()=>{if(alive)setLoading(false);});
  else setLoading(false);
  return()=>{alive=false;};
 },[hardware.device_id,hardware.wiring_hash,enabled]);
 useEffect(()=>{
  if(!owned)return;
  let pending=false;
  const timer=setInterval(async()=>{
   if(pending||!live.current.owned)return;pending=true;
   try{const state=await api(base+'test',{action:'renew'});live.current.onState(state);}
   catch(e){setOwned(false);setVerification(null);setError('调试会话已结束：'+(e as Error).message);}
   finally{pending=false;}
  },300);
  return()=>clearInterval(timer);
 },[owned]);
 useEffect(()=>()=>{if(live.current.owned)void api(base+'test',{action:'end'}).catch(()=>{});},[]);
 useEffect(()=>{setConfirmed(false);},[draft]);
 useEffect(()=>{workbench.current?.scrollIntoView({block:'start'});},[step,axis]);
 async function run(action:()=>Promise<void>){
  if(requestBusy.current)return;requestBusy.current=true;setBusy(true);setError('');setMessage('');
  try{await action();}catch(e){setError((e as Error).message);}finally{requestBusy.current=false;setBusy(false);}
 }
 async function command(action:string,extra:object={}){
  setVerification(null);setReading(NaN);
  const state:HardwareState=await api(base+'test',{action,axis,...extra});onState(state);
  if(action==='begin'){setOwned(true);setMessage('单路输出已开启，请观察实体位置。');}
  if(action==='end'){setOwned(false);setSupported(false);setMessage('PWM 已关闭，机构需要外部支撑。');}
  if(state.test)setPulse(state.test.target_us);
 }
 async function endOutput(){if(owned)await command('end');else {onState(await api('hardware/disarm'));setVerification(null);}}
 async function saveDraft(){const data=parseDraft(draft);await api(base+'draft',{axis,data});records.current[String(axis)]=data;}
 function record(zero=false){
  if(!settled||!test||(!zero&&!Number.isFinite(reading))||(step===4&&!canRecordValidation))return;
  const deg=zero?0:reading;
  const row:Reading={deg,us:test.nominal_us,ticks:test.ticks,time:new Date().toISOString(),direction,load:draft.load,...(step===4?{target:verification!.target,revision:verification!.revision}:{})};
  setDraft(d=>({...d,readings:[...d.readings,row],points:step===4?d.points:[...d.points.filter(p=>p.deg!==deg),{deg,us:row.us}].sort((a,b)=>a.deg-b.deg)}));
  setReading(NaN);setMessage(zero?'已记录关节 0°。下一步测量零位两侧的角度。':'人工读数已记录，尚未自动写入设备。');
 }
 async function selectAxis(next:number){
  await saveDraft();setAxis(next);setDraft(records.current[String(next)]??deviceDraft(hardware.mappings?.[next-1]));
  setSource(records.current[String(next)]?'电脑草稿':hardware.mappings?.[next-1]?.confirmed?'设备已保存值':'新标定');
  setSupported(false);setStep(0);setPulse(1500);setLowUs(1400);setHighUs(1600);setRate(50);setVerification(null);setReading(NaN);setTarget(0);
 }
 async function saveMapping(){
  if(pointsIssues.length||rangeIssues.length)throw Error([...pointsIssues,...rangeIssues].join('；'));
  await saveDraft();
  const result=await api(base+'save',{axis,points:draft.points,low_deg:draft.low,high_deg:draft.high,
   confirmed:true,device_id:hardware.device_id,wiring_hash:hardware.wiring_hash,expected_revision:mapping?.revision??0});
  onState(result.state);setBackupMatches(!result.warning);setVerification(null);setMessage(result.warning||'固件保存成功，读回一致。下一步重新开启单轴并验证角度。');
 }
 async function exportRecords(){await saveDraft();const data=await api(base+'records');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='CyberArm-标定记录.json';a.click();URL.revokeObjectURL(url);}
 async function importRecords(file:File){
  if(file.size>500000)throw Error('导入文件过大');
  const data=JSON.parse(await file.text());
  if(data.schema_version!==1||!data.axes)throw Error('标定记录格式不正确');
  const next=parseDraft(data.axes[String(axis)]);setDraft(next);setSource('导入草稿');setVerification(null);
  setMessage('仅导入当前轴草稿；请在当前设备复核后确认保存。');
 }
 const validation=draft.readings.filter(r=>r.target!==undefined&&r.revision===mapping?.revision);
 const maxError=validation.length?Math.max(...validation.map(r=>Math.abs(r.deg-r.target!))):null;
 const stepAllowed=[true,!loading,!loading&&hasZero,!loading&&pointsIssues.length===0,!loading&&Boolean(mapping?.confirmed)];
 const nextReason=['核对接线和测试窗口后继续','记录关节零位后继续',pointsIssues.join('；'),sameAsDevice?'':'先保存并读回当前标定',''][step];
 const readyNext=step===0?!loading:step===1?hasZero:step===2?pointsIssues.length===0:step===3?sameAsDevice:false;
 const movementPanel=(step===1||step===2||step===4);
 if(!enabled)return <div className="debug-locked"><b>单轴标定需要固件 0.3.0 或更新版本</b><span>请先烧录支持单轴标定的固件。</span></div>;
 return <div className="calibration-workbench" ref={workbench}>
  <div className="calibration-toolbar">
   <label>调试关节<select aria-label="调试关节" value={axis} disabled={locked} onChange={e=>void run(()=>selectAxis(Number(e.target.value)))}>{axes.map((n,i)=><option key={n} value={i+1}>{n} · PWM{hardware.wiring?.axes[i]?.channel??i}{hardware.mappings?.[i]?.confirmed?' · 已保存':''}</option>)}</select></label>
   <span className={active?'output-on':'output-off'}>{active?`${axes[(test?.axis??1)-1]} · PWM 输出中`:'PWM 已关闭'}</span>
   <button disabled={!ownActive||busy} onClick={()=>void run(()=>command('hold'))}>暂停脉宽变化</button>
   <button className="danger" disabled={(!hardware.outputs_enabled&&!active)||busy} onClick={()=>void run(endOutput)}>关闭输出</button>
  </div>
  <nav className="calibration-steps" aria-label="单轴标定流程">{steps.map((name,i)=><button key={name} aria-current={step===i?'step':undefined} className={step===i?'selected':''} disabled={busy||!stepAllowed[i]} onClick={()=>setStep(i)}><span>{i+1}</span>{name}</button>)}</nav>
  <div className="calibration-notices" aria-live="polite">{message&&<p role="status">{message}</p>}{error&&<p role="alert" className="debug-error">{error}</p>}{loading&&<p>正在读取当前设备记录…</p>}</div>
  {!backupMatches&&<p className="debug-error">电脑备份与设备不同或备份未完成，控制始终使用设备已保存值。</p>}
  <section className="calibration-stage" aria-label={steps[step]}>
   <header><span>步骤 {step+1} / 5</span><h3>{steps[step]}</h3><p>{instructions[step]}</p></header>
   {step===0&&<>
    <div className="calibration-facts"><div><span>实际输出接线</span><b>{axes[axis-1]} → PCA9685 第 {hardware.wiring?.axes[axis-1]?.channel??'—'} 路</b></div><div><span>当前数据来源</span><b>{source} · 设备版本 {mapping?.revision??0}</b></div></div>
    <fieldset disabled={locked||hardware.armed}><legend>测试窗口 · 关闭输出后可调整</legend><div className="pulse-fields">
     {([['下限 μs',lowUs,setLowUs],['初始 μs',pulse,setPulse],['上限 μs',highUs,setHighUs],['变化速度 μs/s',rate,setRate]] as const).map(([label,value,set])=><label key={label}>{label}<input aria-label={label} type="number" value={Number.isFinite(value)?value:''} onChange={e=>{set(e.target.valueAsNumber);setSupported(false);}}/></label>)}
    </div><p>初始脉宽是第一次发给舵机的目标，不能保证首次上电无跳动。默认 1400–1600 μs 仅为窄范围起点。</p></fieldset>
    {!windowValid&&<p className="calibration-check">请填写有效窗口：500 ≤ 下限 ≤ 初始 ≤ 上限 ≤ 2500 μs，下限小于上限，速度 5–200 μs/s。</p>}
    <p className="hint">需要更大行程：关闭输出 → 每次少量扩展窗口 → 重新确认并开启。500–2500 μs 是软件允许边界，不是你的舵机安全范围。</p>
   </>}
   {(step===0||movementPanel)&&!active&&<div className="calibration-start">
    <label className="check"><input type="checkbox" checked={supported} disabled={busy||loading} onChange={e=>setSupported(e.target.checked)}/>已断开传动或支撑机构，确认第一帧脉宽</label>
    <button className="solid" disabled={!canBegin} onClick={()=>void run(async()=>{await command('begin',{pulse_us:pulse,low_us:lowUs,high_us:highUs,rate_us_s:rate,confirmation:'SUPPORTED'});if(step===0)setStep(1);})}>开启选中舵机</button>
    {hardware.armed?<p>请先关闭整机跟随。</p>:!hardware.driver_ready?<p>PWM 驱动未就绪，请检查连接与接线。</p>:null}
    {step!==0&&<p>第一帧 {pulse.toFixed(2)} μs · 窗口 {lowUs}–{highUs} μs <button onClick={()=>setStep(0)}>调整测试窗口</button></p>}
   </div>}
   {movementPanel&&<>
    <div className="calibration-live"><div><span>输出名义脉宽</span><b>{ownActive?test?.nominal_us.toFixed(2):'—'} <small>μs</small></b></div><div><span>输出计数</span><b>{ownActive?test?.ticks:'—'}</b></div><div><span>真实关节角</span><b>— <small>无反馈</small></b></div></div>
    <p className="calibration-motion-state">{ownActive?test?.moving?'脉宽正在过渡，等实体稳定后再测量':'脉宽已稳定，请观察实体是否稳定':'尚未开启当前轴输出'}</p>
    {step!==4&&<><div className="calibration-jog">{[-5,-1,1,5].map(n=><button key={n} disabled={!settled||(test!.nominal_us+n*tick)<lowUs||(test!.nominal_us+n*tick)>highUs} onClick={()=>void run(()=>command('target',{pulse_us:test!.nominal_us+n*tick}))}>{n>0?'+':''}{n} 计数</button>)}</div><p className="hint">±1 计数用于细调，±5 计数用于小步移动；每计数约 {tick.toFixed(3)} μs。到窗口边界后，返回准备页调整。</p></>}
   </>}
   {step===1&&<ZeroReference axis={axis} model={robotModel}/>}
   {step===1&&<div className="calibration-task"><p>先对照上方模型零姿态确定相邻连杆的参考关系。舵盘安装偏差由零位标定吸收，切勿把外壳朝向当作 0°。</p><button className="solid" disabled={!settled||(draft.points.length>=7&&!hasZero)} onClick={()=>record(true)}>记录当前位置为关节 0°</button><p>{hasZero?`已记录零位：${draft.points.find(p=>p.deg===0)!.us.toFixed(2)} μs`:'尚未记录零位'}</p></div>}
   {step===4&&<>
    <p className="calibration-check">使用设备版本 {mapping?.revision} · 当前有效范围 {rangeText(mapping?.low_deg,mapping?.high_deg)}{!sameAsDevice?'。草稿有改动，尚未用于控制。':''}</p>
    <div className="hardware-actions"><label>目标角度 °<input aria-label="标定试转角度" type="number" step="0.5" value={Number.isFinite(target)?target:''} onChange={e=>{setTarget(e.target.valueAsNumber);setVerification(null);setReading(NaN);}}/></label><button className="solid" disabled={!settled||!!angleIssue} onClick={()=>void run(async()=>{await command('angle',{angle_deg:target});setVerification({target,revision:mapping!.revision,pulse:verificationPulse!});})}>按已保存标定试转</button></div>
    {angleIssue&&<p className="hint">{angleIssue}</p>}
   </>}
   {(step===2||step===4)&&<div className="calibration-measure"><h3>{step===2?'填写量具实测值':'记录本次试转结果'}</h3><div className="pulse-fields"><label>人工角度读数 °<input aria-label="人工角度读数" type="number" step="0.1" placeholder="量具读数" value={Number.isFinite(reading)?reading:''} onChange={e=>setReading(e.target.valueAsNumber)}/></label><label>接近方向<select value={direction} onChange={e=>setDirection(e.target.value)}><option>正向接近</option><option>反向接近</option></select></label><label>负载/备注<input value={draft.load} onChange={e=>setDraft(d=>({...d,load:e.target.value}))}/></label></div><button disabled={!settled||!Number.isFinite(reading)||Math.abs(reading)>180||(step===4?!canRecordValidation:draft.points.length>=7&&!draft.points.some(p=>p.deg===reading))} onClick={()=>record()}>记录人工测量</button><p className="hint">{step===2?'相同角度会替换对应标定点，最多 7 点。先测近处，再逐步补测远处。':'请先发送目标并等待稳定。更改目标、暂停或关闭输出后，需重新试转才能记录误差。'}</p></div>}
   {(step===2||step===3)&&<>
    <h3>当前草稿标定点 <span>{draft.points.length}/7</span></h3>
    <table><thead><tr><th>实测关节角 °</th><th>名义脉宽 μs</th><th>操作</th></tr></thead><tbody>{draft.points.map((p,i)=><tr key={i}><td>{p.deg===0?'0（零位）':p.deg}</td><td>{p.us.toFixed(2)}</td><td><button aria-label={`移除 ${p.deg} 度标定点`} disabled={busy} onClick={()=>setDraft(d=>({...d,points:d.points.filter((_,j)=>j!==i)}))}>移除</button></td></tr>)}</tbody></table>
    {pointsIssues.length>0&&<ul className="calibration-check">{pointsIssues.map(issue=><li key={issue}>{issue}</li>)}</ul>}
   </>}
   {step===3&&<>
    <div className="pulse-fields"><label>工作下限 °<input aria-label="工作负限位" type="number" value={Number.isFinite(draft.low)?draft.low:''} onChange={e=>setDraft(d=>({...d,low:e.target.valueAsNumber}))}/></label><label>工作上限 °<input aria-label="工作正限位" type="number" value={Number.isFinite(draft.high)?draft.high:''} onChange={e=>setDraft(d=>({...d,high:e.target.valueAsNumber}))}/></label></div>
    <div className="calibration-ranges"><div><span>模型配置限位（软件参数）</span><b>{rangeText(model[0],model[1])}</b></div><div><span>实测标定覆盖</span><b>{rangeText(draft.points[0]?.deg,draft.points.at(-1)?.deg)}</b></div><div><span>本次工作限位</span><b>{rangeText(draft.low,draft.high)}</b></div><div className="effective"><span>保存后整机有效范围</span><b>{pointsIssues.length||rangeIssues.length?'请先修正标定数据':rangeText(effectiveLow,effectiveHigh)}</b></div></div>
    <p className="hint">整机有效范围取以上三者交集。模型配置限位不代表舵机物理行程；展开下方“修改模型软限位参数”即可同步调整。工作限位可在已实测覆盖内调整。仅仿真、未使能时仍使用模型范围。</p>
    {rangeIssues.map(issue=><p key={issue} className="calibration-check">{issue}</p>)}
    <div className="calibration-save"><ol><li>{active||hardware.outputs_enabled?'先点击顶部「关闭输出」':'输出已关闭'}</li><li>{pointsIssues.length||rangeIssues.length?'修正上方数据检查项':'测量点与工作范围格式检查通过'}</li><li>复核量具读数、零位和方向，再勾选确认</li></ol><label className="check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>这些点为当前设备人工实测，方向、零位及范围已复核</label><button className="solid" disabled={locked||hardware.outputs_enabled||hardware.armed||!confirmed||!!pointsIssues.length||!!rangeIssues.length} onClick={()=>void run(saveMapping)}>确认保存到 ESP32 并读回</button></div>
   </>}
   {step===4&&<div className="calibration-task"><p>设备版本 {mapping?.revision} 的验证记录 {validation.length} 次 · 最大绝对误差 {maxError===null?'—':maxError.toFixed(2)+'°'}</p>{validation.length>0&&<table><thead><tr><th>目标 °</th><th>实测 °</th><th>误差 °</th><th>接近方向</th></tr></thead><tbody>{validation.slice(-6).map((r,i)=><tr key={i}><td>{r.target}</td><td>{r.deg}</td><td>{(r.deg-r.target!).toFixed(2)}</td><td>{r.direction}</td></tr>)}</tbody></table>}<p className="hint">误差来自人工测量，软件不自动判定验收通过。验证后关闭输出，再切换下一关节。</p></div>}
   <footer className="calibration-navigation"><button disabled={step===0||busy} onClick={()=>setStep(s=>s-1)}>上一步</button><span>{step===4?'完成后关闭输出，切换下一轴':readyNext?'可以继续下一步':nextReason}</span>{step<4&&<button disabled={!readyNext||busy} onClick={()=>setStep(s=>s+1)}>下一步：{steps[step+1]}</button>}</footer>
  </section>
  <JointLimitsEditor key={axis} axis={axis} hardware={hardware} limits={model} blocked={locked} onState={onState}/>
  <details className="calibration-help"><summary>操作说明：如何找行程、改限位？</summary><ol><li>先在窄窗口确认方向和零位，再逐步向两侧测量。到窗口边界要先关闭输出，再少量扩展。</li><li>无位置或堵转反馈，不能自动寻找硬限位。观察到干涉、持续异响或不再随指令转动时立即停止，不继续顶住。</li><li>将最后确认可用的角度向内留余量，作为工作下限/上限。标称 180° 不等于装配后可用 180°。</li><li>修改限位不改变零点或角度比例。模型范围是另一层约束，可在软限位参数区保存到设备，上位机自动读取。扩大前应核对机械结构。</li></ol><p>“暂停脉宽变化”仍有 PWM；“关闭输出”释放 PWM。软件显示的稳定是指令稳定，真实角度仍需量具测量。</p></details>
  <details className="calibration-records"><summary>草稿、备份与设备数据</summary><p>草稿用于编辑，控制以设备已保存值为准。载入设备值会替换当前草稿，请先保存或导出需要保留的内容。</p><div className="hardware-actions"><button disabled={locked||!mapping?.confirmed} onClick={()=>{setDraft(deviceDraft(mapping));setSource('设备已保存值');setVerification(null);setMessage('已载入设备当前标定，可调整工作限位后重新保存。');}}>用设备值替换草稿</button><button disabled={busy||loading} onClick={()=>void run(async()=>{await saveDraft();setMessage('测量草稿已保存到电脑。');})}>保存电脑草稿</button><button disabled={busy||loading} onClick={()=>void run(exportRecords)}>导出记录 JSON</button></div><label className="calibration-import">导入当前轴草稿<input aria-label="导入当前轴草稿" type="file" accept=".json" disabled={locked} onChange={e=>{const file=e.target.files?.[0];if(file)void run(()=>importRecords(file));e.target.value='';}}/></label><details><summary>设备当前标定 / 人工记录 ({draft.readings.length})</summary><pre>{JSON.stringify({mapping,readings:draft.readings},null,2)}</pre></details></details>
 </div>;
}
