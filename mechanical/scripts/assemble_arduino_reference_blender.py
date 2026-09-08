"""Rigid assembly of the user's ORIGINAL STL files. Coordinates in mm.

Original mesh coordinates, scale and topology are never edited. Servo envelopes
are separate purchased-hardware representations, not printable replacement parts.
"""
import bpy, math, json, hashlib
from pathlib import Path
from mathutils import Vector, Matrix

ROOT=Path('E:/下载/大白爱模型_机械臂资料/arduino机械臂/files')
OUT=Path('E:/CyberArm/mechanical/archive/arduino_reference_replica')
OUT.mkdir(exist_ok=True)
V=Vector
def cols(x,y,z): return Matrix((x,y,z)).transposed()
def rotation(axis,degrees): return Matrix.Rotation(math.radians(degrees),3,axis)
def at(R,src,dst):
    M=R.to_4x4();M.translation=V(dst)-R@V(src);return M
def translate(p):return Matrix.Translation(V(p))

previous_scenes=[s for s in bpy.data.scenes if s.name.startswith('Arduino_Original_Replica')]
sc=bpy.data.scenes.new('Arduino_Original_Replica_REBUILD')
bpy.context.window.scene=sc
for previous_scene in previous_scenes:
    for previous_object in list(previous_scene.objects):
        bpy.data.objects.remove(previous_object,do_unlink=True)
    bpy.data.scenes.remove(previous_scene)
sc.name='Arduino_Original_Replica'
sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=.001
sc.unit_settings.length_unit='MILLIMETERS'
def collection(name):
    c=bpy.data.collections.new(name);sc.collection.children.link(c);return c
parts=collection('ARD_01_Original_printed_parts')
servos=collection('ARD_02_Servos_NOT_FOR_PRINT')
hardware=collection('ARD_03_Horns_and_fasteners_REFERENCE')
studio=collection('ARD_04_Studio')
def material(name,color,metal=0,rough=.35):
    m=bpy.data.materials.new('ARD_'+name);m.diffuse_color=(*color,1);m.use_nodes=True
    p=next(n for n in m.node_tree.nodes if n.bl_idname=='ShaderNodeBsdfPrincipled')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
    return m
orange=material('Orange',(1,.19,.018));gray=material('Gray',(.43,.49,.55))
black=material('Servo_black',(.025,.031,.039));gold=material('Output_spline',(.62,.36,.10),.65)
silver=material('Steel',(.48,.52,.57),.75);white=material('Stock_horn',(.87,.88,.83))
red=material('Label',(.7,.018,.045));ground=material('Ground',(.12,.15,.19))

def move_collection(o,c):
    for old in list(o.users_collection):old.objects.unlink(o)
    c.objects.link(o)
def assign(o,m,c):
    move_collection(o,c);o.data.materials.clear();o.data.materials.append(m);return o
manifest=[]
def original(stem,name,M,mat):
    source=bpy.data.objects.get('REF_SCAN_'+stem)
    if source:
        o=bpy.data.objects.new('ARD_'+name,source.data.copy());parts.objects.link(o)
    else:
        bpy.ops.wm.stl_import(filepath=str(ROOT/(stem+'.stl')));o=bpy.context.object
        o.name='ARD_'+name;move_collection(o,parts)
    o.matrix_world=M;o.data.materials.clear();o.data.materials.append(mat)
    o['source_file']=str(ROOT/(stem+'.stl'));o['original_scale']=1.0
    o['geometry_policy']='Original STL; rigid placement only; NOT redesigned'
    # Smooth only cylindrical walls; keep imported triangles and vertices exact.
    for p in o.data.polygons:p.use_smooth=False
    rec={'object':o.name,'source':str(ROOT/(stem+'.stl')),
         'sha256':hashlib.sha256((ROOT/(stem+'.stl')).read_bytes()).hexdigest(),
         'vertices':len(o.data.vertices),'triangles':len(o.data.polygons),
         'matrix_world':[list(row) for row in M],'scale':list(o.scale)}
    manifest.append(rec);return o

def box(name,center,size,M,mat=black,c=servos,bevel=.4):
    bpy.ops.mesh.primitive_cube_add(size=1);o=bpy.context.object;o.name='ARD_'+name
    o.scale=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.matrix_world=M@translate(center);assign(o,mat,c)
    if bevel:
        b=o.modifiers.new('Small molded edges','BEVEL');b.width=bevel;b.segments=2
        o.modifiers.new('Corner normals','WEIGHTED_NORMAL')
    return o
def cylinder(name,p,r,depth,M,mat=silver,c=hardware,vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=depth)
    o=bpy.context.object;o.name='ARD_'+name;o.matrix_world=M@translate(p);assign(o,mat,c)
    return o
