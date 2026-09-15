"""Local command client with a replaceable transport. Never retries motion."""
import threading
from typing import Protocol
import uuid
import httpx


class Transport(Protocol):
    def get(self, path: str): ...
    def post(self, path: str, body: dict): ...
    def close(self): ...


class HttpTransport:
    def __init__(self,url='http://127.0.0.1:8765'):
        self.http=httpx.Client(base_url=url,timeout=65,trust_env=False)
        try:
            bootstrap=self.get('bootstrap')
            self.http.headers.update({'X-Session':bootstrap['session'],'X-Client':uuid.uuid4().hex})
        except Exception:
            self.http.close()
            raise
    def get(self,path):return self.http.get('/api/'+path).raise_for_status().json()
    def post(self,path,body):return self.http.post('/api/'+path,json=body).raise_for_status().json()
    def close(self):self.http.close()


class CommandError(Exception):
    def __init__(self,response):
        self.response=response
        super().__init__(response['error']['message'])


class CyberArm:
    def __init__(self,url='http://127.0.0.1:8765',*,transport:Transport|None=None):
        self.transport=transport if transport is not None else HttpTransport(url)
        self.closed=threading.Event()
        self.worker=threading.Thread(target=self._heartbeat,daemon=True);self.worker.start()
    def _heartbeat(self):
        while not self.closed.wait(.4):
            try:self.call('heartbeat',{})
            except (httpx.HTTPError,OSError):pass
    def call(self,path,body):return self.transport.post(path,body)
    def state(self):return self.transport.get('state')
    def commands(self):return self.transport.get('commands')
    def command(self,text=None,*,name=None,args=None,request_id=None):
        if (text is None)==(name is None) or (text is not None and args is not None):
            raise ValueError('Provide text OR name and args')
        body={'protocol_version':1,'request_id':request_id or uuid.uuid4().hex}
        body.update({'text':text} if text is not None else {'command':name,'args':args or {}})
        response=self.call('command',body)
        if not response['ok']:raise CommandError(response)
        return response
    def preview(self,steps,speed=.7):return self.call('plan',{'steps':steps,'speed':speed})
    def execute(self,plan):return self.call('execute',{'plan_id':plan['plan_id']})
    def stop(self):return self.call('control',{'action':'stop'})
    def close(self):
        if self.closed.is_set():return
        self.closed.set()
        try:self.call('release',{})
        except (httpx.HTTPError,OSError):pass
        self.worker.join(timeout=3);self.transport.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
