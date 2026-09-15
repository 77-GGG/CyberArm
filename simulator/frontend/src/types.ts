export type Obstacle={name:string;center:number[];size:number[]};
export type ServoCalibration={min_us:number;center_us:number;max_us:number;reversed:boolean;confirmed:boolean};
export type HardwareState={available:boolean;connected:boolean;armed:boolean;outputs_enabled:boolean;mode:string;port:string|null;baud:number|null;protocol_version:number;firmware_version:string|null;model_id:string;driver_ready:boolean;calibrated:boolean[];calibration:(ServoCalibration|null)[];commanded_q_deg:number[]|null;measured_q_deg:number[]|null;measured_feedback:boolean;last_seen:number|null;error:string};
export type State={mode:string;q_deg:number[];matrices:number[][];tcp:number[][];seq:number;revision:number;time:number;duration:number;events:{time:string;message:string}[];planning:boolean;error:string;obstacles:Obstacle[];hardware:HardwareState|null};
export type Model={limits_deg:number[][];model_id:string;source_sha256:string;meshes:{bounds:number[][]}[]};
export type Step={kind:'joint'|'cartesian'|'linear'|'wait';q_deg?:number[];position_mm?:number[];direction?:number[];seconds?:number};
export type Plan={plan_id:string;duration:number;end:number[];path:number[][];checks:number;seq:number;revision:number};
