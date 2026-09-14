"""Local simulator client. Uses the same planning and validation as the UI."""
import threading
import uuid
import httpx

class CyberArm:
    def __init__(self,url='http://127.0.0.1:8765'):
        self.http=httpx.Client(base_url=url,timeout=65)
        bootstrap=self.http.get('/api/bootstrap').raise_for_status().json()
        self.http.headers.update({'X-Session':bootstrap['session'],'X-Client':uuid.uuid4().hex})
        self.closed=threading.Event()
        self.worker=threading.Thread(target=self._heartbeat,daemon=True);self.worker.start()
    def _heartbeat(self):
        while not self.closed.wait(.4):
            try:self.http.post('/api/heartbeat',json={}).raise_for_status()
            except httpx.HTTPError:pass
    def call(self,path,body):return self.http.post('/api/'+path,json=body).raise_for_status().json()
    def state(self):return self.http.get('/api/state').raise_for_status().json()
    def preview(self,steps,speed=.7):return self.call('plan',{'steps':steps,'speed':speed})
    def execute(self,plan):return self.call('execute',{'plan_id':plan['plan_id']})
    def stop(self):return self.call('control',{'action':'stop'})
    def close(self):
        self.closed.set();self.worker.join(timeout=3);self.http.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
