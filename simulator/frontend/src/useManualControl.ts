import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {State} from './types';
import type {TrialResult} from './useReachability';
export type ManualTarget={kind:'joint'|'cartesian';q_deg?:number[];position_mm?:number[];direction?:number[];refine:boolean};

export function useManualControl(state:State|null,onState:(s:State)=>void){
 const latest=useRef({state,onState});latest.current={state,onState};
 const serial=useRef(0),epoch=useRef(0),active=useRef(false),alive=useRef(true);
 const pending=useRef<{id:number;epoch:number;target:ManualTarget}|null>(null);
 const [busy,setBusy]=useState(false),[result,setResult]=useState<TrialResult|null>(null);
 useEffect(()=>()=>{alive.current=false;pending.current=null;},[]);
 const cancel=()=>{epoch.current++;serial.current++;pending.current=null;setResult(null);setBusy(false);};
 const submit=(target:ManualTarget)=>{
  const id=++serial.current;pending.current={id,epoch:epoch.current,target};setBusy(true);setResult(null);
  const pump=async()=>{
   if(active.current)return;
   active.current=true;
   try{
    while(pending.current&&alive.current){
     const job=pending.current;pending.current=null;
     const current=latest.current.state;if(!current)continue;
     try{
      const answer=await api('manual',{...job.target,seq:current.seq,revision:current.revision});
      if(!alive.current||job.epoch!==epoch.current)continue;
      // Intermediate results are actual controller states, even when a newer
      // pointer target is already queued. Only the latest target owns feedback.
      latest.current.state=answer.state;latest.current.onState(answer.state);
      if(job.id===serial.current)setResult(answer);
     }catch(error){
      if(alive.current&&job.epoch===epoch.current&&job.id===serial.current)
       setResult({status:'error',message:error instanceof Error?error.message:String(error)});
     }
    }
   }finally{active.current=false;if(alive.current&&!pending.current)setBusy(false);}
  };
  void pump();
 };
 return {submit,cancel,busy,result};
}
