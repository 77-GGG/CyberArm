"""Bounded IK and immutable, conservatively checked simulation trajectories."""
import itertools
import time
import json
import ctypes as C
from functools import lru_cache
import numpy as np
from scipy.optimize import least_squares
from .model import Robot, ROOT, pointer

class Rejected(ValueError): pass

@lru_cache(maxsize=1)
def collision_arrays():
    with np.load(ROOT/"assets/revc/collision.npz",allow_pickle=False) as data:
        return {key:np.ascontiguousarray(data[key]) for key in data.files}

class Geometry:
    def __init__(self, robot, obstacles):
        self.r=robot
        meshes=robot.data['meshes']
        self.names=[m['source'] for m in meshes]
        self.frames=np.array([m['frame'] for m in meshes])
        bounds=np.array([m['bounds'] for m in meshes])
        self.center=bounds.mean(axis=1); self.half=np.diff(bounds,axis=1)[:,0]/2
        self.obstacles=obstacles
        # Only explicit mechanical attachments / gear meshing are allowed.
        # Moving pins share the body of the linkage which carries their centre.
        pin_groups={5:4,9:6,10:7,14:11,15:12}
        groups=np.array([pin_groups.get(int(f),int(f)) for f in self.frames])
        contacts={frozenset(pair) for pair in [(-1,0),(0,1),(1,2),(2,3),(3,4),
                  (4,6),(4,7),(4,11),(4,12),(6,11),(6,8),(7,8),(11,13),(12,13)]}
        self.pairs=np.array([(i,j) for i,j in itertools.combinations(range(len(meshes)),2)
                             if groups[i]!=groups[j] and frozenset((groups[i],groups[j])) not in contacts],dtype=int)
        self.floor=float(bounds[:,0,2].min()-.002)
        self.trees=collision_arrays()

    def surface_gap(self,i,j,transforms,ceiling):
        def args(index):
            data=self.trees
            return [pointer(np.ascontiguousarray(transforms[index])),pointer(data[f'b{index}']),
                    data[f'c{index}'].ctypes.data_as(C.POINTER(C.c_int)),
                    data[f'f{index}'].ctypes.data_as(C.POINTER(C.c_int)),pointer(data[f't{index}'])]
        return self.r.lib.ca_mesh_gap(*args(i),*args(j),ceiling)

    @staticmethod
    def triangle_gap(x,y):
        ex=np.roll(x,-1,axis=0)-x;ey=np.roll(y,-1,axis=0)-y
        nx=np.cross(ex[0],ex[1]);ny=np.cross(ey[0],ey[1])
        axes=np.array([nx,ny,*[np.cross(a,b) for a in ex for b in ey],
                       *[np.cross(nx,a) for a in ex],*[np.cross(ny,b) for b in ey]])
        norms=np.linalg.norm(axes,axis=1);axes=axes[norms>1e-16]/norms[norms>1e-16,None]
        if len(axes)==0:return 0.
        px=x@axes.T;py=y@axes.T
        return float(np.max(np.maximum(px.min(axis=0)-py.max(axis=0),py.min(axis=0)-px.max(axis=0))))

    def boxes(self,q):
        frames,_=self.r.fk(q)
        transforms=frames@self.r.invzero
        transforms=np.concatenate([transforms,np.eye(4)[None]])
        t=transforms[np.where(self.frames<0,16,self.frames)]
        c=np.einsum('nij,nj->ni',t[:,:3,:3],self.center)+t[:,:3,3]
        axes=t[:,:3,:3]
        ext=np.einsum('nij,nj->ni',np.abs(axes),self.half)
        return c,axes,ext,t

    @staticmethod
    def gap(ca,aa,ha,cb,ab,hb):
        axes=[*aa.T,*ab.T]
        axes.extend(np.cross(a,b) for a in aa.T for b in ab.T)
        best=-1e6
        for a in axes:
            n=np.linalg.norm(a)
            if n<1e-8: continue
            a=a/n
            g=abs((cb-ca)@a)-np.abs(aa.T@a)@ha-np.abs(ab.T@a)@hb
            best=max(best,float(g))
        return best

    def clearance(self,q,delta=None):
        c,a,e,transforms=self.boxes(q)
        delta=np.zeros(6) if delta is None else np.abs(delta)
        influence=np.array([[f>=k if k<5 else f>=6 for k in range(6)] for f in self.frames])
        # Shared upstream rotations preserve pair distance. World vertical
        # clearance is also invariant under the vertical base-yaw joint.
        floor_influence=influence.copy();floor_influence[:,0]=False
        padding=.7*(floor_influence@delta)
        floor=c[:,2]-e[:,2]-self.floor
        floor=np.where((self.frames<0)&(floor>.0002),np.inf,floor)
        floor-=padding
        best=min(.000201,float(floor.min())); names=(self.names[int(floor.argmin())],'地面')
        for i,j in self.pairs:
            relative=np.logical_xor(influence[i],influence[j]);relative[5]=influence[i,5] or influence[j,5]
            pad=.7*float(relative@delta)
            coarse=float(np.max(np.abs(c[i]-c[j])-e[i]-e[j]))
            if coarse-pad>=best:continue
            gap=self.surface_gap(i,j,transforms,best+pad)-pad
            if gap<best:best=gap;names=(self.names[i],self.names[j])
        for o in self.obstacles:
            oc=np.array(o['center']);oh=np.array(o['size'])/2
            pads=.7*(influence@delta)
            gaps=np.max(np.abs(c-oc)-e-oh,axis=1)-pads
            for i in np.flatnonzero(gaps<best):
                gap=self.gap(c[i],a[i],self.half[i],oc,np.eye(3),oh)-pads[i]
                if gap<best:best=gap;names=(self.names[i],o['name'])
        return best,names

    def check_segment(self,start,end,deadline):
        # A 2 m/rad global displacement bound per joint covers this <0.5 m arm
        # including the closed-chain jaw over the configured +/-8 degree interval.
        stack=[(np.asarray(start),np.asarray(end),0)]; count=0
        while stack:
            if time.monotonic()>deadline:raise Rejected('路径检查超时；未确认安全，已拒绝')
            lo,hi,depth=stack.pop();mid=(lo+hi)/2
            gap,names=self.clearance(mid,(hi-lo)/2);count+=1
            if gap>.0002:continue
            actual,names=self.clearance(mid)
            if actual<=.0002:raise Rejected('碰撞包络或间隙不足：'+' / '.join(names))
            if depth>=17:raise Rejected('路径间隙无法确认，已拒绝')
            stack.extend([(lo,mid,depth+1),(mid,hi,depth+1)])
        return count

