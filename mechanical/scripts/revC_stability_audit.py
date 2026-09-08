"""Read-only RevC geometry/load screening; run in BACKGROUND Blender.

Writes audit data only. Never saves or modifies the user's .blend file.
No FEA, no certified payload, no print mass prediction.
"""
import bpy, bmesh, json, math, hashlib, struct, itertools
from pathlib import Path
import numpy as np
from mathutils import Vector

ROOT = Path('E:/CyberArm/mechanical/arduino_reference_revC')
OUT = ROOT / 'audit_20260907'
OUT.mkdir(exist_ok=True)
SC = bpy.data.scenes['Arduino_Original_Replica']
bpy.context.window.scene = SC
bpy.context.view_layer.update()
G = 9.80665
JN = ['J01_Base_yaw','J02_Shoulder_pitch','J03_Elbow_pitch','J04_Wrist_roll','J05_Wrist_pitch']
J0 = [np.array(bpy.data.objects[n].matrix_world, dtype=float) for n in JN]
JL = [J0[0]] + [np.linalg.inv(J0[i-1]) @ J0[i] for i in range(1,5)]

def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf8')

def chain(o):
    result=[]
    while o:
        result.append(o.name); o=o.parent
    return result

def stage(o):
    c=chain(o)
    return max([i for i,n in enumerate(JN) if n in c], default=-1)

def geom(o):
    me=o.data; me.calc_loop_triangles()
    xyz=np.array([v.co[:] for v in me.vertices], dtype=float)
    tri=np.array([t.vertices[:] for t in me.loop_triangles], dtype=int)
    a,b,c=xyz[tri[:,0]],xyz[tri[:,1]],xyz[tri[:,2]]
    v=np.einsum('ij,ij->i',a,np.cross(b,c))/6
    volume=float(v.sum())
    com=((a+b+c)*v[:,None]/4).sum(axis=0)/volume if abs(volume)>1e-9 else xyz.mean(axis=0)
    signature=hashlib.sha256(xyz.astype('<f4').tobytes()+tri.astype('<i4').tobytes()).hexdigest()
    return xyz,tri,abs(volume),com,signature

manifest=json.loads((ROOT/'print_manifest.json').read_text(encoding='utf8'))
PN=[r['object'] for r in manifest]+['ARD_02_Foot_2','ARD_02_Foot_3','ARD_02_Foot_4','ARD_09_Link_Right']
actors=[];geometry={};baseline={};raw={}

def add(o,mass,local_com,kind):
    p=np.array(o.matrix_world) @ np.r_[local_com,1]
    actors.append({'name':o.name,'mass_g':float(mass),'p':p.tolist(),'stage':stage(o),'kind':kind})

for name in PN:
    o=bpy.data.objects[name]; xyz,tri,vol,com,sig=geom(o);raw[name]=(xyz,tri)
    W=np.array(o.matrix_world);world=xyz @ W[:3,:3].T+W[:3,3]
    bm=bmesh.new();bm.from_mesh(o.data)
    bad=sum(not e.is_manifold for e in bm.edges);bm.free()
    # Connected components, including source auxiliary hooks.
    parent=np.arange(len(xyz))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    for a,b in [e.vertices[:] for e in o.data.edges]:
        a,b=find(a),find(b)
        if a!=b:parent[a]=b
    groups={}
    for i in range(len(xyz)):groups.setdefault(find(i),[]).append(i)
    components=[]
    for indices in sorted(groups.values(),key=len,reverse=True):
        pts=xyz[indices]
        components.append({'vertices':len(indices),'local_min':pts.min(axis=0).tolist(),'local_max':pts.max(axis=0).tolist()})
    geometry[name]={'volume_mm3':vol,'solid_PLA_g':vol*.00124,'com_local_mm':com.tolist(),
        'bounds_world_mm':[world.min(axis=0).tolist(),world.max(axis=0).tolist()],
        'nonmanifold_edges':bad,'components':components}
    baseline[name]={'matrix_world':W.tolist(),'sha256_mesh':sig}
    add(o,vol*.00124,com,'print_solid_proxy')

for name in ['REVB_S01_Base_MG996R_SOURCE','REVB_S02_Shoulder_MG996R_SOURCE','REVB_S03_Elbow_MG996R_SOURCE']:
    add(bpy.data.objects[name],55,[-10.45,0,-24.2],'servo_nominal')
