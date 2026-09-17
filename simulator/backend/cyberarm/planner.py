"""Bounded IK and immutable, conservatively checked simulation trajectories."""
import itertools
import threading
import time
import ctypes as C
from functools import lru_cache
import numpy as np
from .model import Robot, ROOT, pointer

class Rejected(ValueError): pass

# A point of this <0.5 m arm travels at most this many metres per radian of
# joint motion. Multiplying a joint interval by it bounds how far one body of a
# checked pair can move relative to the other inside that interval. The
# gripper linkage is measured separately, see gripper_sweep_radii.
SWEEP_PER_RADIAN=.7
# The closed chain moves every jaw body rigidly with the gripper joint frame,
# so its speed is a function of that one angle and can be measured instead of
# estimated. A narrow-phase query is billed per millimetre of ceiling, so the
# measured value, which is close to the part size, pays for itself.
GRIPPER_SWEEP_SAMPLES=129
GRIPPER_SWEEP_MARGIN=1.25
# A narrow-phase query gets more expensive the larger its ceiling, so a checked
# segment is first cut into pieces whose sweep padding stays near this size.
PAD_TARGET=.004
# 1 mm of position error and 1 radian of tool direction error cost about the
# same, so the solver cannot trade position away for orientation.
POSITION_GAIN=1000.
# Deepest bisection a node that still looks close may be refined to.
MAX_DEPTH=17
# A warm start is a few Newton steps away from the answer, so the residual only
# has to reach a thousandth of a millimetre before the answer is handed on.
POLISH_TOLERANCE=1e-3
POLISH_ITERATIONS=40
POLISH_BACKTRACK=8
INT_PTR=C.POINTER(C.c_int)

_SOLVER=None

def least_squares_solver():
    """The trust-region least-squares solver, imported the first time it is used.

    Importing scipy.optimize costs about 0.6 s, which is most of a planning
    worker's one-time start-up. Only a cold seed needs the generic solver: a
    joint move never calls the inverse kinematics at all, and a reachable cartesian
    target is answered by the damped Gauss-Newton polish, so the import is kept
    out of the path that the first preview of a session actually takes. The
    module is cached after the first use, so later calls are a name lookup. The
    frozen build lists scipy.optimize explicitly, because a function-level
    import is easier for a bundler to miss than a module-level one.
    """
    global _SOLVER
    if _SOLVER is None:
        from scipy.optimize import least_squares
        _SOLVER=least_squares
    return _SOLVER

@lru_cache(maxsize=1)
def collision_arrays():
    with np.load(ROOT/"assets/revc/collision.npz",allow_pickle=False) as data:
        return {key:np.ascontiguousarray(data[key]) for key in data.files}

@lru_cache(maxsize=1)
def gripper_sweep_radii():
    """Per-mesh travel per radian of the gripper joint, measured not assumed.

    The jaws, links and gears of the gripper form a closed chain which the
    gripper joint drives on its own, so every gripper body is rigidly carried by
    one chain frame and its pose relative to the palm is a function of that
    single angle. Scanning the joint range therefore covers the whole reachable
    set of gripper poses, and turning the base joints only rotates the measured
    speed, so one scan at the zero pose bounds every pose. The speed varies
    smoothly with the angle, so the largest secant between neighbouring scan
    points is the largest speed up to the scan spacing, and the margin covers
    the rest. The generic SWEEP_PER_RADIAN estimate is an order of magnitude
    larger here, and a narrow phase query is billed per millimetre of ceiling.
    """
    robot=Robot()
    positions=np.linspace(robot.limits[5,0],robot.limits[5,1],GRIPPER_SWEEP_SAMPLES)
    frames=np.stack([robot.fk(np.r_[np.zeros(5),angle])[0] for angle in positions])
    step=float(positions[1]-positions[0])
    meshes=robot.data['meshes']
    bounds=np.array([mesh['bounds'] for mesh in meshes])
    center=bounds.mean(axis=1);half=np.diff(bounds,axis=1)[:,0]/2
    signs=np.array([(x,y,z) for x in (1,-1) for y in (1,-1) for z in (1,-1)],dtype=np.float64)
    corners=center[:,None,:]+half[:,None,:]*signs
    radii=np.zeros(len(meshes))
    for index,mesh in enumerate(meshes):
        frame=int(mesh['frame'])
        if frame<6:continue
        # The body is rigid with this chain frame, and speed is convex in the
        # point, so the fastest corner of the bounding box bounds every point.
        transform=np.matmul(frames[:,frame],robot.invzero[frame])
        points=np.einsum('sij,cj->sci',transform[:,:3,:3],corners[index])+transform[:,:3,3][:,None,:]
        radii[index]=GRIPPER_SWEEP_MARGIN*float(np.max(np.linalg.norm(np.diff(points,axis=0),axis=2)))/step
    return radii

