import {useEffect,useState} from 'react';
import {api} from './api';
import {SceneView} from './SceneView';
import type {Model,State} from './types';

type Reference={zero:{matrices:number[][];tcp:number[][]};positive:{matrices:number[][];tcp:number[][]};origin:number[];direction:number[];model_id:string};
const descriptions=[
 'J1 底座回转：上部转台相对固定底座的 CAD 装配朝向为 0°。以固定底座上的装配特征作参考。',
 'J2 肩俯仰：大臂相对底座转台的 CAD 装配姿态为 0°，不默认是大臂竖直或水平。',
 'J3 肘俯仰：小臂相对大臂的 CAD 装配夹角为 0°，不默认是两臂伸直。',
 'J4 腕旋转：腕部相对小臂的 CAD 装配朝向为 0°，用腕部安装面方向作参考。',
 'J5 腕俯仰：夹爪安装座相对腕部的 CAD 装配姿态为 0°，不默认是夹爪水平。',
 'G 夹爪：CAD 中两侧齿轮与连杆的初始装配状态为驱动角 0°，不等于完全闭合或开口 0 mm。',
];
export function ZeroReference({axis,model}:{axis:number;model:Model}){
 const [data,setData]=useState<Reference|null>(null),[positive,setPositive]=useState(false),[error,setError]=useState(''),[view,setView]=useState('perspective'),[sceneStatus,setSceneStatus]=useState('');
 useEffect(()=>{let alive=true;setData(null);setPositive(false);setError('');api('hardware/calibration-workbench/reference?axis='+axis).then(r=>{if(alive)setData(r);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[axis]);
 const pose=data&&(positive?data.positive:data.zero);
 const state=pose?{...pose,q_deg:Array.from({length:6},(_,i)=>positive&&i===axis-1?5:0),mode:'REFERENCE',seq:0,revision:0,time:0,duration:0,events:[],planning:false,error:'',obstacles:[],hardware:null} as State:null;
 return <div className="zero-reference"><h3>模型零位与正转方向 <span>仅查看，不发送运动指令</span></h3><p>{descriptions[axis-1]}</p>
  <div className="zero-reference-controls"><button aria-pressed={!positive} className={!positive?'selected':''} onClick={()=>setPositive(false)}>查看全零姿态</button><button aria-pressed={positive} className={positive?'selected':''} onClick={()=>setPositive(true)}>查看本轴 +5°</button><select aria-label="零位参考视角" value={view} onChange={e=>setView(e.target.value)}><option value="perspective">透视</option><option value="top">顶视</option><option value="front">前视</option><option value="side">侧视</option></select></div>
  <div className="zero-reference-scene" data-model-ready={sceneStatus.includes('已载入')}>{state&&data?<SceneView key={axis} state={state} model={model} plan={null} points={[]} drag={false} target={[0,0,0]} onTarget={()=>{}} onDragging={()=>{}} trialStatus="" view={view} onLoad={setSceneStatus} referenceAxis={{origin:data.origin,direction:data.direction}}/>:<p>{error||'正在读取模型参考…'}</p>}</div>
  {sceneStatus.includes('失败')&&<p role="alert">{sceneStatus}</p>}
  <p className="hint">蓝色箭头标出当前轴正方向，正角遵循右手定则。对照相邻两段结构，不按屏幕上的顺/逆时针猜方向。零位是模型装配参考，实体的安装标记仍需人工确定。</p>
 </div>;
}