def empty(name,M):
    o=bpy.data.objects.new('ARD_'+name,None);hardware.objects.link(o)
    o.matrix_world=M;o.empty_display_type='ARROWS';o.empty_display_size=9;o.hide_render=True
    return o

servo_records=[]
def big_servo(name,M):
    """MG996R envelope: official overall 40.7 x 19.7 x 42.9.
    48 x 10 hole pattern represents measured STL seats, not a vendor-certified CAD.
    """
    root=empty(name+'_axis',M);root['representation']='MG996R dimension envelope; detailed mounting measurements provisional'
    body=box(name+'_MG996R_BODY',(-10.25,0,-24.6),(40.7,19.7,36.6),M)
    body['type']='MG996R_REFERENCE_ENVELOPE';body['NOT_FOR_PRINT']=True
    box(name+'_case_seam',(-10.25,0,-13),(40.85,19.85,.5),M,gray,bevel=.1)
    for x in (-34.25,13.75):
        ear=box(name+'_ear_'+str(x),(x,0,-17.55),(6,19.7,2.5),M,bevel=.25)
        for y in (-5,5):
            cylinder(name+'_mount_screw',(x,y,-15.5),2,1.5,M)
    cylinder(name+'_gear_cap',(0,0,-5.1),6.3,3,M,black,servos)
    cylinder(name+'_output_spline',(0,0,-1.8),3,3.6,M,gold,servos)
    box(name+'_label',(-10.25,-9.91,-25),(27,.12,10),M,red,bevel=0)
    servo_records.append({'name':name,'type':'MG996R envelope','shaft_origin':list(M.translation),
       'shaft_direction':list(M.to_3x3()@V((0,0,1))), 'mount_hole_pitch_mm':[48,10],
       'note':'Body dimensions from TowerPro; mounting envelope inferred from original STL, verify real hardware.'})
    return root

SERVO=next(Path('E:/CyberArm/mechanical').glob('伺服电机模型*/servo_MG90S.STL'))
mini_mesh=None
def mini_servo(name,M):
    global mini_mesh
    if mini_mesh is None:
        bpy.ops.wm.stl_import(filepath=str(SERVO));tmp=bpy.context.object
        mini_mesh=tmp.data.copy();mini_mesh.name='ARD_MG90S_user_source_normalized'
        for v in mini_mesh.vertices:
            x,y,z=v.co;v.co=(x-21.325,z-6.0254,y-32.1)
        bpy.data.objects.remove(tmp,do_unlink=True)
    o=bpy.data.objects.new('ARD_'+name+'_MG90S_USER_MODEL',mini_mesh.copy());servos.objects.link(o)
    o.matrix_world=M;o.data.materials.clear();o.data.materials.append(black)
    o['source_file']=str(SERVO);o['NOT_FOR_PRINT']=True
    o['fit_status']='Original SG90 seat with actual MG90S comparison; horn pattern NOT a confirmed drop-in fit'
    cylinder(name+'_gold_shaft',(0,0,-1),2.4,2,M,gold,servos)
    servo_records.append({'name':name,'type':'User MG90S STL in original SG90 seat',
       'shaft_origin':list(M.translation),'shaft_direction':list(M.to_3x3()@V((0,0,1))),
       'note':'Original seat pitch 27.6; source MG90S pitch 27.894. Supplied horn pitch differs from original 9 mm pattern.'})
    return o

def horn(name,M,large=True,plate=6):
    # Simplified ORIGINAL required horn interface, not a claim of spline-fit.
    if large:
        o=cylinder(name+'_stock_round_horn',(0,0,1.25),10,2.5,M,white)
        for x in (-7.25,7.25):cylinder(name+'_horn_screw',(x,0,2.5+plate+.6),1.8,1.2,M)
    else:
        o=box(name+'_required_9mm_horn',(0,0,1.1),(14,6,2.2),M,white,hardware,1)
        for x in (-4.5,4.5):cylinder(name+'_horn_screw',(x,0,3),1.5,1.2,M)
    o['reference_only']='Original required horn interface; spline/stock horn details not modeled or certified'
    cylinder(name+'_center_screw',(0,0,3),1.7,1.2,M)

# Base: native Y is vertical; native X becomes global Y.
T=cols((0,1,0),(0,0,1),(1,0,0))
B=at(T,(40.779,36.107574,92.88),(0,0,0))
base=original('Base','01_Base',B,gray)
for i in range(4):
    M=rotation('Z',90*i).to_4x4()@B
    original('Pata_de_Soporte','02_Foot_'+str(i+1),M,gray)