def warm_worker():
    """Pay a planning worker's one-time costs before the first preview.

    A worker that runs its very first job has to import the planner and
    decompress the 140 MB collision archive, which together are about a second.
    Both results are cached per process, so doing it while the window is still
    opening keeps that second off the first click of the preview button.

    The trust-region solver is a third, separate cost: importing scipy.optimize
    takes about 0.6 s, and only a cold seed ever calls it, so it is loaded here
    on a background thread rather than in the path of the first preview. A
    reachable target never waits for it, and an unreachable one finds it ready
    instead of paying for it after the user has already asked for an answer.
    """
    collision_arrays()
    gripper_sweep_radii()
    threading.Thread(target=least_squares_solver,daemon=True).start()
    return True

class Geometry:
    def __init__(self, robot, obstacles):
        self.r=robot;self.lib=robot.lib
        meshes=robot.data['meshes']
        self.names=[m['source'] for m in meshes]
        self.frames=np.array([m['frame'] for m in meshes])
        bounds=np.array([m['bounds'] for m in meshes])
        self.center=bounds.mean(axis=1); self.half=np.diff(bounds,axis=1)[:,0]/2
        self.obstacles=obstacles
        # Chain frame of every mesh; negative frames sit on the fixed base.
        self.mesh_frame=np.where(self.frames<0,16,self.frames)
        # Only explicit mechanical attachments / gear meshing are allowed.
        # Moving pins share the body of the linkage which carries their centre.
        pin_groups={5:4,9:6,10:7,14:11,15:12}
        groups=np.array([pin_groups.get(int(f),int(f)) for f in self.frames])
        contacts={frozenset(pair) for pair in [(-1,0),(0,1),(1,2),(2,3),(3,4),
                  (4,6),(4,7),(4,11),(4,12),(6,11),(6,8),(7,8),(11,13),(12,13)]}
        self.pairs=np.array([(i,j) for i,j in itertools.combinations(range(len(meshes)),2)
                             if groups[i]!=groups[j] and frozenset((groups[i],groups[j])) not in contacts],dtype=int)
        self.pi=np.ascontiguousarray(self.pairs[:,0]);self.pj=np.ascontiguousarray(self.pairs[:,1])
        self.floor=float(bounds[:,0,2].min()-.002)
        data=collision_arrays()
        # Joint influence per mesh, so a query only has to do arithmetic.
        influence=np.zeros((len(self.frames),6))
        for k in range(5):influence[:,k]=self.frames>=k
        influence[:,5]=self.frames>=6
        self.influence=influence
        # Joints that move both bodies of a pair turn it rigidly, which leaves
        # their mutual distance unchanged, so only the exclusive ones count.
        relative=np.abs(influence[self.pi]-influence[self.pj])
        relative[:,5]=np.maximum(influence[self.pi,5],influence[self.pj,5])
        self.relative=relative
        floor_influence=influence.copy();floor_influence[:,0]=0.
        self.floor_influence=floor_influence
        # Distance either body of a pair can travel per radian of each joint.
        # Every joint except the gripper joint uses the generic estimate; the
        # gripper joint carries the closed chain, whose speed is measured, and
        # a pair whose two bodies both move with it is padded with both.
        gripper=gripper_sweep_radii()
        self.sweep=self.relative*SWEEP_PER_RADIAN
        self.sweep[:,5]=gripper[self.pi]+gripper[self.pj]
        self.floor_sweep=self.floor_influence*SWEEP_PER_RADIAN
        self.floor_sweep[:,5]=gripper
        self.mesh_sweep=self.influence*SWEEP_PER_RADIAN
        self.mesh_sweep[:,5]=gripper
        # Constant ctypes arguments per mesh; only the transform pointer changes
        # between queries.
        self.static=[(pointer(data[f'b{k}']),data[f'c{k}'].ctypes.data_as(INT_PTR),
                      data[f'f{k}'].ctypes.data_as(INT_PTR),pointer(data[f't{k}']))
                     for k in range(len(self.frames))]

    def surface_gap(self,i,j,transforms,ceiling):
        ai=self.static[i];aj=self.static[j]
        return self.lib.ca_mesh_gap(pointer(transforms[i]),ai[0],ai[1],ai[2],ai[3],
                                    pointer(transforms[j]),aj[0],aj[1],aj[2],aj[3],ceiling)

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
        transforms=np.empty((17,4,4))
        np.matmul(frames,self.r.invzero,out=transforms[:16])
        transforms[16]=np.eye(4)
        # One world transform per mesh, which is what the narrow phase indexes.
        t=transforms[self.mesh_frame]
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
        c,a,e,t=self.boxes(q)
        count=len(self.pairs);pads=None;mesh_pads=None;pad_floor=None
        if delta is not None:
            d=np.abs(np.asarray(delta,dtype=np.float64))
            if d.any():
                pad_floor=self.floor_sweep@d
                if count:pads=self.sweep@d
                if self.obstacles:mesh_pads=self.mesh_sweep@d
        # World vertical clearance is invariant under the vertical base-yaw joint.
        floor=c[:,2]-e[:,2]-self.floor
        floor=np.where((self.frames<0)&(floor>.0002),np.inf,floor)
        if pad_floor is not None:floor=floor-pad_floor
        best=min(.000201,float(floor.min())); names=(self.names[int(floor.argmin())],'地面')
        if count:
            # Axis aligned box separation bounds the exact surface gap from
            # below, so it prunes pairs before the narrow phase is entered. The
            # narrow phase can only answer min(ceiling,gap), so its ceiling has
            # to stay best+pad to reproduce the padded gap bit for bit.
            coarse=np.max(np.abs(c[self.pi]-c[self.pj])-e[self.pi]-e[self.pj],axis=1)
            lower=coarse if pads is None else coarse-pads
            candidates=np.flatnonzero(lower<best)
            order=candidates[np.argsort(lower[candidates],kind='stable')] if len(candidates) else candidates
            for index in order:
                if lower[index]>=best:break
                i=int(self.pi[index]);j=int(self.pj[index])
                pad=0. if pads is None else pads[index]
                gap=float(self.surface_gap(i,j,t,best+pad)-pad)
                if gap<best:best=gap;names=(self.names[i],self.names[j])
        for o in self.obstacles:
            oc=np.array(o['center']);oh=np.array(o['size'])/2
            gaps=np.max(np.abs(c-oc)-e-oh,axis=1)
            if mesh_pads is not None:gaps=gaps-mesh_pads
            for i in np.flatnonzero(gaps<best):
                gap=self.gap(c[i],a[i],self.half[i],oc,np.eye(3),oh)-(0. if mesh_pads is None else mesh_pads[i])
                if gap<best:best=gap;names=(self.names[i],o['name'])
        return best,names

    def check_segment(self,start,end,deadline):
        start=np.asarray(start,dtype=np.float64);end=np.asarray(end,dtype=np.float64)
        # Sweep padding makes a wide node expensive without making it more
        # informative, so the segment is cut up front into pieces whose padding
        # is small. Every piece is then cheap: the coarse filter usually
        # certifies it without entering the narrow phase at all, and only a
        # piece that still looks close is refined by bisection.
        span=float(np.abs(end-start).sum())
        pieces=max(1,int(np.ceil(span*SWEEP_PER_RADIAN/PAD_TARGET)))
        step=(end-start)/pieces
        stack=[(start+step*k,start+step*(k+1),0) for k in range(pieces)]
        count=0
        while stack:
            if time.monotonic()>deadline:raise Rejected('路径检查超时；未确认安全，已拒绝')
            lo,hi,depth=stack.pop();mid=(lo+hi)/2
            gap,names=self.clearance(mid,hi-lo);count+=1
            if gap>.0002:continue
            actual,names=self.clearance(mid)
            if actual<=.0002:raise Rejected('碰撞包络或间隙不足：'+' / '.join(names))
            if depth>=MAX_DEPTH:raise Rejected('路径间隙无法确认，已拒绝')
            stack.extend([(lo,mid,depth+1),(mid,hi,depth+1)])
        return count