for name in ['ARD_S04_Wrist_roll_MG90S_USER_MODEL','ARD_S05_Wrist_pitch_MG90S_USER_MODEL','ARD_S06_Gripper_MG90S_USER_MODEL']:
    add(bpy.data.objects[name],13.4,[-5.2,0,-19],'servo_nominal')
for o in SC.objects:
    if o.type!='MESH':continue
    if o.name.startswith('REVC_') and any(c.name.startswith('REVC_09_') for c in o.users_collection):
        xyz,tri,vol,com,sig=geom(o);add(o,vol*.00785,com,'steel_geometric_proxy')
    if o.name.startswith('ARD_') and o.name.endswith(('_pin','_head')) and not o.hide_get():
        xyz,tri,vol,com,sig=geom(o);add(o,vol*.00785,com,'steel_geometric_proxy')
    if o.name.startswith('REVC_') and 'HORN_DRILL' in o.name:
        # Source horn meshes may be open: nominal mass allowance, NOT volume.
        horn_xyz=geom(o)[0]
        horn_com=(horn_xyz.min(axis=0)+horn_xyz.max(axis=0))/2
        add(o,1.5 if o.name[5:8] in ('S01','S02','S03') else .6,horn_com,'horn_mass_allowance')
        baseline[o.name]={'matrix_world':np.array(o.matrix_world).tolist(),'sha256_mesh':geom(o)[4]}

palm=bpy.data.objects['ARD_07_Gripper_base'];PM=np.array(palm.matrix_world)
verts=np.concatenate([np.array([v.co[:] for v in bpy.data.objects[n].data.vertices]) @ np.array(bpy.data.objects[n].matrix_world)[:3,:3].T + np.array(bpy.data.objects[n].matrix_world)[:3,3] for n in ['ARD_10_Jaw_Left','ARD_10_Jaw_Right']])
pv=np.c_[verts,np.ones(len(verts))] @ np.linalg.inv(PM).T
TIP=PM@np.array([18.45,12.8,float(pv[:,2].max()),1])
# Residual unmodelled installation hardware / cables: deliberately explicit.
for label,mass,st,pos in [('base_mount_allowance',8,-1,J0[0][:,3]),('shoulder_mount_allowance',6,0,J0[1][:,3]),('elbow_mount_allowance',6,2,J0[2][:,3]),('distal_cable_allowance',8,4,TIP)]:
    actors.append({'name':label,'mass_g':mass,'p':pos.tolist(),'stage':st,'kind':'unweighed_allowance'})

def hull(points):
    P=sorted(set(tuple(float(v) for v in p) for p in points))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lo=[];hi=[]
    for p in P:
        while len(lo)>=2 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(hi)>=2 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return np.array(lo[:-1]+hi[:-1])

base_points=[];foot_points=[];contact={}
for name in ['ARD_01_Base']+['ARD_02_Foot_'+str(i) for i in range(1,5)]:
    xyz=raw[name][0];W=np.array(bpy.data.objects[name].matrix_world)
    pts=xyz @ W[:3,:3].T+W[:3,3]
    low=float(pts[:,2].min());touch=pts[pts[:,2]<=low+.1,:2]
    contact[name]={'lowest_world_z_mm':low,'contact_xy_hull_mm':hull(touch).tolist()}
    (base_points if name=='ARD_01_Base' else foot_points).extend(touch.tolist())
H=hull(base_points+foot_points); HB=hull(base_points)
def edges(H):
    d=np.roll(H,-1,axis=0)-H
    inward=np.c_[-d[:,1],d[:,0]]/np.linalg.norm(d,axis=1)[:,None]
    return inward,np.einsum('ij,ij->i',inward,H)
N,C=edges(H);NB,CB=edges(HB)

def rz(deg):
    c,s=math.cos(math.radians(deg)),math.sin(math.radians(deg))
    return np.array([[c,-s,0,0],[s,c,0,0],[0,0,1,0],[0,0,0,1]],float)
def pose(q):
    J=[]
    for i in range(5):J.append((J[i-1] if i else np.eye(4))@JL[i]@rz(q[i]))
    D=[J[i]@np.linalg.inv(J0[i]) for i in range(5)]
    pts=np.array([(D[a['stage']]@a['p'] if a['stage']>=0 else a['p'])[:3] for a in actors])
    tip=(D[4]@TIP)[:3]
    return J,pts,tip

