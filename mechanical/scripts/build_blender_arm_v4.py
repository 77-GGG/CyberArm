"""B4: horn-driven closed-chain arm. No shoulder gears; both main servos on turret.
Coordinates mm. Original nylon horns are purchased mechanisms, not printed replicas.
"""
import bpy,bmesh,math,json
from pathlib import Path
from mathutils import Vector,Matrix
root=Path('E:/CyberArm/mechanical');OUT=root/'archive/blender_arm_v4';OUT.mkdir(exist_ok=True);(OUT/'stl').mkdir(exist_ok=True)
for s in bpy.data.scenes:
    if s.name.startswith(('CyberArm_B2_','CyberArm_B3_')):
        for o in s.objects:
            if not o.name.startswith(('B2_ARCHIVE_','B3_ARCHIVE_')):o.name='B3_ARCHIVE_'+o.name
src=(root/'scripts/build_blender_arm.py').read_text(encoding='utf-8')
helpers=src.split("BASE=joint('J0_YAW')",1)[0]
helpers=helpers.replace('blender_arm_v2','blender_arm_v4').replace('CyberArm_B2','CyberArm_B4')
exec(compile(helpers,'B4_geometry_helpers','exec'),globals())
GREY.diffuse_color=(.20,.24,.28,1)
next(n for n in GREY.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value=(.20,.24,.28,1)
next(n for n in BLUE.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value=(.035,.04,.045,1)
pitch=Matrix(((1,0,0),(0,0,-1),(0,1,0))).to_4x4()
BASE=joint('J0_YAW');UP=joint('J1_SHOULDER_HORN',BASE,(0,0,90))
ELBOW_DRIVE=joint('J2_ELBOW_HORN',BASE,(0,0,90))
FORE=joint('LINK_FOREARM',UP,(60,0,0));WRIST=joint('J3_WRIST',FORE,(55,0,0))
JAW=joint('J4_GRIPPER',WRIST,(41,0,10));ROD=joint('LINK_PUSHROD',BASE)

def remove(n):
    ob=bpy.data.objects.get(n)
    if ob:bpy.data.objects.remove(ob,do_unlink=True)
def into(o,tf):
    active(o);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True);o.data.transform(tf);return o
def pitched(o,at):return into(o,Matrix.Translation(Vector(at))@pitch)
def ring(c,r,ri,h,axis='Y'):
    o=cyl(c,r,h,axis);hole(o,c,ri,h+5,axis);return o
def finish_part(o,n,parent=None,color=None,plane='XZ'):
    return finish(o,n,parent,color or ORANGE,plane)
def frame(n,parent,at,pitched_axis=True):
    o=box((-5.2,0,-14.95),(37,20,3),.6)
    boolean(o,box((-5.2,0,-14.95),(23,12.65,9),.3))
    for x in (-19.147,8.747):hole(o,(x,0,-14.95),1.2,10)
    tf=Matrix.Translation(Vector(at))@(pitch if pitched_axis else Matrix.Identity(4))
    return finish_part(into(o,tf),n,parent,GREY,'XZ' if pitched_axis else 'XY')
def bearing(n,parent,c):return finish(ring(c,5,1.5,4),n,parent,STEEL,hardware=True,mass=1.8)
def spacer(n,parent,c,length):return finish_part(ring(c,2.75,1.65,length),n,parent,GREY)

# User servo mesh, normalized to output tip. Five unchanged MG90S bodies.
path=next(root.rglob('servo_MG90S.STL'));bpy.ops.wm.stl_import(filepath=str(path));temp=bpy.context.object
for v in temp.data.vertices:
    x,y,z=v.co;v.co=(x-21.325,z-6.0254,y-32.1)
servo_mesh=temp.data.copy();bpy.data.objects.remove(temp,do_unlink=True)
def servo(n,parent,at,axis=True):
    o=bpy.data.objects.new(n,servo_mesh.copy());REF.objects.link(o);o.parent=parent
    o.matrix_basis=Matrix.Translation(Vector(at))@(pitch if axis else Matrix.Identity(4))
    o.data.materials.clear();o.data.materials.append(BLUE);o['mass_g']=13.4;o['purpose']='purchased_reference';return o
servo('HW_MG90S_Yaw',None,(0,0,36),False)
servo('HW_MG90S_Shoulder',BASE,(0,-13,90))
servo('HW_MG90S_Elbow_FIXED',BASE,(0,-53,90))
servo('HW_MG90S_Wrist',FORE,(55,-30,0))
servo('HW_MG90S_Gripper',WRIST,(41,0,10),False)

# Measured original horns. Arm underside = shaft tip, source spline mouth toward servo.
specs={'single':('obj_1_ServoMotor Arms.stl_B.stl',111.455343,138.914075), 'double':('obj_2_ServoMotor Arms.stl_A_A.stl',125.348794,129.224590),'cross':('obj_3_ServoMotor Arms.stl_A_B.stl',125.233263,114.057127)}
horn_meshes={}
for kind,(name,cx,cy) in specs.items():
    bpy.ops.wm.stl_import(filepath=str(root/'servo配件'/name));o=bpy.context.object
    for v in o.data.vertices:v.co=(v.co.x-cx,cy-v.co.y,2.5-v.co.z)
    horn_meshes[kind]=o.data.copy();bpy.data.objects.remove(o,do_unlink=True)
def horn(kind,n,parent,at,axis=True,angle=0):
    o=bpy.data.objects.new('HW_Horn_'+kind+'_'+n,horn_meshes[kind].copy());REF.objects.link(o);o.parent=parent
    o.matrix_basis=Matrix.Translation(Vector(at))@(pitch if axis else Matrix.Identity(4))@Matrix.Rotation(angle,4,'Z')
    o.data.materials.clear();o.data.materials.append(WHITE);o['purpose']='purchased_reference';o['mass_g']={'single':.5,'double':.8,'cross':1}[kind]
    o['connection']='Original spline + center screw; M1.6 through measured peripheral holes, no adhesive';return o
horn('cross','YAW_DIRECT',BASE,(0,0,36),False)
horn('double','SHOULDER_DIRECT',UP,(0,-13,0))
horn('double','ELBOW_CRANK_R16',ELBOW_DRIVE,(0,-53,0))
horn('single','WRIST_DIRECT',WRIST,(0,-30,0))
horn('single','GRIPPER_DIRECT',JAW,(0,0,0),False,math.atan2(13,31))

# Fixed bearing-supported yaw base. Rounded footprint and a removable cylindrical sleeve.
o=cyl((0,0,2),65,4)
for a in (0,120,240):
    x,y=73*math.cos(math.radians(a)),73*math.sin(math.radians(a))
    add(o,cyl((x,y,2),10,4));hole(o,(x,y,2),2.25,10)
for x in (-25,25):
    for y in (-24,24):hole(o,(x,y,2),1.7,10)
boolean(o,box((-5.2,0,4),(23,12.7,1)))
for x in (-19.147,8.747):
    if x<0:add(o,cyl((x,0,11.775),2.3,15.55))
    else:
        for y in (-4.5,4.5):add(o,cyl((x,y,11.775),2.3,15.55))
        add(o,box((x,0,18.45),(4.6,13.6,2.2),.3))
    hole(o,(x,0,18),1.05,6)
base=finish_part(o,'P01_Base',None,GREY,'XY');frame('P02_Yaw_frame',None,(0,0,36),False)
for side in (-1,1):
    o=box((0,0,51),(46,44,22),1.5);hole(o,(0,0,51),12.4,35)
    for z in (44,58):hole(o,(0,0,z),16.1,7.2)
    boolean(o,box((-side*30,0,51),(60.2,70,40)))
    for y in (-24,24):
        add(o,box((side*25,y,33),(8,10,58),1));add(o,box((side*22,y,59),(12,10,6),.5));hole(o,(side*25,y,33),1.7,70)
    for y in (-19,19):hole(o,(0,y,51),1.65,60,'X')
    finish_part(o,'P03_Bearing_pedestal_'+str(side),None,GREY)
for z in (44,58):finish(ring((0,0,z),16,10,7,'Z'),'HW_6804_'+str(z),None,STEEL,hardware=True,mass=15)
o=cyl((0,0,50.75),9.925,23.5);add(o,cyl((0,0,39.5),12,2));hole(o,(0,0,49),3.6,40)
for x,y in [(6,0),(-6,0),(0,5.1),(0,-5.1)]:hole(o,(x,y,39.5),.9,6)
for a in (0,120,240):hole(o,(7*math.cos(math.radians(a)),7*math.sin(math.radians(a)),58),.9,12)
finish_part(o,'P04_Cross_horn_yaw_hub',BASE,GREY,'XY')
finish(ring((0,0,61.95),12,10.05,.9,'Z'),'HW_Yaw_inner_race_shim',BASE,STEEL,hardware=True,mass=1)
o=cyl((0,0,64.5),59,4);hole(o,(0,0,64.5),3.6,10)
for a in (0,120,240):hole(o,(7*math.cos(math.radians(a)),7*math.sin(math.radians(a)),64.5),1.2,10)
turret=finish_part(o,'P05_Turret',BASE,GREY,'XY')
o=ring((0,0,32.9),58,56.4,57.8,'Z')
for a in (0,120,240):
    x,y=53.3*math.cos(math.radians(a)),53.3*math.sin(math.radians(a))
    add(o,cyl((x,y,5.6),4,3.2));hole(o,(x,y,5.6),1.2,12);hole(base,(x,y,2),1,10)
for y in (-10,0,10):boolean(o,box((-57,y,28),(8,3,18),1))
finish_part(o,'P06_Round_base_sleeve',None,GREY,'XY')

# Both shoulder and elbow actuators are now FIXED to the turret.
for name,bx,tipy in [('Shoulder',0,-13),('Elbow',0,-53)]:
    o=frame('P07_'+name+'_fixed_motor_stand',BASE,(bx,tipy,90))
    for dx in (-20.7,10.3):
        x,y=bx+dx,tipy+14.95
        add(o,box((x,y,74.3),(5,5,15.6),.6));add(o,box((x,y,68.5),(7,13,4),.8))
        hole(o,(x,y+4,68.5),1.2,10);hole(turret,(x,y+4,64.5),1.0,10)
o=box((0,24,80.5),(18,4,28),1);add(o,cyl((0,24,90),8,4.2,'Y'))
add(o,box((0,24,68.5),(22,12,4),1));hole(o,(0,24,90),5.1,12,'Y')
for x in (-7,7):hole(o,(x,24,68.5),1.2,12);hole(turret,(x,24,64.5),1,12)
finish_part(o,'P08_Shoulder_rear_bearing_stand',BASE,GREY)
bearing('HW_623_Shoulder',BASE,(0,24,90))

def link(L,y,r0=12,r1=10):
    o=box((L/2,y,0),(L,2.8,14),.6)
    add(o,cyl((0,y,0),r0,3.0,'Y'));add(o,cyl((L,y,0),r1,3.0,'Y'))
    # 1.2 mm web remains under a shallow recess, not a perforated stick.
    outside=y+(-1.0 if y<0 else 1.0)
    boolean(o,box((L/2,outside,0),(max(8,L-32),1.4,6),1))
    return o
for y in (-18,29):
    o=link(60,y)
    hole(o,(0,y,0),3.6 if y<0 else 1.7,12,'Y')
    add(o,cyl((60,y,0),7,4,'Y'));hole(o,(60,y,0),5.1,12,'Y')
    if y<0:
        add(o,ring((0,-16.1,0),11,3.6,1.2))
        for x in (-6,6):hole(o,(x,y,0),.9,12,'Y')
    else:hole(o,(0,y,5),.85,10)
    # Matched cross-member screw holes, away from the two joint circles.
    for z in (-4,4):hole(o,(30,y,z),1.2,12,'Y')
    finish_part(o,'P10_Upper_trough_'+str(y),UP)
    bearing('HW_623_Elbow_'+str(y),UP,(60,y,0))
o=box((30,5.5,0),(6,43.8,12),.6)
for z in (-4,4):hole(o,(30,5.5,z),1,50,'Y')
finish_part(o,'P11_Upper_cross_tie',UP,GREY)
finish(cyl((0,28,0),1.5,12,'Y'),'HW_Shoulder_idler_pin',UP,STEEL,hardware=True,mass=1)
spacer('P12_Shoulder_idler_spacer',UP,(0,26.75,0),1.5)

# Forearm carries a 16 mm bell-crank input point. The visible pushrod drives it.
for y in (-27,14):
    o=link(55,y,r0=11,r1=13.5);hole(o,(0,y,0),1.7,12,'Y')
    hole(o,(55,y,0),9.3 if y<0 else 1.7,12,'Y')
    if y<0:
        # Rigid outboard bell crank aligns with the forward fixed servo horn.
        add(o,ring((0,-41,0),6.5,1.7,25.2))
        add(o,cyl((16,-40.4,0),3.5,26.4,'Y'))
        add(o,box((8,-55,0),(16,3,7),.5));add(o,cyl((0,-55,0),8,3.2,'Y'));add(o,cyl((16,-55,0),4,3.2,'Y'))
        hole(o,(0,-55,0),1.7,64,'Y');hole(o,(16,-55,0),.9,12,'Y')
    else:hole(o,(55,y,5),.85,10)
    add(o,box((30,y,0),(8,3.2,10)))
    for z in (-3,3):hole(o,(30,y,z),1.2,12,'Y')
    finish_part(o,'P13_Forearm_bellcrank_'+str(y),FORE)
for name,y,length in [('front',-22.75,5.5),('middle',-1.75,28.5),('rear',21.25,11.5)]:spacer('P14_Elbow_axle_spacer_'+name,FORE,(0,y,0),length)
finish(cyl((0,-13,0),1.5,96,'Y'),'HW_Elbow_M3_axle',FORE,STEEL,hardware=True,mass=5.8)

# Actual double horn's OUTERMOST 16 mm hole is the pushrod pivot.
o=link(60,-58.5,r0=3.5,r1=3.5)
boolean(o,box((30,-58.5,0),(42,10,6),1.5))
for x in (0,60):hole(o,(x,-58.5,0),.9,12,'Y')
finish_part(o,'P15_Direct_horn_pushrod_60mm',ROD,ORANGE)
finish_part(ring((16,-56.25,0),2.3,.9,1.5),'P16_Crank_pin_spacer',ELBOW_DRIVE,GREY)
finish_part(ring((16,-56.8,0),2.3,.9,.4),'P16_Bellcrank_pin_spacer',FORE,GREY)
for name,parent,c in [('Crank',ELBOW_DRIVE,(16,-56.8,0)),('Bellcrank',FORE,(16,-56.8,0))]:
    finish(cyl(c,.8,10,'Y'),'HW_M1p6_'+name+'_pivot',parent,STEEL,hardware=True,mass=.3)

# Wrist and gripper retain direct single-arm-horn transmission, with screw access.
o=frame('P17_Wrist_motor_frame',FORE,(55,-30,0))
add(o,box((30,-6.5,0),(6,37.8,12),.6))
for z in (-3,3):hole(o,(30,-6.5,z),1,45,'Y')
for y in (-34,20):
    o=link(49,y,r0=15,r1=5)
    hole(o,(0,y,0),3.6 if y<0 else 5.1,14,'Y')
    if y<0:
        for x in (6,11):hole(o,(x,y,0),.9,15,'Y')
    for x in (36,46):hole(o,(x,y,-4),1.2,12,'Y')
    finish_part(o,'P18_Wrist_single_horn_fork_'+str(y),WRIST,GREY)
bearing('HW_623_Wrist',WRIST,(0,20,0))
finish(cyl((55,17,0),1.5,12,'Y'),'HW_Wrist_idler_pin',FORE,STEEL,hardware=True,mass=1)
o=frame('P19_Gripper_servo_palm',WRIST,(41,0,10),False)
for y in (-31.7,17.7):
    add(o,box((41,y,-4),(18,1.6,9),.3))
    add(o,box((41,-19.5 if y<0 else 12.55,-6),(18,25.8 if y<0 else 11.9,2.2),.4))
    for x in (36,46):hole(o,(x,y,-4),1.0,10,'Y')
for x in (52,57):hole(o,(x,-14,-5),1.2,12)
o=box((64,-14,-1.5),(28,6,5),1);add(o,box((72,-14,5),(12,6,18),1))
for x in (52,57):hole(o,(x,-14,-1.5),1.2,12)
finish_part(o,'P20_Fixed_finger',WRIST,GREY,'XY')
o=cyl((0,0,4),10,3);beam=box((15.5,6.5,4),(34,6,3),1);beam.rotation_euler[2]=math.atan2(13,31)
add(o,beam);add(o,box((31,13,-1),(12,6,12),1));hole(o,(0,0,4),3.6,12)
for r in (6,11):hole(o,(r*math.cos(math.atan2(13,31)),r*math.sin(math.atan2(13,31)),4),.9,12)
finish_part(o,'P21_Single_horn_moving_finger',JAW,GREY,'XY')
finish(box((72,-10.5,5),(10,1,10),.3),'HW_Fixed_foam_pad',WRIST,RUBBER,hardware=True,mass=.15)
finish(box((31,9.5,-1),(10,1,10),.3),'HW_Moving_foam_pad',JAW,RUBBER,hardware=True,mass=.15)

# Reuse measured fit coupons; they are standalone, never part of the robot assembly.
for file in sorted((root/'archive/blender_arm_v3/stl').glob('TEST_*.stl')):
    bpy.ops.wm.stl_import(filepath=str(file));o=bpy.context.object
    finish_part(o,file.stem,None,GREY,'XY');o.hide_render=True;o.hide_set(True)

# Robust mesh audit and flat exports before kinematic posing.
rows=[]
for o in PRINT.objects:
    bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.0001);bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
    nm=sum(not e.is_manifold for e in bm.edges);volume=abs(bm.calc_volume());bm.to_mesh(o.data);bm.free()
    o['solid_mass_g']=volume*.00124
    r=Matrix.Rotation(math.pi/2,4,'X') if o['print_plane']=='XZ' else Matrix.Identity(4)
    vs=[r@v.co for v in o.data.vertices];lo=Vector([min(v[k] for v in vs) for k in range(3)])
    exp=bpy.data.objects.new('export_B4',o.data.copy());sc.collection.objects.link(exp);exp.data.transform(Matrix.Translation(-lo)@r)
    active(exp);bpy.ops.wm.stl_export(filepath=str(OUT/'stl'/(o.name+'.stl')),export_selected_objects=True,ascii_format=False)
    bpy.data.objects.remove(exp,do_unlink=True)
    rows.append({'part':o.name,'solid_PLA_mass_g':o['solid_mass_g'],'nonmanifold_edges':nm})

