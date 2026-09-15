import asyncio
import numpy as np
import pytest
from fastapi.testclient import TestClient
from cyberarm import server


@pytest.fixture
def connection():
    with TestClient(server.app) as client:
        boot=client.get('/api/bootstrap').json()
        yield client,{'X-Session':boot['session'],'X-Client':'manual-test'}


def test_manual_updates_current_position_and_invalidates_plan(connection):
    client,headers=connection
    before=client.get('/api/state').json()
    plan=client.post('/api/plan',headers=headers,json={'steps':[{'kind':'joint','q_deg':[2,0,0,0,0,0]}]}).json()
    result=client.post('/api/manual',headers=headers,json={'kind':'joint','q_deg':[3,0,0,0,0,1],
                      'seq':before['seq'],'revision':before['revision']})
    assert result.status_code==200
    assert result.json()['status']=='reachable'
    after=client.get('/api/state').json()
    assert after['q_deg']==pytest.approx([3,0,0,0,0,1])
    assert after['mode']=='READY'
    assert after['seq']>before['seq']
    assert after['tcp']!=before['tcp']
    assert client.post('/api/execute',headers=headers,json={'plan_id':plan['plan_id']}).status_code==409
    target=np.array(after['tcp'])[:3,3]*1000;target[1]+=1
    cart=client.post('/api/manual',headers=headers,json={'kind':'cartesian','position_mm':target.tolist(),
                    'seq':after['seq'],'revision':after['revision']})
    assert cart.status_code==200
    assert cart.json()['status']=='reachable'
    assert np.linalg.norm(np.array(cart.json()['state']['tcp'])[:3,3]*1000-target)<.5


def test_rejected_manual_target_does_not_move_and_stop_cancels_inflight(connection,monkeypatch):
    client,headers=connection
    before=client.get('/api/state').json()
    def request(**target):return client.post('/api/manual',headers=headers,json={**target,'seq':before['seq'],'revision':before['revision']})
    assert request(kind='joint',q_deg=[90,0,0,0,0,0]).status_code==422
    result=request(kind='cartesian',position_mm=[10000]*3)
    assert result.json()['status']=='unsolved'
    assert client.get('/api/state').json()['q_deg']==before['q_deg']
    # In-flight work must never apply after stop, even if the worker returns
    # an otherwise valid target for the unchanged seq/revision.
    loop=client.portal.call(asyncio.get_running_loop)
    original=loop.run_in_executor
    def interrupted(executor,fn,*args):
        if fn is server.manual_job:
            server.c.stop(False)
        return original(executor,fn,*args)
    monkeypatch.setattr(loop,'run_in_executor',interrupted)
    assert request(kind='joint',q_deg=[2,0,0,0,0,0]).status_code==409
    assert client.get('/api/state').json()['q_deg']==before['q_deg']


def test_manual_rejects_running_and_stale_scene(connection):
    client,headers=connection
    body={'kind':'joint','q_deg':[1,0,0,0,0,0],'seq':0,'revision':0}
    client.post('/api/scene',headers=headers,json={'obstacles':[]})
    assert client.post('/api/manual',headers=headers,json=body).status_code==409
    body['revision']=1
    plan=client.post('/api/plan',headers=headers,json={'steps':[{'kind':'wait','seconds':5}]}).json()
    client.post('/api/execute',headers=headers,json={'plan_id':plan['plan_id']})
    assert client.post('/api/manual',headers=headers,json=body).status_code==409


def test_manual_keeps_segment_collision_checks_without_visual_preview(connection):
    client,headers=connection
    before=client.get('/api/state').json()
    first=client.post('/api/manual',headers=headers,json={'kind':'joint','q_deg':[-20,0,0,0,0,0],
                      'seq':before['seq'],'revision':before['revision']}).json()
    assert first['status']=='reachable'
    jaw=next(m for m in server.c.r.data['meshes'] if m['source']=='ARD_10_Jaw_Left')
    obstacle={'name':'中途障碍','center':np.mean(jaw['bounds'],axis=0).tolist(),'size':[.008]*3}
    scene=client.post('/api/scene',headers=headers,json={'obstacles':[obstacle]}).json()
    result=client.post('/api/manual',headers=headers,json={'kind':'joint','q_deg':[20,0,0,0,0,0],
                       'seq':scene['seq'],'revision':scene['revision']}).json()
    assert result['status']=='collision'
    assert result['state']['q_deg']==pytest.approx([-20,0,0,0,0,0])
