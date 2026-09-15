export type Obstacle={name:string;center:number[];size:number[]};
export type State={mode:string;q_deg:number[];matrices:number[][];tcp:number[][];seq:number;revision:number;time:number;duration:number;events:{time:string;message:string}[];planning:boolean;error:string;obstacles:Obstacle[]};
export type Model={limits_deg:number[][];model_id:string;source_sha256:string;meshes:{bounds:number[][]}[]};
export type Step={kind:'joint'|'cartesian'|'linear'|'wait';q_deg?:number[];position_mm?:number[];direction?:number[];seconds?:number};
export type Plan={plan_id:string;duration:number;end:number[];path:number[][];checks:number;seq:number;revision:number};