def inverse(robot,target,start,direction=None,attempts=7,deadline=None):
    target=np.asarray(target,dtype=float);start=np.asarray(start,dtype=float)
    if target.shape!=(3,) or not np.isfinite(target).all():raise Rejected('目标坐标非法')
    direction=None if direction is None else np.asarray(direction,dtype=float)
    if direction is not None:
        if direction.shape!=(3,) or not np.isfinite(direction).all() or np.linalg.norm(direction)<1e-8:raise Rejected('工具方向非法')
        direction=direction/np.linalg.norm(direction)
    def system(x):
        if deadline is not None and time.monotonic()>=deadline:
            raise Rejected('本次求解时间已用完，尚未找到有效解')
        # Every joint turns about the local z axis of its own chain frame, so the
        # task Jacobian follows from a single forward kinematics evaluation
        # instead of the finite differences least_squares would fall back to.
        frames,tcp=robot.fk(np.r_[x,start[5]])
        p=tcp[:3,3];z=tcp[:3,2]
        position=(p-target)*POSITION_GAIN
        jacobian=np.empty((6 if direction is not None else 3,5))
        # Both cross products are taken for all five axes at once; the loop
        # version spent more time in numpy dispatch than in arithmetic.
        axes=frames[:5,:3,2];origins=frames[:5,:3,3]
        np.multiply(np.cross(axes,p-origins).T,POSITION_GAIN,out=jacobian[0:3])
        if direction is not None:np.copyto(jacobian[3:6],np.cross(axes,z).T)
        return (position if direction is None else np.r_[position,z-direction]),jacobian
    # least_squares takes the residual and the Jacobian as separate callables,
    # so the last evaluation is remembered and shared instead of solving twice.
    last=[None]
    def fun(x):
        residual,jacobian=system(x)
        last[0]=(np.array(x,copy=True),jacobian)
        return residual
    def jac(x):
        cached=last[0]
        if cached is not None and np.array_equal(cached[0],x):return cached[1]
        return system(x)[1]
    rng=np.random.default_rng(20260914)
    lower=robot.limits[:5,0];upper=robot.limits[:5,1]
    def polish(seed):
        # Damped Gauss-Newton with a backtracking step, which is all a seed that
        # already sits near the answer needs. The generic trust-region solver
        # spends most of a millisecond per iteration on bookkeeping that only
        # pays off for the cold seeds, so it is kept for those.
        x=np.clip(np.asarray(seed,dtype=float),lower,upper)
        residual,jacobian=system(x);cost=float(residual@residual);damping=1e-6
        for _ in range(POLISH_ITERATIONS):
            if float(np.max(np.abs(residual)))<=POLISH_TOLERANCE:return x
            normal=jacobian.T@jacobian;gradient=jacobian.T@residual
            scale=max(float(np.trace(normal))/5,1e-12)
            for _ in range(POLISH_BACKTRACK):
                try:step=np.linalg.solve(normal+damping*scale*np.eye(5),gradient)
                except np.linalg.LinAlgError:return None
                candidate=np.clip(x-step,lower,upper)
                trial_residual,trial_jacobian=system(candidate)
                trial_cost=float(trial_residual@trial_residual)
                if trial_cost<cost:break
                damping=min(damping*10.,1e10)
            else:return None
            x=candidate;residual=trial_residual;jacobian=trial_jacobian;cost=trial_cost
            damping=max(damping*.3,1e-10)
        return x if float(np.max(np.abs(residual)))<=POLISH_TOLERANCE else None
    seeds=[np.clip(start[:5],lower,upper)]
    if attempts>1:seeds.append(np.zeros(5))
    seeds.extend(rng.uniform(lower,upper) for _ in range(max(0,attempts-2)))
    polished=polish(seeds[0])
    if polished is not None:
        candidate=np.r_[polished,start[5]];_,tcp=robot.fk(candidate)
        error=float(np.linalg.norm(tcp[:3,3]-target))
        angle=0. if direction is None else float(np.arccos(np.clip(tcp[:3,2]@direction,-1,1)))
        if error<=.0005 and angle<=np.radians(.5):
            return candidate,{'position_mm':error*1000,'direction_deg':float(np.degrees(angle))}
        # The polished joints are a better cold start than either end point.
        seeds.insert(1,polished)
    best=None
    solver=least_squares_solver()
    for seed in seeds:
        result=solver(fun,seed,jac=jac,bounds=(lower,upper),
                              max_nfev=200,gtol=1e-9,ftol=1e-9,xtol=1e-9)
        q=np.r_[result.x,start[5]];_,tcp=robot.fk(q)
        error=float(np.linalg.norm(tcp[:3,3]-target))
        angle=0. if direction is None else float(np.arccos(np.clip(tcp[:3,2]@direction,-1,1)))
        if best is None or error<best[0]:best=(error,angle)
        if error<=.0005 and angle<=np.radians(.5):return q,{'position_mm':error*1000,'direction_deg':float(np.degrees(angle))}
    raise Rejected(f'未找到满足约束的解；最佳位置误差 {best[0]*1000:.3f} mm，方向误差 {np.degrees(best[1]):.3f}°')

