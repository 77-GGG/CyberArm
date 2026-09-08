"""Reproducible mass, static screening, and sampled pose checks; not certification."""
import bpy, bmesh, math, json, itertools
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
out=Path('E:/CyberArm/mechanical/archive/blender_arm_v2')
sc=bpy.context.scene
parts=[o for o in sc.objects if o.get('purpose')=='FDM_part' and not o.name.startswith('TEST_')]
servos=[o for o in sc.objects if o.name.startswith('HW_MG90S_')]
refs=[o for o in sc.objects if o.get('mass_g') is not None]
meshes=parts+servos
joints=[bpy.data.objects[n] for n in ['J0_YAW','J1_SHOULDER_3_to_1','J2_ELBOW','J3_WRIST','J4_GRIPPER']]
saved=[o.rotation_euler.copy() for o in joints]

def centroid(o):
    o.data.calc_loop_triangles();vsum=0.;csum=Vector()
    for t in o.data.loop_triangles:
        a,b,c=[o.data.vertices[i].co for i in t.vertices]
        v=a.dot(b.cross(c))/6;vsum+=v;csum+=(a+b+c)*(v/4)
    return csum/vsum if abs(vsum)>1e-8 else sum((v.co for v in o.data.vertices),Vector())/len(o.data.vertices)

def descendant(o,j):
    p=o.parent
    while p:
        if p==j:return True
        p=p.parent
    return False

for o in joints:o.rotation_euler=(0,0,0)
bpy.context.view_layer.update()
massrows=[]
for o in parts+refs:
    mass=o.get('solid_mass_g',o.get('mass_g',0))
    # Printed bodies use signed-volume centroids. Purchased COM is an estimate.
    center=Vector((-5.2,0,-20.8)) if o in servos else centroid(o)
    world=o.matrix_world@center
    massrows.append({'part':o.name,'mass_g':mass,'com_world_mm':list(world),'com_method':'housing-centre estimate' if o in servos else 'geometric-volume centroid'})
torques={}
for j,ratio in zip(joints[1:4],[3,1,1]):
    x=j.matrix_world.translation.x
    dead=sum(r['mass_g']*max(0,r['com_world_mm'][0]-x)/10000 for r in massrows if descendant(bpy.data.objects[r['part']],j))
    for xx,mm in [(80,4),(150,3),(215,2)]:
        if xx>=x:dead+=mm*(xx-x)/10000
    budget=1.8*ratio*(.8 if ratio==3 else .9)/2
    lever=(247-x)/10000
    torques[j.name]={'dead_kgf_cm':dead,'with_5g_kgf_cm':dead+5*lever,'with_10g_kgf_cm':dead+10*lever,'screening_budget_kgf_cm':budget,'payload_at_budget_g':max(0,(budget-dead)/lever)}

# Elementary screening: fully solid rails, unknown printed properties explicitly assumed.
Iupper=2*2.8*(14**3-6**3)/12
Ifore=Iupper
Iwrist=2*3*9**3/12
stress=[]
for j,L,I,h in zip(joints[1:4],[80,70,55],[Iupper,Ifore,Iwrist],[14,14,9]):
    M=torques[j.name]['with_5g_kgf_cm']*98.0665
    stress.append({'joint':j.name,'I_mm4':I,'nominal_bending_MPa':M*(h/2)/I,'threefold_local_stress_MPa':3*M*(h/2)/I,'equivalent_tip_load_deflection_mm':M*L*L/(3*1500*I)})

# Surface screening over a small explicit grid. Rigid coplanar contacts are ignored
# only if the earlier exact Boolean measurement found zero intersection volume.
prior=json.loads((out/'interference_volume.json').read_text())
allowed={tuple(sorted([r['a'],r['b']])) for r in prior if r.get('volume_mm3',1)<.01}
def candidates():
    bpy.context.view_layer.update();trees={};bounds={}
    for o in meshes:
        vs=[o.matrix_world@v.co for v in o.data.vertices]
        trees[o.name]=BVHTree.FromPolygons(vs,[p.vertices[:] for p in o.data.polygons])
        bounds[o.name]=([min(v[k] for v in vs) for k in range(3)],[max(v[k] for v in vs) for k in range(3)])
    hits=[]
    for i,a in enumerate(meshes):
        for b in meshes[i+1:]:
            key=tuple(sorted([a.name,b.name]))
            if key in allowed:continue
            aa,ab=bounds[a.name];ba,bb=bounds[b.name]
            if any(min(ab[k],bb[k])-max(aa[k],ba[k])<.02 for k in range(3)):continue
            if trees[a.name].overlap(trees[b.name]):hits.append(list(key))
    return hits

samples=[]
for yaw,s,e in itertools.product([-45,0,45],[45,60,80],[-60,-80,-100]):
    w=s+e
    for o,axis,deg in [(joints[0],2,yaw),(joints[1],1,-s),(joints[2],1,-e),(joints[3],1,w),(joints[4],2,-8)]:o.rotation_euler[axis]=math.radians(deg)
    samples.append({'angles_deg':{'yaw':yaw,'shoulder_elevation':s,'elbow_relative':e,'wrist_euler_y':w,'jaw':-8},'crossing_candidates':candidates()})
for o,r in zip(joints,saved):o.rotation_euler=r
grip=[]
for a in [0,-8,-20,-30,-34,-36]:
    joints[4].rotation_euler[2]=math.radians(a)
    grip.append({'jaw_deg':a,'crossing_candidates':candidates()})
for o,r in zip(joints,saved):o.rotation_euler=r
bpy.context.view_layer.update()
result={'printed_parts':len(parts),'solid_print_mass_g':sum(o['solid_mass_g'] for o in parts),'mass_components':massrows,'static_horizontal_volume_centroid':torques,'beam_screening_5g':stress,'material_assumptions':{'PLA_density_g_cm3':1.24,'E_MPa':1500,'local_allowable_MPa':8,'notch_multiplier':3,'warning':'Assumed screening values, not measured material allowables or FEA.'},'pinion_Lewis':{'assumed_Y':.32,'half_stall_tangential_force_N':8.826,'tooth_bending_at_half_stall_MPa':8.826/(5*1*.32),'at_stall_MPa':17.652/(5*1*.32)},'sampled_poses':samples,'gripper_samples':grip,'limitations':['No continuous torque rating is available: half-stall budget is a screening heuristic, not a service rating.','Only sampled mesh-surface crossings, not continuous swept volume, cable motion, fastener envelopes or full containment.','Fixed foam and unmeasured horn templates are not collision-qualified.','Beam formula omits joint compliance, bearing play, servo gear backlash and creep.']}
(out/'final_checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'torques':torques,'stress':stress,'solid_print_mass_g':result['solid_print_mass_g'],'pose_samples':len(samples),'pose_candidates':[x for x in samples if x['crossing_candidates']],'gripper_candidates':[x for x in grip if x['crossing_candidates']]},indent=2))
