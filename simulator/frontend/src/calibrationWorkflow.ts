import type {AxisMapping} from './types';

export type Point={deg:number;us:number};
export type Reading={deg:number;us:number;ticks:number;time:string;direction:string;load:string;target?:number;revision?:number};
export type Draft={points:Point[];readings:Reading[];low:number;high:number;load:string};
export const emptyDraft=():Draft=>({points:[],readings:[],low:-5,high:5,load:'空载'});
export function deviceDraft(mapping?:AxisMapping):Draft {
 return mapping?.confirmed?{...emptyDraft(),points:mapping.points.map(p=>({...p})),low:mapping.work_low_deg,high:mapping.work_high_deg}:emptyDraft();
}
export function pointProblems(points:Point[]):string[] {
 const problems:string[]=[];
 if(points.length<3||points.length>7)problems.push('需要 3–7 个测量点');
 if(!points.some(p=>p.deg===0))problems.push('缺少关节 0° 参考点');
 if(!points.some(p=>p.deg<0)||!points.some(p=>p.deg>0))problems.push('零位两侧各需至少一个测量点');
 if(points.some(p=>!Number.isFinite(p.deg)||Math.abs(p.deg)>180||!Number.isFinite(p.us)||p.us<500||p.us>2500))problems.push('角度须在 ±180° 内，脉宽须在 500–2500 μs 内');
 const differences=points.slice(1).map((p,i)=>p.us-points[i].us);
 if(points.some((p,i)=>i>0&&p.deg<=points[i-1].deg)||differences.length&&!(differences.every(d=>d>0)||differences.every(d=>d<0)))problems.push('角度顺序或脉宽方向不一致，请复核读数');
 return problems;
}
export function rangeProblems(draft:Draft):string[] {
 if(!Number.isFinite(draft.low)||!Number.isFinite(draft.high)||draft.low>=0||draft.high<=0)return ['工作下限须小于 0°，上限须大于 0°'];
 if(!draft.points.length||draft.low<draft.points[0].deg||draft.high>draft.points.at(-1)!.deg)return ['工作限位超出实测覆盖，请缩小范围或补测端点'];
 return [];
}
export function pulseAt(points:Point[],angle:number):number|null {
 if(!Number.isFinite(angle)||!points.length||angle<points[0].deg||angle>points.at(-1)!.deg)return null;
 for(let i=1;i<points.length;i++)if(angle<=points[i].deg){const a=points[i-1],b=points[i];return a.us+(angle-a.deg)*(b.us-a.us)/(b.deg-a.deg);}
 return null;
}
// Drafts (including older exports) are untrusted input, not device calibration.
export function parseDraft(value:unknown):Draft {
 if(!value||typeof value!=='object')throw Error('当前轴草稿无效');
 const d=value as Draft;
 if(!Array.isArray(d.points)||d.points.length>7||!Array.isArray(d.readings)||d.readings.length>1000||!Number.isFinite(d.low)||!Number.isFinite(d.high)||typeof d.load!=='string'||
    d.points.some(p=>!p||!Number.isFinite(p.deg)||Math.abs(p.deg)>180||!Number.isFinite(p.us)||p.us<500||p.us>2500)||
    d.readings.some(r=>!r||![r.deg,r.us,r.ticks].every(Number.isFinite)||typeof r.time!=='string'||typeof r.direction!=='string'||typeof r.load!=='string'||(r.target!==undefined&&!Number.isFinite(r.target))))throw Error('当前轴草稿无效，请检查角度、脉宽和人工记录');
 return {points:d.points.map(p=>({deg:p.deg,us:p.us})).sort((a,b)=>a.deg-b.deg),readings:d.readings,low:d.low,high:d.high,load:d.load};
}