def assess(q,print_factor=1.,base_factor=None):
    J,pts,tip=pose(q)
    mass=np.array([a['mass_g']*(base_factor if base_factor is not None and a['kind']=='print_solid_proxy' and a['stage']<=0 else print_factor if a['kind']=='print_solid_proxy' else 1) for a in actors])
    rows=[]
    for j in range(1,5):
        org=J[j][:3,3];axis=J[j][:3,2]
        sel=np.array([a['stage']>=j for a in actors])
        force=np.c_[np.zeros((len(mass),2)),-mass*G/1000]
        signed=float(np.sum(np.cross((pts[sel]-org)/1000,force[sel])@axis))
        per_g=float(np.dot(np.cross((tip-org)/1000,[0,0,-G/1000]),axis))
        stall=(9.4 if j<3 else 1.8)*.0980665
        caps={}
        for fraction in [.3,.5,1.]:
            budget=stall*fraction
            # Solve |T0 + c*m| <= budget for positive m; overload at m=0 fails screening.
            caps[str(fraction)]=max(0., (budget-abs(signed))/abs(per_g)) if abs(per_g)>1e-8 else None
        rows.append({'joint':JN[j],'empty_Nm':abs(signed),'signed_Nm':signed,'payload_Nm_per_g':abs(per_g),
            'with_50g_Nm':abs(signed+50*per_g),'with_100g_Nm':abs(signed+100*per_g),
            'fraction_of_stall_empty':abs(signed)/stall,'stall_4p8V_Nm':stall,'screen_cap_g':caps})
    def tipping(n,c):
        dist=pts[:,:2]@n.T-c
        # kg*mm signed moments, divided by 1000 and multiplied by g -> N.m.
        sums=mass@dist
        pd=tip[:2]@n.T-c
        caps=[s/(-p) for s,p in zip(sums,pd) if p<0]
        com=mass@pts/mass.sum()
        return {'margin_mm':float(np.min(n@com[:2]-c)),
            'minimum_empty_restoring_Nm':float(sums.min()*G/1e6),
            'static_tip_threshold_g':float(min(caps)) if caps else None,
            'tip_threshold_1p5_moment_margin_g':float(min([((mass@np.maximum(dist,0)) [i]/1.5+(mass@np.minimum(dist,0))[i])/(-pd[i]) for i in range(len(pd)) if pd[i]<0])) if caps else None}
    return {'q_deg':list(q),'print_solid_mass_multiplier':print_factor,'base_print_multiplier':base_factor,
        'total_mass_g':float(mass.sum()),'com_world_mm':(mass@pts/mass.sum()).tolist(),
        'tip_world_mm':tip.tolist(),'reach_from_base_axis_mm':float(np.linalg.norm(tip[:2])),
        'joints':rows,'all_feet':tipping(N,C),'base_only':tipping(NB,CB)}

write('baseline_geometry.json',{'source_blend':bpy.data.filepath,'mesh_transforms':baseline,'printed':geometry,
    'joints':{n:J.tolist() for n,J in zip(JN,J0)},'mass_actors':actors,'payload_point_definition':'Symmetric jaw-tip proxy, same as RevB; actual object COM may differ','tip_zero_mm':TIP.tolist(),
    'contact':contact,'all_feet_hull_xy_mm':H.tolist(),'base_hull_xy_mm':HB.tolist()})
print('BASELINE',json.dumps({'print_g':sum(a['mass_g'] for a in actors if a['kind']=='print_solid_proxy'),
    'mass_by_kind':{k:sum(a['mass_g'] for a in actors if a['kind']==k) for k in set(a['kind'] for a in actors)},
    'contact_z':{n:c['lowest_world_z_mm'] for n,c in contact.items()},'components':{n:g['components'] for n,g in geometry.items() if len(g['components'])>1}}))

# Saved posture plus horizontal extended reference found by coarse-to-fine reach optimization.
qbest=[0,0,0,0,0];best=-1
for q2,q3,q5 in itertools.product(range(-90,91,15),range(-90,91,15),range(-90,91,30)):
    q=[0,q2,q3,0,q5];_,_,tip=pose(q)
    # Pose purely kinematic. Not a physically approved joint range.
    if tip[0]>best:best=tip[0];qbest=q
for step in [5,1,.2]:
    center=qbest.copy()
    for d2,d3,d5 in itertools.product([-2,-1,0,1,2],repeat=3):
        q=[0,center[1]+d2*step,center[2]+d3*step,0,center[4]+d5*step]
        _,_,tip=pose(q)
        if tip[0]>best:best=tip[0];qbest=q
