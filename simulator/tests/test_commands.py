import asyncio
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from cyberarm import server
from cyberarm.commands import parse_text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sdk'))
from cyberarm_sdk import CyberArm, CommandError


@pytest.fixture
def connection():
    with TestClient(server.app) as client:
        headers = {'X-Session': client.get('/api/bootstrap').json()['session'], 'X-Client': 'commands-test'}
        yield client, headers


def send(connection, text=None, **body):
    client, headers = connection
    response = client.post('/api/command', headers=headers, json={'text': text, **body} if text is not None else body)
    assert response.status_code == 200
    return response.json()


def test_catalogue_status_and_structured_parity(connection):
    client, headers = connection
    specs = client.get('/api/commands').json()['commands']
    assert len(specs) == 27
    for name in ('status', 'joints', 'tcp', 'limits', 'events', 'device', 'hwstatus'):
        text = send(connection, name)
        structured = send(connection, command=name, args={}, request_id='correlation-test')
        assert text['ok'] and structured['ok']
        assert text['data'] == structured['data']
        assert structured['request_id'] == 'correlation-test'
    assert send(connection, 'device')['data']['measured_feedback'] is False
    assert send(connection, 'device')['data']['hardware_transports'] == ['usb-cdc-jsonl-v1']
    assert send(connection, 'help joint')['data'][0]['args_schema']['properties']['index']['maximum'] == 6
    assert client.post('/api/command', json={'text': 'stop'}).status_code == 403
    assert client.post('/api/command', headers=headers, json={'text': 'stop', 'command': 'status'}).status_code == 422
    assert client.post('/api/command', headers=headers, json={'text': 'status', 'protocol_version': 2}).status_code == 422


@pytest.mark.parametrize('line', ['joint 0 3', 'joint 1 nan', 'joint 1 inf', 'pose 0 0',
                                       'movej 0 0 0 0 0 0 2', 'status extra', 'stop; reset',
                                       'plan {bad}', 'joint {"index":1,"angle_deg":2,"extra":1}',
                                       'moveto {"position_mm":[1,2,3],"direction":[0,0,0]}'])
def test_invalid_commands_do_not_move(connection, line):
    before = server.c.q.copy()
    result = send(connection, line)
    assert not result['ok'] and result['error']['code'] == 422
    assert np.array_equal(before, server.c.q)


def test_manual_commands_and_stale_plan(connection):
    plan = send(connection, 'plan {"steps":[{"kind":"joint","q_deg":[2,0,0,0,0,0]}]}')
    assert plan['ok']
    assert send(connection, 'joint 1 3')['ok']
    assert send(connection, 'grip 1')['ok']
    assert send(connection, 'joints')['data']['q_deg'] == pytest.approx([3,0,0,0,0,1])
    assert send(connection, 'execute '+plan['data']['plan_id'])['error']['code'] == 409
    assert not send(connection, 'joint 1 90')['ok']
    assert send(connection, 'pose 0 0 0 0 0 0')['ok']


def test_collision_rejection_uses_segment_checks(connection):
    client, headers = connection
    assert send(connection, 'joint 1 -20')['ok']
    jaw = next(m for m in server.c.r.data['meshes'] if m['source'] == 'ARD_10_Jaw_Left')
    client.post('/api/scene', headers=headers, json={'obstacles': [
        {'name': 'midpath', 'center': np.mean(jaw['bounds'], axis=0).tolist(), 'size': [.008]*3}]})
    assert not send(connection, 'joint 1 20')['ok']
    assert send(connection, 'joints')['data']['q_deg'][0] == pytest.approx(-20)


def test_motion_owner_busy_pause_resume_stop(connection):
    client, headers = connection
    plan = send(connection, 'plan {"steps":[{"kind":"wait","seconds":10}]}')['data']
    other = (client, {**headers, 'X-Client': 'other'})
    assert send(other, 'execute '+plan['plan_id'])['error']['code'] == 409
    assert send(connection, 'execute '+plan['plan_id'])['ok']
    assert not send(connection, 'joint 1 1')['ok']
    client.post('/api/release', headers=other[1], json={})
    assert server.c.mode == 'RUNNING'
    assert send(connection, 'pause')['ok']
    client.portal.call(lambda: server.c.advance(2))
    assert server.c.mode == 'PAUSED'
    assert send(connection, 'resume')['ok']
    client.post('/api/release', headers=headers, json={})
    assert server.c.mode == 'STOPPING'
    client.portal.call(lambda: server.c.advance(2))
    assert server.c.mode == 'PAUSED'
    assert send(connection, 'stop')['ok']
    assert not send(connection, 'resume')['ok']
    assert send(connection, 'reset')['ok']