def inverse(robot,target,start,direction=None,attempts=7):
    target=np.asarray(target,dtype=float);start=np.asarray(start,dtype=float)
    if target.shape!=(3,) or not np.isfinite(target).all():raise Rejected('目标坐标非法')
    direction=None if direction is None else np.asarray(direction,dtype=float)
    if direction is not None:
        if direction.shape!=(3,) or not np.isfinite(direction).all() or np.linalg.norm(direction)<1e-8:raise Rejected('工具方向非法')
        direction=direction/np.linalg.norm(direction)
    def residual(x):
        _,t=robot.fk(np.r_[x,start[5]])
        position=(t[:3,3]-target)*10
        return position if direction is None else np.r_[position,t[:3,2]-direction]
    rng=np.random.default_rng(20260914)
    seeds=[np.clip(start[:5],robot.limits[:5,0],robot.limits[:5,1]),np.zeros(5)]
    seeds.extend(rng.uniform(robot.limits[:5,0],robot.limits[:5,1]) for _ in range(attempts-2))
    best=None
    for seed in seeds:
        result=least_squares(residual,seed,bounds=(robot.limits[:5,0],robot.limits[:5,1]),max_nfev=200,gtol=1e-10,ftol=1e-10,xtol=1e-10)
        q=np.r_[result.x,start[5]];_,tcp=robot.fk(q)
        error=float(np.linalg.norm(tcp[:3,3]-target))
        angle=0. if direction is None else float(np.arccos(np.clip(tcp[:3,2]@direction,-1,1)))
        if best is None or error<best[0]:best=(error,angle)
        if error<=.0005 and angle<=np.radians(.5):return q,{'position_mm':error*1000,'direction_deg':float(np.degrees(angle))}
    raise Rejected(f'未找到满足约束的解；最佳位置误差 {best[0]*1000:.3f} mm，方向误差 {np.degrees(best[1]):.3f}°')

