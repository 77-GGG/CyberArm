import json
import time
import numpy as np
import pytest
from cyberarm.model import Robot,ROOT
from cyberarm.planner import Geometry,inverse,plan_job,Rejected
from cyberarm.server import Controller,Project,Step

@pytest.fixture(scope='module')
def robot():return Robot()

def test_blender_reference(robot):
    samples=json.loads((ROOT/'assets/revc/reference_poses.json').read_text())
    translations=[];rotation=[]
    for sample in samples:
        frames,tcp=robot.fk(np.radians(sample['q_deg']))
        reference=np.array(sample['frames']);translations.append(float(np.max(np.linalg.norm(frames[:,:3,3]-reference[:,:3,3],axis=1))))
        assert np.max(np.abs(frames-reference))<1e-6
        assert np.linalg.norm(tcp[:3,3]-np.array(sample['tcp'])[:3,3])<.0001
        rotation.append(float(np.max(np.abs(frames[:,:3,:3]-reference[:,:3,:3]))))
    assert len(samples)>=67
    report={'poses':len(samples),'max_position_error_mm':max(translations)*1000,'max_rotation_matrix_element_error':max(rotation)}
    (ROOT/'reports').mkdir(exist_ok=True);(ROOT/'reports/model_baseline.json').write_text(json.dumps(report,indent=2))

def test_known_reachable_ik(robot):
    rng=np.random.default_rng(924);success=0;errors=[];failed=[]
    for i in range(100):
        known=rng.uniform(robot.limits[:,0]*.8,robot.limits[:,1]*.8);known[5]=0
        target=robot.fk(known)[1]
        try:
            q,error=inverse(robot,target[:3,3],np.zeros(6),target[:3,2] if i%2 else None)
            assert robot.within(q);assert error['position_mm']<=.5;assert error['direction_deg']<=.5
            success+=1;errors.append(error)
        except Rejected as e:failed.append({'index':i,'reason':str(e)})
    (ROOT/'reports').mkdir(exist_ok=True);(ROOT/'reports/ik_baseline.json').write_text(json.dumps({'targets':100,'success':success,'failures':failed,'errors':errors},indent=2))
    assert success>=95

def test_invalid_target_and_limits(robot):
    with pytest.raises(Rejected):inverse(robot,[10,10,10],np.zeros(6))
    with pytest.raises(ValueError):robot.fk([float('nan')]*6)
    assert not robot.within(np.radians([0,0,0,0,0,9]))
    with pytest.raises(ValueError):Step(kind='joint')
    with pytest.raises(ValueError):Project(schema_version=1,model_version='a',steps=[],speed=float('nan'))

def test_collision_and_midpath(robot):
    geometry=Geometry(robot,[]);assert geometry.clearance(np.zeros(6))[0]>.0002
    # A box around the tool at the midpoint must reject an otherwise valid arc.
    low=np.radians([-20,0,0,0,0,0]);high=np.radians([20,0,0,0,0,0])
    # TCP lies in free space between the fingers. Place the obstacle on the
    # left jaw material instead of confusing empty grasp space with a collision.
    jaw=next(m for m in robot.data['meshes'] if m['source']=='ARD_10_Jaw_Left')
    middle=np.mean(jaw['bounds'],axis=0)
    obstacle={'name':'中途障碍','center':middle.tolist(),'size':[.008,.008,.008]}
    blocked=Geometry(robot,[obstacle])
    assert blocked.clearance(low)[0]>.0002
    assert blocked.clearance(high)[0]>.0002
    with pytest.raises(Rejected):blocked.check_segment(low,high,time.monotonic()+45)

def test_execution_stop_pause_and_determinism(robot):
    p=plan_job({'start':[0]*6,'obstacles':[],'steps':[{'kind':'joint','q_deg':[12,0,0,0,0,0]}],'speed':1})
    def run(stop=False):
        controller=Controller();controller.active=p;controller.mode='RUNNING'
        states=[]
        for i in range(600):
            if stop and i==20:controller.stop(True)
            controller.advance(.02);states.append(controller.q.copy())
        return controller,np.array(states)
    end,trace=run();assert end.mode=='READY';assert np.allclose(end.q,p['end'])
    assert np.array_equal(trace,run()[1])
    paused,stopped=run(True);assert paused.mode=='PAUSED';assert paused.q[0]<end.q[0]
    velocity=np.diff(stopped,axis=0)/.02;acceleration=np.diff(velocity,axis=0)/.02
    assert np.all(np.abs(velocity)<=robot.vmax+1e-7)
    assert np.all(np.abs(acceleration)<=robot.amax+1e-7)

def test_curve_endpoints(robot):
    assert np.allclose(robot.curve(0,2),[0,0,0])
    assert np.allclose(robot.curve(2,2),[1,0,0])
    assert np.allclose(robot.curve(1,2),[.5,.9375,0])
