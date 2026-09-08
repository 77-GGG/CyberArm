"""Closed-chain virtual-work screening; not a stall/thermal or strength certification."""
import bpy,bmesh,math,json,itertools
from pathlib import Path
from mathutils import Vector
p=Path('E:/CyberArm/mechanical');out=p/'archive/blender_arm_v4';sc=bpy.context.scene
BASE=bpy.data.objects['J0_YAW'];UP=bpy.data.objects['J1_SHOULDER_HORN'];ELBOW_DRIVE=bpy.data.objects['J2_ELBOW_HORN']
FORE=bpy.data.objects['LINK_FOREARM'];WRIST=bpy.data.objects['J3_WRIST'];JAW=bpy.data.objects['J4_GRIPPER'];ROD=bpy.data.objects['LINK_PUSHROD']
code=(p/'scripts/build_blender_arm_v4.py').read_text();exec(code[code.index('def pose('):code.index('pose_info=pose()')],globals())
objects=[o for o in sc.objects if o.type=='MESH' and not o.name.startswith(('TEST','Studio')) and (o.get('solid_mass_g') is not None or o.get('mass_g') is not None)]
com={}
for o in objects:
    mass=o.get('solid_mass_g',o.get('mass_g',0))
    if o.name.startswith('HW_MG90S'):center=Vector((-5.2,0,-20.8))
    elif o.name.startswith('HW_Horn'):center=sum((Vector(c) for c in o.bound_box),Vector())/8
    else:
        o.data.calc_loop_triangles();sv=0.;cs=Vector()
        for t in o.data.loop_triangles:
            a,b,c=[o.data.vertices[i].co for i in t.vertices];v=a.dot(b.cross(c))/6;sv+=v;cs+=(a+b+c)*(v/4)
        center=cs/sv if abs(sv)>1e-7 else Vector()
    com[o.name]=(mass,center)
def energy(theta,psi,wrist,payload):
    info=pose(theta,psi,wrist=wrist)
    value=sum(m*(o.matrix_world@c).z for o in objects for m,c in [com[o.name]])
    # Distal mounting screws and flexible wires: conservative small explicit allowances.
    for j,c,m in [(FORE,Vector((0,0,0)),3),(WRIST,Vector((0,0,0)),3),(WRIST,Vector((41,0,0)),2),(WRIST,Vector((74,0,5)),payload)]:value+=m*(j.matrix_world@c).z
    return value,info
def torques(theta,psi,payload=5):
    inf=pose(theta,psi);w=-inf['forearm_absolute_deg'];q=[theta,psi,w];h=.02;ts=[]
    for k in range(3):
        plus=q.copy();minus=q.copy();plus[k]+=h;minus[k]-=h
        vp,_=energy(*plus,payload);vm,_=energy(*minus,payload)
        ts.append((vp-vm)/(2*math.radians(h))/10000)
    return {'theta_deg':theta,'psi_deg':psi,'wrist_relative_deg':w,'payload_g':payload,'servo_static_kgf_cm':ts,'max_abs_kgf_cm':max(map(abs,ts)),'loop':inf}
samples=[]
for t,pp in itertools.product([45,55,65,75],[-50,-35,-20,-5]):
    try:samples.append(torques(t,pp))
    except ValueError:samples.append({'theta_deg':t,'psi_deg':pp,'unreachable':True})
display={str(load):torques(60,-35,load) for load in (0,2,5,10)}
res={'method':'Numerical virtual work d(sum m*z)/dq with the other actuator angles held fixed, closed-loop forearm solved each step','screening_budget_kgf_cm':.81,'density_g_cm3':1.24,'budget_basis':'1.8 kgf cm at 4.8 V * assumed efficiency 0.9 / 2; NOT a continuous torque rating','printed_solid_mass_g':sum(o.get('solid_mass_g',0) for o in objects),'moving_component_masses_g':{o.name:com[o.name][0] for o in objects if o.parent in (UP,FORE,WRIST,JAW,ROD,ELBOW_DRIVE)},'display_load_sweep':display,'pose_samples_5g':samples,'limitations':['No dynamic inertia, thermal, friction, flexure, bolt preload, wear or FEA verification','Servo and horn COM/mass are estimates; print masses use fully solid PLA','Pose existence and torque tests do not establish continuous collision-free workspace']}
(out/'torque_screening.json').write_text(json.dumps(res,indent=2))
pose();print(json.dumps({'display_load_sweep':display,'pose_samples_5g':samples,'printed_solid_mass_g':res['printed_solid_mass_g']},indent=2))