def plan_job(payload):
    r=Robot();start=np.array(payload['start']);obstacles=payload['obstacles']
    geo=Geometry(r,obstacles);deadline=time.monotonic()+45
    steps=payload['steps'];q=start.copy();segments=[];path=[];checks=0;elapsed=0.;residuals=[]
    if not r.within(q):raise Rejected('当前状态超出模拟限制')
    gap,names=geo.clearance(q)
    if gap<=.0002:raise Rejected('初始场景包络干涉：'+' / '.join(names))
    for step in steps:
        if step['kind']=='wait':
            duration=step['seconds'];segments.append({'start':q.tolist(),'end':q.tolist(),'duration':duration,'at':elapsed});elapsed+=duration;continue
        targets=[]
        if step['kind']=='joint':targets=[np.radians(step['q_deg'])]
        elif step['kind'] in ('cartesian','linear'):
            target=np.array(step['position_mm'])/1000
            direction=step.get('direction')
            if step['kind']=='cartesian':
                dest,err=inverse(r,target,q,direction);targets=[dest];residuals.append(err)
            else:
                origin=r.fk(q)[1][:3,3];last=q.copy()
                for alpha in np.linspace(0,1,max(2,int(np.ceil(np.linalg.norm(target-origin)/.002))+1))[1:]:
                    dest,err=inverse(r,origin+(target-origin)*alpha,last,direction)
                    v=target-origin
                    endpoint_error=0.
                    for candidate in (last,dest):
                        p=r.fk(candidate)[1][:3,3];beta=np.clip((p-origin)@v/max(v@v,1e-18),0,1)
                        endpoint_error=max(endpoint_error,float(np.linalg.norm(p-origin-beta*v)))
                    # The second derivative bound for this <0.7 m serial chain
                    # certifies the entire joint segment, including between samples.
                    curve_bound=.7*float(np.abs(dest[:5]-last[:5]).sum())**2/8
                    if endpoint_error+curve_bound>.0005:raise Rejected('无法确认整段直线精度，请缩短距离或调整目标')
                    # Check actual joint-interpolated curve against the straight line.
                    for u in np.linspace(0,1,9):
                        p=r.fk(last+(dest-last)*u)[1][:3,3]
                        v=target-origin;beta=np.clip((p-origin)@v/max(v@v,1e-18),0,1)
                        if np.linalg.norm(p-origin-beta*v)>.0004:raise Rejected('直线插补误差超过保守阈值，请缩短目标距离')
                    targets.append(dest);last=dest;residuals.append(err)
        for dest in targets:
            if not r.within(dest):raise Rejected('目标关节或夹爪超出模拟限制')
            checks+=geo.check_segment(q,dest,deadline)
            duration=r.duration(q,dest)/payload['speed']
            segments.append({'start':q.tolist(),'end':dest.tolist(),'duration':duration,'at':elapsed})
            for u in np.linspace(0,1,15):path.append((r.fk(q+(dest-q)*u)[1][:3,3]).tolist())
            elapsed+=duration;q=dest
    if not segments:raise Rejected('动作序列为空')
    return {'segments':segments,'duration':elapsed,'end':q.tolist(),'path':path,'checks':checks,'residuals':residuals}

def workspace_job(payload):
    r=Robot();rng=np.random.default_rng(14);points=[]
    direction=payload.get('direction')
    direction=None if direction is None else np.array(direction)/np.linalg.norm(direction)
    for _ in range(3500):
        q=rng.uniform(r.limits[:,0],r.limits[:,1]);t=r.fk(q)[1]
        if direction is None or np.degrees(np.arccos(np.clip(t[:3,2]@direction,-1,1)))<=5:points.append(t[:3,3].tolist())
    return {'points':points,'label':'关节限位下的运动学采样；方向筛选容差 5°；未扣除碰撞，不能作为执行许可'}
