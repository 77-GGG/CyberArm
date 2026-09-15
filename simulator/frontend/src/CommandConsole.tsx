import {useEffect,useRef,useState} from 'react';
import {api} from './api';

export type CommandResult={protocol_version:number;request_id:string;ok:boolean;command:string;data?:any;error?:{code:number;message:string};elapsed_ms:number};
type Entry={id:string;text:string;output:string;ok:boolean};
export function CommandConsole({connected,onStart,onResult,onFinish}:{connected:boolean;onStart:()=>void;onResult:(result:CommandResult)=>Promise<void>;onFinish:()=>void}){
 const [text,setText]=useState(''),[busy,setBusy]=useState(false),[entries,setEntries]=useState<Entry[]>([]);
 const [commands,setCommands]=useState<{command:string;usage:string;description:string}[]>([]);
 const history=useRef<string[]>([]),index=useRef(0),draft=useRef(''),output=useRef<HTMLDivElement>(null),locked=useRef(false);
 useEffect(()=>{api('commands').then(data=>setCommands(data.commands)).catch(()=>{});},[]);
 useEffect(()=>{output.current?.scrollTo(0,output.current.scrollHeight);},[entries,busy]);
 const submit=async()=>{
  const line=text.trim();if(!line||locked.current||!connected)return;
  if(line==='clear'){setEntries([]);setText('');return;}
  locked.current=true;setBusy(true);onStart();setText('');
  history.current=[...history.current,line].slice(-100);index.current=history.current.length;
  const id=crypto.randomUUID();
  try{
   const result:CommandResult=await api('command',{protocol_version:1,request_id:id,text:line});
   const data=result.command==='help'&&result.ok?result.data.map((c:{usage:string;description:string})=>`${c.usage}\n  ${c.description}`).join('\n'):JSON.stringify(result.data,null,2);
   setEntries(old=>[...old,{id,text:line,ok:result.ok,output:result.ok?data:`错误 ${result.error?.code}: ${result.error?.message}`}].slice(-100));
   await onResult(result);
  }catch(e){setEntries(old=>[...old,{id:id+'-error',text:line,ok:false,output:`${e instanceof Error?e.message:String(e)}\n响应未确认；先查询 status，不自动重发运动命令。`}].slice(-100));}
  finally{locked.current=false;setBusy(false);onFinish();}
 };
 return <div className="command-console">
  <details className="console-guide"><summary>仿真 · ° / mm · help 查看命令</summary><p>Enter 执行，↑↓ 历史，Tab 补全，clear 清屏。movej / moveto / movel 检查后立即运动。Esc 或底部停止可取消运动。</p></details>
  <div className="console-address">本地服务：<code>{location.origin}</code></div>
  <div className="console-output" role="log" aria-label="命令输出" ref={output}>
   {!entries.length&&<span className="console-empty">输入 status 查看状态，或输入 help 查看命令。</span>}
   {entries.map(entry=><div key={entry.id} className={entry.ok?'console-entry':'console-entry failed'}><div className="console-prompt">&gt; {entry.text}</div><pre>{entry.output}</pre></div>)}
   {busy&&<div role="status">正在执行命令…</div>}
  </div>
  <form onSubmit={e=>{e.preventDefault();void submit();}} className="console-input">
   <span>&gt;</span><input aria-label="控制台命令" autoComplete="off" spellCheck={false} value={text} disabled={!connected||busy} placeholder="help / status / joint 1 3" onChange={e=>setText(e.target.value)} onKeyDown={e=>{
    if(e.key==='ArrowUp'||e.key==='ArrowDown'){
     e.preventDefault();if(index.current===history.current.length)draft.current=text;
     index.current=Math.max(0,Math.min(history.current.length,index.current+(e.key==='ArrowUp'?-1:1)));
     setText(history.current[index.current]??draft.current);
    }
    if(e.key==='Tab'&&!text.includes(' ')){
     const matches=commands.filter(c=>c.command.startsWith(text));
     if(matches.length===1){e.preventDefault();setText(matches[0].command+' ');}
    }
   }}/><button className="solid" type="submit" disabled={!connected||busy||!text.trim()}>发送</button>
  </form>
 </div>;
}