# Closed-chain solver. A = fixed-servo crank pin; C = moving bell-crank pin.
def pose(theta=60,psi=-35,wrist=None,yaw=0,jaw=-8):
    t,p=map(math.radians,(theta,psi));E=Vector((60*math.cos(t),0,90+60*math.sin(t)))
    A=Vector((16*math.cos(p),0,90+16*math.sin(p)))
    phi=p
    if abs(math.sin(t-p))<.3:raise ValueError('Near collinear parallelogram singularity')
    C=E+Vector((16*math.cos(phi),0,16*math.sin(phi)))
    UP.rotation_euler[1]=-t;ELBOW_DRIVE.rotation_euler[1]=-p;FORE.rotation_euler[1]=t-phi
    WRIST.rotation_euler[1]=phi if wrist is None else -math.radians(wrist)
    BASE.rotation_euler[2]=math.radians(yaw);JAW.rotation_euler[2]=math.radians(jaw)
    ROD.location=A;ROD.rotation_euler[1]=-math.atan2((C-A).z,(C-A).x)
    bpy.context.view_layer.update()
    return {'forearm_absolute_deg':math.degrees(phi),'rod_length_mm':(C-A).length,'transmission_sin':abs(math.sin(t-p))}
pose_info=pose()
sc['mechanism']='Coaxial-projection grounded servos -> real double horn R16 -> pinned 60 mm pushrod -> R16 forearm bellcrank; parallelogram'
sc['no_adhesive']=True;sc['no_shoulder_gears']=True;sc['pose_solver']='mechanical/scripts/build_blender_arm_v4.py: pose(theta, psi, wrist, yaw, jaw)'