results={'scope':'STATIC SCREEN ONLY. All-solid PLA upper mass proxy and illustrative mass multipliers, not infill percentages. No certified operating envelope. Tips are proxy COM locations. Support assumes all feet are rigidly attached, coplanar and nonslip. No springs, electronics, payload offset, servo torque derating by lot, thermal rating, contact/friction, dynamics or FEA.',
    'saved_pose':[assess([0]*5,f) for f in [1.,.75,.5]],
    'max_extension_reference':[assess(qbest,f) for f in [1.,.75,.5]],
    'light_base_heavy_arm':assess(qbest,1.,.5)}
print('POSES',json.dumps(results))
write('static_load_screen.json',results)

# Sweep nominal preview ranges, including yaw relative to support polygon.
worst={};count=0
for q2,q3,q4,q5 in itertools.product([-30,0,30],repeat=4):
    for yaw in range(-30,31,15):
        q=[yaw,q2,q3,q4,q5];r=assess(q);count+=1
        for row in r['joints']:
            key=row['joint']
            if key not in worst or row['empty_Nm']>worst[key]['row']['empty_Nm']:worst[key]={'q_deg':q,'row':row}
        for key in ['all_feet','base_only']:
            k=key+'_margin'
            if k not in worst or r[key]['margin_mm']<worst[k]['margin_mm']:worst[k]={'q_deg':q,**r[key]}
write('preview_pose_sweep.json',{'sample_count':count,'angles_deg':[-30,0,30],'yaw_deg':[-30,-15,0,15,30],'not_collision_checked':True,'worst_samples':worst})
print('SWEEP',json.dumps({'sample_count':count,'worst':worst}))

# Cross-section moments of area from direct triangle/plane intersections.
# Signed polygon line integral includes holes and separated contours without voxelization.
sections=[]
for name,levels in [('ARD_04_Arm_01',[25,40,60,80,95]),('ARD_05_Arm_02_v3',[-10,0,20,40])]:
    xyz,tri=raw[name]
    for y in levels:
        segments=[]
        for ids in tri:
            p=xyz[ids];d=p[:,1]-y
            if min(d)>=0 or max(d)<=0:continue
            hit=[]
            for i,j in [(0,1),(1,2),(2,0)]:
                if d[i]*d[j]<0:hit.append(p[i]+(p[j]-p[i])*(-d[i])/(d[j]-d[i]))
            if len(hit)!=2:continue
            a,b=hit
            normal=np.cross(p[1]-p[0],p[2]-p[0]);direction=np.cross([0,1,0],normal)
            if np.dot(b-a,direction)<0:a,b=b,a
            segments.append((a[[0,2]],b[[0,2]]))
        if not segments:continue
        ar=mx=mz=ix=iz=ixz=0
        coords=[]
        for a,b in segments:
            x,z=a;u,v=b;c=x*v-u*z;ar+=c/2;mx+=(x+u)*c/6;mz+=(z+v)*c/6
            ix+=(z*z+z*v+v*v)*c/12;iz+=(x*x+x*u+u*u)*c/12
            ixz+=(2*x*z+x*v+u*z+2*u*v)*c/24;coords.extend([a,b])
        if abs(ar)<1e-5:continue
        s=1 if ar>0 else -1;cx,cz=mx/ar,mz/ar
        Ixx=s*(ix-ar*cz*cz);Izz=s*(iz-ar*cx*cx);Ixz=s*(ixz-ar*cx*cz)
        arr=np.array(coords);cmax=max(abs(arr[:,0]-cx))
        sections.append({'name':name,'local_y_mm':y,'material_area_mm2':abs(ar),'com_xz':[cx,cz],
            'Ixx_mm4':Ixx,'Izz_mm4':Izz,'Ixz_mm4':Ixz,'Z_about_local_z_mm3':Izz/cmax,
            'nominal_bending_MPa_at_0p5Nm':500*cmax/Izz,'note':'Solid geometric section, ignores infill, stress concentration, torsion and anisotropy; nominal bending about local Z only.'})
write('beam_sections.json',sections)
print('SECTIONS',json.dumps(sections))

# Independent forward-transform cross-check against Blender evaluated drivers.
ctrl=bpy.data.objects['ARM_CONTROLS']
keys=['01_Base_deg','02_Shoulder_deg','03_Elbow_deg','04_Wrist_roll_deg','05_Wrist_pitch_deg']
qcheck=[15,10,-10,5,-5]
expectedJ,expectedP,expectedTip=pose(qcheck)
for k,v in zip(keys,qcheck):ctrl[k]=float(v)
ctrl.update_tag();bpy.context.view_layer.update();SC.frame_set(SC.frame_current)
errors={n:float(np.abs(np.array(bpy.data.objects[n].matrix_world)-M).max()) for n,M in zip(JN,expectedJ)}
for k in keys:ctrl[k]=0.
ctrl.update_tag();bpy.context.view_layer.update();SC.frame_set(SC.frame_current)
write('kinematic_crosscheck.json',{'q_deg':qcheck,'matrix_error':errors,'passed':max(errors.values())<.001})
assert max(errors.values())<.001,errors