# Feet retain original coordinates: the bolt at 79.446,131.993 mates to base.
BY=cols((0,1,0),(-1,0,0),(0,0,1))
S0=at(BY,(0,0,0),(0,0,54.3));big_servo('S01_Base',S0)
horn('S01',at(Matrix.Identity(3),(0,0,0),S0.translation),plate=4)
W=at(T,(0,0,0),(0,0,57.1));waist=original('Waist','03_Waist',W,orange)

# Shoulder mount rectangle and shaft hole were measured from Waist.stl.
s=math.sqrt(.5)
RS=cols((0,s,-s),(0,s,s),(1,0,0))
S1=W@at(RS,(0,0,0),(-1.7,40.275986,-13.919))
big_servo('S02_Shoulder',S1)
theta=math.radians(43)
D=V((math.cos(theta),0,math.sin(theta)));X=V((math.sin(theta),0,-math.cos(theta)))
U=at(cols(-X,D,(0,1,0)),(0,0,0),W@V((.8,40.275986,-13.919)))
horn('S02',at(cols(D,X,(0,1,0)),(0,0,0),S1.translation))
upper=original('Arm_01','04_Arm_01',U,orange)
EP=U@V((0,120,0))

# Elbow MG996R is carried by Arm_02, its output screws into Arm_01.
theta2=math.radians(-38)
D2=V((math.cos(theta2),0,math.sin(theta2)));X2=V((math.sin(theta2),0,-math.cos(theta2)))
RF=cols(X2,D2,(0,-1,0))
F=at(RF,(0,-34.75,-6.3),EP+V((0,-2.5,0)))
fore=original('Arm_02_v3','05_Arm_02_v3',F,orange)
RE=cols((0,-1,0),(-1,0,0),(0,0,-1))
S2=F@at(RE,(0,0,0),(0,-34.75,-6.3));big_servo('S03_Elbow',S2)
# Horn rotates with the upper arm, but its bolt line is along the arm.
RH=cols(D,X,(0,1,0));horn('S03',at(RH,(0,0,0),EP+V((0,-2.5,0))))

RM=cols((-1,0,0),(0,0,1),(0,1,0))
S3=F@at(RM,(0,0,0),(-5.3,56.075,5.5));mini_servo('S04_Wrist_roll',S3)
horn('S04',S3,False)
A=F@at(Matrix.Identity(3),(-5,0,0),(-5.3,58.575,5.5))
wrist=original('Arm_03','06_Arm_03',A,orange)
RP=cols((0,1,0),(1,0,0),(0,0,-1))
S4=A@at(RP,(0,0,0),(0,28,-14.575));mini_servo('S05_Wrist_pitch',S4)
horn('S05',S4,False)
RG=cols((0,0,-1),(-1,0,0),(0,1,0))
G=A@at(RG,(9,-9,-63),(0,28,-17.075))
palm=original('Gripper_base','07_Gripper_base',G,gray)
RGM=cols((1,0,0),(0,0,-1),(0,1,0))
S5=G@at(RGM,(0,0,0),(31.9,5.575,-25));mini_servo('S06_Gripper',S5)

# Exact four-bar closure from the actual STL pin centers (31 / 30.75 / 22 mm).
def intersection(c0,r0,c1,r1):
    dv=c1-c0;dist=dv.length;unit=dv/dist
    a=(r0*r0-r1*r1+dist*dist)/(2*dist);h=math.sqrt(max(0,r0*r0-a*a))
    normal=V((-unit.z,0,unit.x));mid=c0+a*unit
    return max((mid+h*normal,mid-h*normal),key=lambda p:p.z)
gear_y=8.4
gripper_checks=[]
for side,stem,cx,ang in [('Left','gear1',5,-155),('Right','gear2',31.9,147.5)]:
    CR=rotation('Y',ang);center=V((cx,gear_y,-25))
    GM=at(CR,(-10.10634,0,0),center)
    original(stem,'08_'+stem,G@GM,gray)
    endpoint=V((20.64366,0,0)) if side=='Left' else V((-40.592571,0,4.01368))
    C=GM@endpoint
    A0=V((13 if side=='Left' else 23,gear_y,-5))
    C2=intersection(C,22,A0,31)
    lx=(C2-A0).normalized();ly=V((0,1,0));lz=lx.cross(ly)
    LM=at(cols(lx,ly,lz),(0,0,0),A0)
    original('grip_link_1','09_Link_'+side,G@LM,gray)
    jx=V((0,1 if side=='Left' else -1,0));jz=(C-C2).normalized();jy=jz.cross(jx)
    source_x=0 if side=='Left' else 8.5
    JM=at(cols(jx,jy,jz),(source_x,5,-5),C+V((0,4.4,0)))
    original('Gripper_1' if side=='Left' else 'Gripper_1_1','10_Jaw_'+side,G@JM,gray)
    for n,P in [('gear',center),('crank',C),('link_base',A0),('link_tip',C2)]:
        # Pins normal to original gripper plate; head and shank are separate hardware.
        pinR=cols((1,0,0),(0,0,-1),(0,1,0))
        P=V(P);P.y=11.8
        PM=G@at(pinR,(0,0,0),P)
        cylinder(side+'_'+n+'_pin',(0,0,0),1.5,14,PM)
        cylinder(side+'_'+n+'_head',(0,0,7.4),2.65,1.8,PM)
    gripper_checks.append({'side':side,'gear_crank_mm':(C-center).length,
       'link_mm':(C2-A0).length,'jaw_pitch_mm':(C2-C).length,
       'closure_error_mm':max(abs((C2-A0).length-31),abs((C2-C).length-22))})