# Studio rendering of actual geometry.
floor=box((15,0,-4),(600,600,3),2);finish(floor,'Studio_floor',None,mat('Ground',(.16,.20,.24)),hardware=True);collect(floor,STUDIO)
def aim(o,p):o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(300,-440,280));cam=bpy.context.object;collect(cam,STUDIO);aim(cam,(25,0,92))
cam.data.type='ORTHO';cam.data.ortho_scale=295;cam.data.clip_end=3000;sc.camera=cam
for pos,power,size in [((80,-170,400),1800000,220),((-170,-30,270),1100000,180),((160,180,320),2200000,170)]:
    bpy.ops.object.light_add(type='AREA',location=pos);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;aim(o,(20,0,90));collect(o,STUDIO)
sc.render.resolution_x=1500;sc.render.resolution_y=1300;sc.render.resolution_percentage=100;sc.view_settings.view_transform='AgX'
sc.render.filepath=str(OUT/'assembly.png')
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.clip_end=3000;area.spaces.active.region_3d.view_distance=310;area.spaces.active.region_3d.view_location=(25,0,90);area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
active(ELBOW_DRIVE)
(OUT/'build_audit.json').write_text(json.dumps({'parts':rows,'pose':pose_info,'warning':'Build mesh audit only, not collision or payload validation.'},indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'CyberArm_B4_Horn_Linkage.blend'))
print('B4_BUILT',len(rows),'NONMANIFOLD',[(r['part'],r['nonmanifold_edges']) for r in rows if r['nonmanifold_edges']],pose_info)
