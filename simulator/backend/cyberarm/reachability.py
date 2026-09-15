"""Read-only TCP trials. A valid endpoint does not certify a motion path."""
from functools import lru_cache
import json
import time
import numpy as np
from .model import Robot
from .planner import Geometry, inverse, Rejected


@lru_cache(maxsize=1)
def geometry_for_scene(scene):
    return Geometry(Robot(),json.loads(scene))


def reachability_job(payload):
    began=time.monotonic()
    geometry=geometry_for_scene(json.dumps(payload['obstacles'],sort_keys=True))
    robot=geometry.r
    seed=np.radians(payload['seed_deg'])
    if not robot.within(seed):raise Rejected('试摆初始角度超出关节限制')
    target=np.asarray(payload['position_mm'])/1000
    refine=payload.get('refine',True)
    try:
        q,error=inverse(robot,target,seed,payload.get('direction'),
                        attempts=7 if refine else 1,
                        deadline=time.monotonic()+(.25 if refine else .035))
    except Rejected as exc:
        return {'status':'unsolved','message':str(exc),'elapsed_ms':(time.monotonic()-began)*1000}
    gap,pair=geometry.clearance(q)
    margins=np.degrees(np.minimum(q-robot.limits[:,0],robot.limits[:,1]-q))
    near=[f'J{i+1}' for i in range(5) if margins[i]<2]
    # Do not flip branches while the pointer is moving. The user can release
    # to run a broader search, then inspect the resulting pose before planning.
    jump=float(np.max(np.abs(np.degrees(q[:5]-seed[:5]))))
    status='collision' if gap<=.0002 else 'reachable'
    if not refine and jump>12:status='unsolved'
    message=('此姿态存在干涉或间隙不足：'+' / '.join(pair) if status=='collision' else
             '连续解变化过大，请松开鼠标重新求解' if status=='unsolved' else
             '目标可达 · 路径尚未检查')
    matrices,tcp=robot.transforms(q)
    return {'status':status,'message':message,'q_deg':np.degrees(q).tolist(),
            'matrices':matrices,'tcp':tcp,'error':error,'near_limits':near,
            'collision_pair':list(pair) if status=='collision' else [],
            'elapsed_ms':(time.monotonic()-began)*1000}