def tcp_frames(robot,points):
    """Tool transforms for many five-joint samples in one vectorised pass.

    The tool centre only depends on the five serial joints, so the chain is five
    local frames and five z rotations, which numpy can evaluate for every sample
    of a path at once instead of paying one library call per sample.
    """
    points=np.asarray(points,dtype=np.float64)
    if len(points)==0:return np.zeros((0,4,4))
    rotations=np.zeros((len(points),5,4,4))
    cosine=np.cos(points);sine=np.sin(points)
    rotations[:,:,0,0]=cosine;rotations[:,:,1,1]=cosine
    rotations[:,:,0,1]=-sine;rotations[:,:,1,0]=sine
    rotations[:,:,2,2]=1.;rotations[:,:,3,3]=1.
    frames=np.broadcast_to(np.eye(4),(len(points),4,4)).copy()
    for k in range(5):frames=np.matmul(np.matmul(frames,robot.joints[k]),rotations[:,k])
    return np.matmul(np.matmul(frames,robot.palm),robot.tool)

def straight_waypoints(robot,origin,target,start,direction,max_depth=6,min_span=.002):
    """Joint waypoints whose interpolation follows the straight line within bounds.

    The move is first attempted as one joint-space segment. Whenever the sampled
    deviation from the line or the second derivative bound exceeds the accepted
    tolerance the segment is bisected, so the number of inverse kinematics solves
    stays proportional to the curvature of the path instead of its length.
    """
    line=np.asarray(target,dtype=float)-origin
    span=float(np.linalg.norm(line))
    # A zero-length MoveL is still a valid checked hold. Run the usual
    # endpoint/direction verification instead of dropping the only segment.
    square=max(float(line@line),1e-18);out=[]
    samples=max(9,min(801,int(np.ceil(span/.0005))+1))
    def deviation(q0,q1):
        # Largest distance between the interpolated tool path and the line.
        u=np.linspace(0,1,samples)
        tool=tcp_frames(robot,q0[:5]+(q1[:5]-q0[:5])*u[:,None])[:,:3,3]
        beta=np.clip(((tool-origin)@line)/square,0.,1.)
        return float(np.max(np.linalg.norm(tool-origin-beta[:,None]*line,axis=1)))
    def solve(alpha_a,q_a,alpha_b,depth):
        dest=None;error=None
        try:dest,error=inverse(robot,origin+line*alpha_b,q_a,direction)
        except Rejected:pass
        if dest is not None:
            # The second derivative bound also certifies the path between samples.
            curve=SWEEP_PER_RADIAN*float(np.abs(dest[:5]-q_a[:5]).sum())**2/8
            if deviation(q_a,dest)+curve<=.0005:
                out.append((dest,error));return
        if depth>=max_depth or (alpha_b-alpha_a)*span<=min_span:
            raise Rejected('无法确认整段直线精度，请缩短距离或调整目标')
        middle=(alpha_a+alpha_b)/2
        solve(alpha_a,q_a,middle,depth+1)
        solve(middle,out[-1][0],alpha_b,depth+1)
    solve(0.,np.asarray(start,dtype=float),1.,0)
    return out

