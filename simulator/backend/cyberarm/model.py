from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RESOURCE_ROOT = Path(os.environ.get('CYBERARM_RESOURCE_DIR', ROOT))
PTR = C.POINTER(C.c_double)
def pointer(a): return a.ctypes.data_as(PTR)

class Robot:
    def __init__(self):
        path=RESOURCE_ROOT/'assets/revc/robot.json'
        self.data=json.loads(path.read_text(encoding='utf-8'))
        self.version=hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        library = RESOURCE_ROOT/'core/libcyberarm_core.dll' if (RESOURCE_ROOT/'core/libcyberarm_core.dll').exists() else ROOT/'core/build/libcyberarm_core.dll'
        self.lib=C.CDLL(str(library))
        self.lib.ca_fk.argtypes=[PTR]*6;self.lib.ca_fk.restype=C.c_int
        self.lib.ca_curve.argtypes=[C.c_double,C.c_double,PTR];self.lib.ca_curve.restype=C.c_int
        self.lib.ca_segment_distance.argtypes=[PTR]*4;self.lib.ca_segment_distance.restype=C.c_double
        self.lib.ca_mesh_gap.argtypes=[PTR,PTR,C.POINTER(C.c_int),C.POINTER(C.c_int),PTR]*2+[C.c_double]
        self.lib.ca_mesh_gap.restype=C.c_double
        self.joints=np.array(self.data['joint_local'],dtype=np.float64)
        self.palm=np.array(self.data['palm_local'],dtype=np.float64)
        self.tool=np.array(self.data['tcp_local'],dtype=np.float64)
        self.zero=np.array(self.data['zero_frames'],dtype=np.float64)
        self.invzero=np.linalg.inv(self.zero)
        self.limits=np.radians(self.data['limits_deg'])
        self.vmax=np.radians(self.data['max_velocity_deg_s'])
        self.amax=np.radians(self.data['max_acceleration_deg_s2'])

    def fk(self,q):
        q=np.ascontiguousarray(q,dtype=np.float64)
        if q.shape!=(6,) or not np.isfinite(q).all():raise ValueError('关节数组必须含六个有限值')
        frames=np.empty((16,4,4));tcp=np.empty((4,4))
        result=self.lib.ca_fk(pointer(q),pointer(self.joints),pointer(self.palm),pointer(self.tool),pointer(frames),pointer(tcp))
        if result:raise ValueError('运动学输入无效或夹爪闭链无解')
        return frames,tcp

    def curve(self,t,duration):
        out=np.empty(3)
        if self.lib.ca_curve(t,duration,pointer(out)):raise ValueError('轨迹时间非法')
        return out

    def within(self,q):
        q=np.asarray(q)
        return q.shape==(6,) and np.isfinite(q).all() and np.all(q>=self.limits[:,0]-1e-10) and np.all(q<=self.limits[:,1]+1e-10)

    def duration(self,q0,q1):
        d=np.abs(np.asarray(q1)-q0)
        return float(max(.15,np.max(1.875*d/(self.vmax*.65)),np.max(np.sqrt(5.773503*d/(self.amax*.35)))))

    def transforms(self,q):
        f,t=self.fk(q)
        return (f@self.invzero).reshape(16,16).tolist(),t.tolist()
