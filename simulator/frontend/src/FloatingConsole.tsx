import {useLayoutEffect,useRef,useState} from 'react';
import type {KeyboardEvent,PointerEvent,ReactNode} from 'react';
import {Terminal,X} from 'lucide-react';

type Box={x:number;y:number;width:number;height:number};
export function FloatingConsole({open,onClose,children}:{open:boolean;onClose:()=>void;children:ReactNode}){
 const frame=useRef<HTMLElement>(null),[box,setBox]=useState<Box|null>(null);
 const gesture=useRef<{kind:'move'|'resize';startX:number;startY:number;box:Box}|null>(null);
 const bounds=()=>{
  const parent=frame.current?.parentElement;
  return {width:parent?.clientWidth??640,height:parent?.clientHeight??480,
   top:(parent?.querySelector('.scene-toolbar') as HTMLElement|null)?.offsetHeight??51};
 };
 const constrain=(value:Box):Box=>{
  const area=bounds(),margin=10,top=area.top+margin;
  const width=Math.max(Math.min(300,area.width-2*margin),Math.min(value.width,area.width-2*margin));
  const height=Math.max(Math.min(220,area.height-top-margin),Math.min(value.height,area.height-top-margin));
  return {width,height,x:Math.max(margin,Math.min(value.x,area.width-width-margin)),y:Math.max(top,Math.min(value.y,area.height-height-margin))};
 };
 useLayoutEffect(()=>{
  const parent=frame.current?.parentElement;if(!parent)return;
  const update=()=>setBox(old=>{
   const area=bounds();
   const height=Math.min(300,(area.height-area.top)*.48);
   return constrain(old??{x:12,y:area.height-height-12,width:Math.min(480,area.width*.72),height});
  });
  update();const observer=new ResizeObserver(update);observer.observe(parent);
  return()=>observer.disconnect();
 },[]);
 const begin=(event:PointerEvent<HTMLButtonElement>,kind:'move'|'resize')=>{
  if(event.button!==0||!box)return;
  event.preventDefault();event.stopPropagation();
  gesture.current={kind,startX:event.clientX,startY:event.clientY,box};
  event.currentTarget.setPointerCapture(event.pointerId);
 };
 const move=(event:PointerEvent<HTMLButtonElement>)=>{
  const start=gesture.current;if(!start)return;
  const dx=event.clientX-start.startX,dy=event.clientY-start.startY;
  if(start.kind==='move')setBox(constrain({...start.box,x:start.box.x+dx,y:start.box.y+dy}));
  else{
   const area=bounds();
   setBox(constrain({...start.box,width:Math.min(start.box.width+dx,area.width-start.box.x-10),height:Math.min(start.box.height+dy,area.height-start.box.y-10)}));
  }
 };
 const end=(event:PointerEvent<HTMLButtonElement>)=>{
  gesture.current=null;
  if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
 };
 const keyboard=(event:KeyboardEvent<HTMLButtonElement>,kind:'move'|'resize')=>{
  if(!box||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
  event.preventDefault();event.stopPropagation();const amount=event.shiftKey?1:10;
  const dx=event.key==='ArrowLeft'?-amount:event.key==='ArrowRight'?amount:0;
  const dy=event.key==='ArrowUp'?-amount:event.key==='ArrowDown'?amount:0;
  setBox(constrain(kind==='move'?{...box,x:box.x+dx,y:box.y+dy}:{...box,width:box.width+dx,height:box.height+dy}));
 };
 return <section ref={frame} className="floating-console" role="dialog" aria-label="命令控制台" hidden={!open}
  style={box?{left:box.x,top:box.y,width:box.width,height:box.height}:undefined}>
  <div className="floating-heading">
   <button className="console-drag" aria-label="移动控制台" title="拖动标题栏移动；方向键微调" onPointerDown={e=>begin(e,'move')} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={()=>{gesture.current=null;}} onKeyDown={e=>keyboard(e,'move')}><Terminal size={16}/><strong>命令控制台</strong><span>拖动移动</span></button>
   <button className="console-close" aria-label="关闭控制台" onClick={onClose}><X size={17}/></button>
  </div>
  {children}
  <button className="console-resize" aria-label="调整控制台大小" title="拖动调整大小；方向键微调" onPointerDown={e=>begin(e,'resize')} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={()=>{gesture.current=null;}} onKeyDown={e=>keyboard(e,'resize')}>◢</button>
 </section>;
}
