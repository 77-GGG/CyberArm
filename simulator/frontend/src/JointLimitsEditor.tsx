import {useEffect,useState} from 'react';
import {api} from './api';
import type {HardwareState} from './types';

export function JointLimitsEditor({axis,hardware,limits,blocked,onState}:{axis:number;hardware:HardwareState;limits:number[];blocked:boolean;onState:(s:HardwareState)=>void}){
 const [low,setLow]=useState(limits[0]),[high,setHigh]=useState(limits[1]);
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const revision=hardware.limits_revisions?.[axis-1]??0;
 useEffect(()=>{setLow(limits[0]);setHigh(limits[1]);setConfirmed(false);setError('');},[axis,limits[0],limits[1],revision]);
 const enabled=hardware.capabilities?.editable_limits===1;
 const valid=Number.isFinite(low)&&Number.isFinite(high)&&-180<=low&&low<0&&high>0&&high<=180;
 const locked=blocked||busy||hardware.outputs_enabled||hardware.armed||hardware.motion_busy;
 async function save(){
  setBusy(true);setError('');setMessage('');
  try{
   const result=await api('hardware/calibration-workbench/limits',{axis,low_deg:low,high_deg:high,confirmed:true,
    expected_revision:revision,device_id:hardware.device_id,wiring_hash:hardware.wiring_hash});
   onState(result.state);setConfirmed(false);
   setMessage(result.warning||'模型软限位已保存到 ESP32，读回一致；连接期间仿真和实机使用这组参数。');
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <details className="calibration-limit-editor"><summary>修改模型软限位参数 · 当前 {limits[0]}° ～ {limits[1]}°</summary>
  <p>这是可调的软件范围，不是舵机物理行程。保存后上位机自动读取设备值，实际运动还受实测工作限位约束。修改不会移动舵机。</p>
  {!enabled?<p className="calibration-check">需要烧录固件 0.4.0 或更新版本，才能在此修改并同步软限位。当前固件仅可修改标定工作范围。</p>:<>
   <fieldset disabled={locked}><legend>当前关节 · 设备参数版本 {revision}</legend><div className="pulse-fields">
    <label>模型下限 °<input aria-label="模型软限位下限" type="number" value={Number.isFinite(low)?low:''} onChange={e=>{setLow(e.target.valueAsNumber);setConfirmed(false);}}/></label>
    <label>模型上限 °<input aria-label="模型软限位上限" type="number" value={Number.isFinite(high)?high:''} onChange={e=>{setHigh(e.target.valueAsNumber);setConfirmed(false);}}/></label>
   </div><label className="check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>已核对机械结构，确认修改当前关节的模型软限位</label></fieldset>
   {!valid&&<p className="calibration-check">允许 -180° ≤ 下限 &lt; 0° &lt; 上限 ≤ 180°。这是参数边界，不是已验证机械行程。</p>}
   {hardware.outputs_enabled&&<p>请先关闭输出再保存。</p>}
   {axis===6&&<p>G 是夹爪驱动角；保存时还会检查连杆闭环是否有解，不能把舵机 180° 当作夹爪可用角。</p>}
   <button className="solid" disabled={locked||!valid||!confirmed} onClick={()=>void save()}>保存模型软限位并同步</button>
  </>}
  {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="debug-error">{error}</p>}
 </details>;
}