horn('S06',G@at(rotation('Y',147.5)@RGM,(0,0,0),(31.9,5.9,-25)),False)

# Studio and views. Original/source objects are in a separate scene, not deleted.
box('Display_ground',(70,0,-3),(2000,2000,5),Matrix.Identity(4),ground,studio,0)
world=bpy.data.worlds.new('ARD_World');sc.world=world;world.use_nodes=True
background=next(n for n in world.node_tree.nodes if n.bl_idname=='ShaderNodeBackground')
background.inputs[0].default_value=(.18,.22,.29,1)
background.inputs[1].default_value=.45
def aim(o,target):o.rotation_euler=(V(target)-o.location).to_track_quat('-Z','Y').to_euler()
def area(name,loc,power,size):
    data=bpy.data.lights.new('ARD_'+name,'AREA');data.energy=power;data.shape='DISK';data.size=size
    o=bpy.data.objects.new('ARD_'+name,data);studio.objects.link(o);o.location=loc;aim(o,(70,0,90))
area('Key',(-100,-250,500),7000000,350)
area('Fill',(350,100,320),5000000,300)
area('Rim',(-80,250,330),6000000,260)
data=bpy.data.cameras.new('ARD_Camera');cam=bpy.data.objects.new('ARD_Camera',data)
studio.objects.link(cam);cam.location=(400,-580,350);aim(cam,(80,0,97))
data.type='ORTHO';data.ortho_scale=420;data.clip_end=5000;sc.camera=cam
sc.render.engine='CYCLES';sc.cycles.samples=24
sc.render.resolution_x=1600;sc.render.resolution_y=1300;sc.render.resolution_percentage=100
sc.render.image_settings.file_format='PNG';sc.render.filepath=str(OUT/'Arduino_Original_Replica.png')
sc.view_settings.view_transform='AgX'
sc['Assembly_status']='Original STL rigid assembly; original large servos MG996R; MG90S shown at original SG90 seats for fit review'
sc['Original_reference']='https://howtomechatronics.com/tutorials/arduino/diy-arduino-robot-arm-with-smartphone-control/'
sc['Not_print_release']='Servo axial stack, horn spline and real fits require physical measurement; no load rating implied.'

bpy.context.view_layer.update()
for o in sc.objects:o.select_set(False)
upper.select_set(True);bpy.context.view_layer.objects.active=upper
for screen in bpy.data.screens:
    for area0 in screen.areas:
        if area0.type=='VIEW_3D':
            space=area0.spaces.active;space.clip_end=10000;space.shading.type='MATERIAL'
            space.region_3d.view_distance=450;space.region_3d.view_location=(80,0,90)
            space.region_3d.view_rotation=cam.rotation_euler.to_quaternion()

report={'source_root':str(ROOT),'printed_instances':len(manifest),'unique_STL':len(set(x['source'] for x in manifest)),
 'parts':manifest,'servos':servo_records,'four_bar_checks':gripper_checks,
 'upper_arm_joint_pitch_mm':120,'base_flange_diameter_mm':130,'base_body_diameter_mm':98,
 'notes':['All original printed meshes unchanged at scale 1.',
 'MG996R modeled as labeled dimension envelope, not downloaded manufacturer CAD.',
 'Three user MG90S models are provisional substitutes in original SG90 seats.',
 'Original 9 mm small-horn bolt pitch does not match supplied MG90S horns; no drop-in claim.',
 'Axial stack based on source seats and nominal servo envelope; verify real horns before printing/assembly.',
 'Static assembly only; no certified collision-free joint range or payload.']}
(OUT/'assembly_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Arduino_Original_Replica.blend'))
print(json.dumps({'saved':str(OUT/'Arduino_Original_Replica.blend'),'printed_instances':len(manifest),'servos':len(servo_records),'gripper':gripper_checks}))