def plan_job(payload):
    r=Robot();r.apply_limits(payload.get('limits_deg'));start=np.array(payload['start']);obstacles=payload['obstacles']
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
                if step.get('q_deg') is not None:
                    # Preserve the selected trial pose, but independently verify
                    # its limits, TCP and direction before checking the path.
                    dest=np.radians(step['q_deg'])
                    if not r.within(dest):raise Rejected('选定姿态超出关节限制')
                    tcp=r.fk(dest)[1];error=float(np.linalg.norm(tcp[:3,3]-target))
                    angle=0.
                    if direction is not None:
                        d=np.asarray(direction,dtype=float)
                        if not np.isfinite(d).all() or np.linalg.norm(d)<1e-8:raise Rejected('工具方向非法')
                        angle=float(np.arccos(np.clip(tcp[:3,2]@(d/np.linalg.norm(d)),-1,1)))
                    if error>.0005 or angle>np.radians(.5):raise Rejected('选定姿态与末端目标不一致，请重新试摆')
                    err={'position_mm':error*1000,'direction_deg':float(np.degrees(angle))}
                else:dest,err=inverse(r,target,q,direction)
                targets=[dest];residuals.append(err)
            else:
                for dest,err in straight_waypoints(r,r.fk(q)[1][:3,3],target,q,direction):
                    targets.append(dest);residuals.append(err)
        for dest in targets:
            if not r.within(dest):raise Rejected('目标关节或夹爪超出模拟限制')
            checks+=geo.check_segment(q,dest,deadline)
            duration=r.duration(q,dest)/payload['speed']
            segments.append({'start':q.tolist(),'end':dest.tolist(),'duration':duration,'at':elapsed})
            # The preview stores fifteen points along the segment, and the tool
            # centre depends only on the five serial joints, so the whole line is
            # one batched pass instead of fifteen forward kinematics calls.
            u=np.linspace(0,1,15)
            path.extend(tcp_frames(r,q[:5]+(dest[:5]-q[:5])*u[:,None])[:,:3,3].tolist())
            elapsed+=duration;q=dest
    if not segments:raise Rejected('动作序列为空')
    return {'segments':segments,'duration':elapsed,'end':q.tolist(),'path':path,'checks':checks,'residuals':residuals}

def workspace_job(payload):
    r=Robot();r.apply_limits(payload.get('limits_deg'));rng=np.random.default_rng(14)
    direction=payload.get('direction')
    direction=None if direction is None else np.array(direction)/np.linalg.norm(direction)
    samples=np.empty((3500,6))
    for index in range(3500):
        samples[index]=rng.uniform(r.limits[:,0],r.limits[:,1])
    # One draw per sample keeps the sequence identical to the loop this
    # replaces; only the kinematics are batched, because the tool frame depends
    # on the five serial joints and one pass over them costs less than 3500
    # library calls.
    tools=tcp_frames(r,samples[:,:5])
    if direction is not None:
        keep=np.degrees(np.arccos(np.clip(tools[:,:3,2]@direction,-1,1)))<=5
        tools=tools[keep]
    return {'points':tools[:,:3,3].tolist(),'label':'关节限位下的运动学采样；方向筛选容差 5°；未扣除碰撞，不能作为执行许可'}
