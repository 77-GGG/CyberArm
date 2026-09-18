from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import sys
import numpy as np

ROOT = Path(os.environ.get('CYBERARM_RESOURCE_DIR', Path(__file__).resolve().parents[2]))
PTR = C.POINTER(C.c_double)

def validate_gripper_range(low, high):
    """Reject linkage singularities anywhere in the requested continuous interval.

    These are the same two circle constraints as ca_fk, evaluated analytically
    at endpoints and every interior extremum, not just at a few sample poses.
    """
    for sign, ax, gx, offset, dx, dz in [(1,.013,.005,-155,.03075,0),(-1,.023,.0319,147.5,-.030486231,.00401368)]:
        a=(ax-gx)**2+.02**2+dx**2+dz**2
        b=-2*(ax-gx)*dx-2*.02*dz
        c=-2*(ax-gx)*dz+2*.02*dx
        lo,hi=sorted(np.radians([offset+sign*low,offset+sign*high]))
        critical=np.arctan2(c,b)+np.arange(-5,6)*np.pi
        angles=np.r_[lo,hi,critical[(critical>lo)&(critical<hi)]]
        squared=a+b*np.cos(angles)+c*np.sin(angles)
        if np.min(squared)<=(.009+1e-6)**2 or np.max(squared)>=(.053-1e-6)**2:
            raise ValueError('夹爪范围经过当前连杆模型的无解或奇异位置，请缩小 G 范围；舵机行程不等于夹爪机构行程')
def pointer(a): return a.ctypes.data_as(PTR)

class Robot:
    def __init__(self):
        path=ROOT/'assets/revc/robot.json'
        self.data=json.loads(path.read_text(encoding='utf-8'))
        self.version=hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        names = {'win32': ['libcyberarm_core.dll', 'cyberarm_core.dll'],
                 'darwin': ['libcyberarm_core.dylib']}.get(sys.platform, ['libcyberarm_core.so'])
        candidates = [ROOT/'core'/name for name in names] + [ROOT/'core/build'/name for name in names]
        library = next((p for p in candidates if p.is_file()), None)
        if library is None: raise FileNotFoundError('找不到目标平台的 CyberArm 核心库：'+str(ROOT/'core'))
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

    def apply_limits(self, limits):
        if limits is None:return
        value=np.asarray(limits,dtype=float)
        if value.shape!=(6,2) or not np.isfinite(value).all() or np.any(value[:,0]>=value[:,1]) or np.any(np.abs(value)>180):
            raise ValueError('实机有效范围无效')
        validate_gripper_range(*value[5])
        # The server supplies authoritative, already intersected runtime limits.
        # Intersecting again with robot.json would silently restore the old cap.
        self.limits=np.radians(value)

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
