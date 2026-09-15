import {useEffect,useRef,useState} from 'react';

export type TrialPose={q_deg:number[];matrices:number[][];tcp:number[][]};
export type TrialResult=Partial<TrialPose>&{
 status:'reachable'|'collision'|'unsolved'|'error';message:string;
 error?:{position_mm:number;direction_deg:number};near_limits?:string[];elapsed_ms?:number;
};
type Input={enabled:boolean;target:number[];direction?:number[];dragging:boolean;
 seq:number;revision:number;actual:TrialPose|null;reset:number};
type Request=(path:string,body?:unknown)=>Promise<any>;

// One in-flight request and one replaceable pending target. Stale responses
// never change the displayed pose, including after a scene edit or execution.
export function useReachability(input:Input,api:Request){
 const key=JSON.stringify([input.enabled,input.target,input.direction,input.dragging,input.seq,input.revision,input.reset]);
 const scope=`${input.seq}:${input.revision}:${input.reset}`;
 const latest=useRef({input,key,scope});latest.current={input,key,scope};
 const alive=useRef(true),busy=useRef(false);
 const pending=useRef<typeof latest.current|null>(null);
 const valid=useRef<{scope:string;pose:TrialPose}|null>(null);
 const [answer,setAnswer]=useState<{key:string;result:TrialResult}|null>(null);
 const [accepted,setAccepted]=useState<{scope:string;pose:TrialPose}|null>(null);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;pending.current=null;};},[]);
 useEffect(()=>{
  if(!input.enabled){pending.current=null;return;}
  const timer=window.setTimeout(()=>{
   pending.current=latest.current;
   const pump=async()=>{
    if(busy.current)return;
    busy.current=true;
    try{
     while(pending.current&&alive.current){
      const job=pending.current;pending.current=null;
      if(job.key!==latest.current.key||!job.input.actual)continue;
      const seed=valid.current?.scope===job.scope?valid.current.pose.q_deg:job.input.actual.q_deg;
      let result:TrialResult;
      try{result=await api('reachability',{position_mm:job.input.target,seed_deg:seed,
       direction:job.input.direction,refine:!job.input.dragging,seq:job.input.seq,revision:job.input.revision});}
      catch(error){result={status:'error',message:error instanceof Error?error.message:String(error)};}
      const current=latest.current;
      const followingPointer=job.input.dragging&&current.input.dragging&&job.scope===current.scope&&JSON.stringify(job.input.direction)===JSON.stringify(current.input.direction);
      if(!alive.current||!current.input.enabled||(job.key!==current.key&&!followingPointer))continue;
      if(result.status==='reachable'&&result.q_deg&&result.matrices&&result.tcp){
       const next={scope:job.scope,pose:{q_deg:result.q_deg,matrices:result.matrices,tcp:result.tcp}};
       valid.current=next;setAccepted(next);
      }
      // An intermediate drag pose may be displayed, but only a result for
      // the exact latest target may label that target reachable.
      if(job.key===current.key)setAnswer({key:job.key,result});
     }
    }finally{busy.current=false;}
   };
   void pump();
  },input.dragging?0:70);
  return()=>window.clearTimeout(timer);
 },[key]);
 return {result:input.enabled&&answer?.key===key?answer.result:null,
  pose:accepted?.scope===scope?accepted.pose:null,
  solving:input.enabled&&answer?.key!==key};
}