# Hook is a separate mesh component; determine whether it touches the main arm.
from mathutils.bvhtree import BVHTree
o=bpy.data.objects['ARD_04_Arm_01'];xyz,tri=raw[o.name]
parent=np.arange(len(xyz))
for a,b in [e.vertices[:] for e in o.data.edges]:
    a,b=find(a),find(b)
    if a!=b:parent[a]=b
groups={}
for i in range(len(xyz)):groups.setdefault(find(i),[]).append(i)
main,hook=sorted(groups.values(),key=len,reverse=True)
S=set(main);mt=[tuple(t) for t in tri if t[0] in S];ht=[tuple(t) for t in tri if t[0] not in S]
tree=BVHTree.FromPolygons([Vector(v) for v in xyz],mt,all_triangles=True)
other=BVHTree.FromPolygons([Vector(v) for v in xyz],ht,all_triangles=True)
nearest=[]
for i in hook:
    loc,norm,idx,dist=tree.find_nearest(Vector(xyz[i]))
    nearest.append(float(dist))
write('hook_attachment_check.json',{'mesh_components':len(groups),'main_vertices':len(main),'hook_vertices':len(hook),
    'triangle_intersections':len(tree.overlap(other)),'hook_vertex_to_main_surface_min_mm':min(nearest),
    'hook_vertex_to_main_surface_max_mm':max(nearest),
    'note':'Vertex-to-surface minimum plus triangle intersections, not an exact CAD solid distance nor print bonding certification.'})

# Gripper virtual-work estimate, not a contact simulation or measured friction.
jaw_names=['ARD_10_Jaw_Left','ARD_10_Jaw_Right'];jaw_points=[]
for name in jaw_names:
    jaw=bpy.data.objects[name];xx=np.array([v.co[:] for v in jaw.data.vertices])
    world=xx@np.array(jaw.matrix_world)[:3,:3].T+np.array(jaw.matrix_world)[:3,3]
    pp=np.c_[world,np.ones(len(world))]@np.linalg.inv(PM).T
    # Representative point of the distal 3 mm of each pad, fixed on the jaw.
    take=pp[:,2]>pp[:,2].max()-3
    jaw_points.append(np.r_[xx[take].mean(axis=0),1])
def jaw_gap(q):
    ctrl['06_Gripper_deg']=float(q);ctrl.update_tag();bpy.context.view_layer.update();SC.frame_set(SC.frame_current)
    pp=[np.linalg.inv(PM)@np.array(bpy.data.objects[n].matrix_world)@p for n,p in zip(jaw_names,jaw_points)]
    return float(pp[1][0]-pp[0][0]),[p[:3].tolist() for p in pp]
grip=[]
for q in [-8,-4,0,4,8]:
    a,_=jaw_gap(q-.02);b,_=jaw_gap(q+.02);gap,points=jaw_gap(q)
    dg=abs((b-a)/math.radians(.04))/1000
    # Equal/opposite normal forces along palm local X: tau=N*d(gap)/dq.
    torque=.5*1.8*.0980665
    normal=torque/dg if dg>1e-8 else None
    grip.append({'q_deg':q,'representative_pad_gap_mm':gap,'pad_points_palm_mm':points,
        'gap_derivative_m_per_rad':dg,'ideal_normal_each_jaw_N_at_half_stall':normal,
        'friction_mass_g_if_mu_0p2_efficiency_0p6':2*.2*.6*normal/G*1000 if normal else None,
        'note':'Illustrative coefficient and efficiency, no object shape/pad compliance/slip validation; excludes gripper self-weight work. No safe payload rating.'})
ctrl['06_Gripper_deg']=0.;ctrl.update_tag();bpy.context.view_layer.update();SC.frame_set(SC.frame_current)
write('gripper_virtual_work.json',grip)
print('EXTRA',json.dumps({'kinematic_errors':errors,'hook_min_vertex_distance':min(nearest),'hook_intersections':len(tree.overlap(other)),'gripper':grip}))
print('AUDIT_COMPLETE_NO_BLEND_SAVED')