def test_stop_cancels_command_planning(connection, monkeypatch):
    client, _ = connection
    loop = client.portal.call(asyncio.get_running_loop)
    original = loop.run_in_executor
    def interrupted(executor, fn, *args):
        if fn is server.plan_job:
            server.c.stop(False)
        return original(executor, fn, *args)
    monkeypatch.setattr(loop, 'run_in_executor', interrupted)
    result = send(connection, 'movej 3 0 0 0 0 0')
    assert not result['ok'] and result['error']['code'] == 409
    assert server.c.mode == 'READY' and server.c.q[0] == 0


def test_cartesian_commands_and_unreachable_target(connection):
    tcp = send(connection, 'tcp')['data']['position_mm']
    for name in ('moveto', 'movel'):
        result = send(connection, command=name, args={'position_mm': tcp})
        assert result['ok'], result
        connection[0].portal.call(lambda: server.c.advance(60))
    assert not send(connection, 'moveto 10000 10000 10000')['ok']
    assert parse_text('help movej') == ('help', {'name': 'movej'})


def test_release_during_planning_prevents_later_execution(connection, monkeypatch):
    client, headers = connection
    loop = client.portal.call(asyncio.get_running_loop)
    original = loop.run_in_executor
    started = threading.Event()
    unblock = client.portal.call(asyncio.Event)
    def delayed(executor, fn, *args):
        future = original(executor, fn, *args)
        if fn is not server.plan_job:
            return future
        async def hold():
            started.set()
            await unblock.wait()
            return await future
        return loop.create_task(hold())
    monkeypatch.setattr(loop, 'run_in_executor', delayed)
    with ThreadPoolExecutor() as threads:
        response = threads.submit(send, connection, 'movej 3 0 0 0 0 0')
        try:
            assert started.wait(5)
            assert server.c.planning_owner == headers['X-Client']
            client.post('/api/release', headers=headers, json={})
        finally:
            client.portal.call(unblock.set)
        result = response.result(timeout=15)
    assert not result['ok'] and result['error']['code'] == 409
    assert server.c.mode == 'READY' and server.c.q[0] == 0


def test_sdk_cli_real_http_heartbeat_and_exit():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'cyberarm.server:app', '--host', '127.0.0.1', '--port', str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+30
        while True:
            try:
                httpx.get(url+'/api/state', timeout=1, trust_env=False).raise_for_status()
                break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise AssertionError('test server did not start')
                time.sleep(.1)
        with CyberArm(url) as arm:
            assert arm.command(name='joint', args={'index': 1, 'angle_deg': 2})['ok']
            with pytest.raises(CommandError):
                arm.command('joint 1 90')
            plan = arm.preview([{'kind': 'wait', 'seconds': 10}])
            arm.execute(plan)
            time.sleep(2)
            assert arm.state()['mode'] == 'RUNNING'  # SDK maintained >1.5s lease.
        deadline = time.monotonic()+3
        while httpx.get(url+'/api/state', trust_env=False).json()['mode'] != 'PAUSED':
            assert time.monotonic() < deadline
            time.sleep(.05)
        cli = Path(__file__).resolve().parents[1] / 'sdk/cyberarm_cli.py'
        def invoke(line):
            return subprocess.run([sys.executable, str(cli), '--url', url, '--json', '-c', line], capture_output=True, text=True, timeout=30)
        assert invoke('stop').returncode == 0
        movement = invoke('movej 3 0 0 0 0 0')
        assert movement.returncode == 0, movement.stderr
        assert json.loads(movement.stdout)['completion']['q_deg'][0] == pytest.approx(3)
        invalid = invoke('joint 1 90')
        assert invalid.returncode == 2 and not json.loads(invalid.stdout)['ok']
        # An absent heartbeat must pause even if the process cannot release.
        with CyberArm(url) as arm:
            arm.closed.set();arm.worker.join(2)
            plan = arm.preview([{'kind': 'wait', 'seconds': 10}]);arm.execute(plan)
            time.sleep(2)
            assert arm.state()['mode'] == 'PAUSED'
            arm.closed.clear()
        assert invoke('stop').returncode == 0
        moving = subprocess.Popen([sys.executable, str(cli), '--url', url, '--json', '-c', 'movej 20 0 0 0 0 0 0.05'],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with CyberArm(url) as observer:
                deadline = time.monotonic()+15
                while observer.state()['mode'] != 'RUNNING':
                    assert time.monotonic() < deadline
                    time.sleep(.05)
                observer.stop()
            stdout, stderr = moving.communicate(timeout=15)
            assert moving.returncode == 2, stderr
            assert json.loads(stdout)['completion']['execution']['status'] == 'stopped'
        finally:
            if moving.poll() is None:
                moving.terminate();moving.wait(timeout=5)
    finally:
        process.terminate()
        process.wait(timeout=15)
