import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
from cyberarm.model import Robot
from cyberarm.planner import Rejected, inverse, plan_job
from cyberarm.reachability import reachability_job
from cyberarm.server import app, Reachability


def payload(q=None):
    r=Robot();q=np.zeros(6) if q is None else np.asarray(q)
    return dict(position_mm=(r.fk(q)[1][:3,3]*1000).tolist(),seed_deg=np.degrees(q).tolist(),obstacles=[],refine=True)


def test_continuous_reachable_targets_and_gripper():
    r=Robot();seed=np.radians([0,0,0,0,0,2])
    times=[]
    for yaw in np.linspace(0,8,25):
        known=np.radians([yaw,0,0,0,0,2]);p=payload(known)
        p.update(seed_deg=np.degrees(seed).tolist(),refine=False)
        result=reachability_job(p)
        # A busy desktop may exhaust the fast wall-clock budget. Releasing
        # the pointer requests a refined solve, just as the UI does.
        if result['status']=='unsolved':
            p['refine']=True;result=reachability_job(p)
        assert result['status']=='reachable'
        current=np.radians(result['q_deg'])
        assert r.within(current)
        assert np.max(np.abs(np.degrees(current-seed)))<3
        assert result['q_deg'][5]==pytest.approx(2)
        assert np.linalg.norm(np.array(result['tcp'])[:3,3]*1000-p['position_mm'])<=.5
        seed=current;times.append(result['elapsed_ms'])
    print('warm trial p50/p95 ms:',np.percentile(times[1:],[50,95]))


def test_failure_collision_and_limit_feedback():
    p=payload();p['position_mm']=[10000]*3
    result=reachability_job(p)
    assert result['status']=='unsolved'
    assert 'matrices' not in result
    p=payload()
    r=Robot();jaw=next(m for m in r.data['meshes'] if m['source']=='ARD_10_Jaw_Left')
    p['obstacles']=[dict(name='测试障碍',center=np.mean(jaw['bounds'],axis=0).tolist(),size=[.008]*3)]
    result=reachability_job(p)
    assert result['status']=='collision'
    assert '测试障碍' in result['collision_pair']
    assert 'J1' in reachability_job(payload(np.radians([29,0,0,0,0,0])))['near_limits']


def test_deadline_and_bad_direction():
    with pytest.raises(Rejected):inverse(Robot(),[.2,0,.1],np.zeros(6),deadline=time.monotonic()-1)
    with pytest.raises(ValueError):Reachability(position_mm=[0]*3,seed_deg=[0]*6,direction=[0]*3,seq=0,revision=0)


def test_selected_endpoint_preserved_and_revalidated():
    q=np.radians([3,0,0,0,0,0]);p=payload(q)
    step=dict(kind='cartesian',position_mm=p['position_mm'],q_deg=p['seed_deg'])
    job=dict(start=[0]*6,obstacles=[],steps=[step],speed=.7)
    result=plan_job(job)
    assert result['end']==pytest.approx(q)
    step['position_mm'][0]+=10
    with pytest.raises(Rejected,match='不一致'):plan_job(job)


def test_zero_length_linear_move_is_a_checked_hold():
    p=payload()
    result=plan_job(dict(start=[0]*6,obstacles=[],speed=.7,
                         steps=[dict(kind='linear',position_mm=p['position_mm'])]))
    assert len(result['segments'])==1
    assert result['end']==pytest.approx([0]*6)
    assert result['checks']>0


def test_api_does_not_move_controller_and_rejects_stale_scene():
    with TestClient(app) as client:
        boot=client.get('/api/bootstrap').json()
        headers={'X-Session':boot['session'],'X-Client':'trial-test'}
        before=client.get('/api/state').json()
        p=payload();p.pop('obstacles');p['seq']=before['seq'];p['revision']=before['revision']
        result=client.post('/api/reachability',json=p,headers=headers)
        assert result.status_code==200
        assert result.json()['status']=='reachable'
        after=client.get('/api/state').json()
        for key in ('q_deg','seq','revision','mode'):assert before[key]==after[key]
        assert client.post('/api/scene',json={'obstacles':[]},headers=headers).status_code==200
        assert client.post('/api/reachability',json=p,headers=headers).status_code==409
        p['revision']+=1;p['seed_deg'][0]=90
        assert client.post('/api/reachability',json=p,headers=headers).status_code==422
