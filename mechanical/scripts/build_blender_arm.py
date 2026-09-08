"""CyberArm B2: millimetre geometry, actual MG90S mesh, separable printable parts.
Run through blender_mcp_client.py in a new Blender scene.
This is a fit-test prototype; see engineering_report.md for qualified limits.
"""
import bpy, bmesh, math, json, csv
from pathlib import Path
from mathutils import Vector, Matrix, Quaternion
from mathutils.geometry import tessellate_polygon

OUT=Path('E:/CyberArm/mechanical/archive/blender_arm_v2')
OUT.mkdir(exist_ok=True)
(OUT/'stl').mkdir(exist_ok=True)
for old in list(bpy.data.scenes):
    if old.name.startswith('CyberArm_B2_Engineering'):
        for o in list(old.objects):bpy.data.objects.remove(o,do_unlink=True)
        bpy.data.scenes.remove(old)
sc=bpy.data.scenes.new('CyberArm_B2_Engineering')
bpy.context.window.scene=sc
sc.unit_settings.system='METRIC'; sc.unit_settings.scale_length=0.001
sc.unit_settings.length_unit='MILLIMETERS'
sc.render.engine='CYCLES'; sc.cycles.samples=32
sc.world=bpy.data.worlds.new('Studio_world'); sc.world.use_nodes=True
bg=next(n for n in sc.world.node_tree.nodes if n.type=='BACKGROUND')
bg.inputs[0].default_value=(0.15,0.18,0.23,1)
bg.inputs[1].default_value=0.5
PRINT=bpy.data.collections.new('01_PRINT_PARTS'); sc.collection.children.link(PRINT)
REF=bpy.data.collections.new('02_PURCHASED_HARDWARE'); sc.collection.children.link(REF)
RIG=bpy.data.collections.new('03_JOINTS'); sc.collection.children.link(RIG)
STUDIO=bpy.data.collections.new('04_STUDIO'); sc.collection.children.link(STUDIO)

def mat(name,c,metal=0):
    m=bpy.data.materials.new(name); m.diffuse_color=(*c,1);m.use_nodes=True
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'); p.inputs['Base Color'].default_value=(*c,1)
    p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=0.33
    return m
ORANGE=mat('PLA_safety_orange',(0.85,0.17,0.027))
GREY=mat('PLA_graphite',(0.075,0.10,0.135))
BLUE=mat('MG90S_source_model',(0.07,0.23,0.43),0.15)
STEEL=mat('Purchased_steel',(0.44,0.48,0.52),0.8)
WHITE=mat('Purchased_nylon_horn',(0.88,0.89,0.81))
RUBBER=mat('Adhesive_foam_pad',(0.04,0.04,0.04))

def collect(o,col):
    for c in list(o.users_collection):c.objects.unlink(o)
    col.objects.link(o)
def active(o):
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
def box(c,d,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=c);o=bpy.context.object;o.dimensions=d
    active(o);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        m=o.modifiers.new('Edge_round','BEVEL');m.width=bevel;m.segments=3
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o
def cyl(c,r,h,axis='Z',n=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=n,radius=r,depth=h,location=c)
    o=bpy.context.object
    if axis=='Y':o.rotation_euler[0]=math.pi/2
    elif axis=='X':o.rotation_euler[1]=math.pi/2
    active(o);bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    return o
def boolean(o,t,op='DIFFERENCE'):
    # Cutters are specified in the target's component coordinates.
    t.parent=o.parent
    active(o);m=o.modifiers.new(op,'BOOLEAN');m.operation=op;m.solver='EXACT';m.object=t
    bpy.ops.object.modifier_apply(modifier=m.name);bpy.data.objects.remove(t,do_unlink=True)
    return o
def add(o,t):return boolean(o,t,'UNION')
def hole(o,c,r,h=100,axis='Z'):return boolean(o,cyl(c,r,h,axis))
def finish(o,name,parent=None,material=ORANGE,orient='XY',hardware=False,mass=None):
    # Bake geometry in component coordinates. Joint parenting remains editable.
    active(o);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    o.name=name;o.data.name=name+'_mesh';o.parent=parent
    collect(o,REF if hardware else PRINT);o.data.materials.clear();o.data.materials.append(material)
    o['print_plane']=orient;o['purpose']='purchased_reference' if hardware else 'FDM_part'
    if mass is not None:o['mass_g']=mass
    return o
def joint(name,parent=None,at=(0,0,0)):
    o=bpy.data.objects.new(name,None);RIG.objects.link(o);o.empty_display_type='ARROWS';o.empty_display_size=10
    o.parent=parent;o.location=at;return o
BASE=joint('J0_YAW');UP=joint('J1_SHOULDER_3_to_1',BASE,(0,0,130))
FORE=joint('J2_ELBOW',UP,(80,0,0));WRIST=joint('J3_WRIST',FORE,(70,0,0))
JAW=joint('J4_GRIPPER',WRIST,(60,0,8))
BASE['range_deg']='initial -45..45';UP['range_deg']='initial 45..80 elevation; 3:1 reduces servo travel'
FORE['range_deg']='initial -100..-60 physical relative angle (Euler Y sign reversed)'
WRIST['range_deg']='initial keep palm horizontal: Euler Y = shoulder elevation + elbow relative'
JAW['range_deg']='initial -30..0; stop contact begins before -34; no rigid object crushing'

# Normalize the actual user-supplied STL to shaft-tip origin and output +Z.
source=next(Path('E:/CyberArm/mechanical').rglob('servo_MG90S.STL'))
bpy.ops.wm.stl_import(filepath=str(source));master=bpy.context.object
for v in master.data.vertices:
    x,y,z=v.co;v.co=(x-21.325,z-6.0254,y-32.1)
servo_mesh=master.data.copy();bpy.data.objects.remove(master,do_unlink=True)
pitch=Matrix(((1,0,0),(0,0,-1),(0,1,0))).to_4x4()
def servo(name,parent,at,pitched=True):
    o=bpy.data.objects.new(name,servo_mesh);REF.objects.link(o);o.parent=parent
    o.matrix_basis=Matrix.Translation(Vector(at)) @ (pitch if pitched else Matrix.Identity(4))
    o.data.materials.clear();o.data.materials.append(BLUE);o['mass_g']=13.4;o['source']=str(source)
    return o
servo('HW_MG90S_0_Yaw',None,(0,0,36),False)
servo('HW_MG90S_1_Shoulder',BASE,(0,-13,90))
servo('HW_MG90S_2_Elbow',UP,(80,-13,0))
servo('HW_MG90S_3_Wrist',FORE,(70,-13,0))
servo('HW_MG90S_4_Gripper',WRIST,(60,0,8),False)

def servo_frame(name,parent,at,pitched=True):
    o=box((-5.2,0,-14.95),(37,20,3),0.7)
    boolean(o,box((-5.2,0,-14.95),(23.0,12.65,8)))
    for x in (-19.147,8.747):hole(o,(x,0,-14.95),1.2,12)
    # Every frame uses the measured ear-hole pattern; no printed spline.
    active(o);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    tf=Matrix.Translation(Vector(at)) @ (pitch if pitched else Matrix.Identity(4))
    o.data.transform(tf)
    return finish(o,name,parent,GREY,'XZ' if pitched else 'XY')

# Base plate and stationary motor mount. M4 desk mounting holes.
o=box((0,0,2),(140,120,4),6)
boolean(o,box((-5.2,0,4),(23,12.7,1)))
for x in (-60,60):
    for y in (-50,50):hole(o,(x,y,2),2.25,12)
for x in (-25,25):
    for y in (-24,24):hole(o,(x,y,2),1.7,12)
for x in (-19.147,8.747):
    if x<0:add(o,cyl((x,0,11.775),2.3,15.55))
    else:
        for y in (-4.5,4.5):add(o,cyl((x,y,11.775),2.3,15.55))
        add(o,box((x,0,18.45),(4.6,13.6,2.2),0.3))
    hole(o,(x,0,18),1.05,6)
for x,y in ((-52,-42),(-52,-14),(-48,30),(-48,46)):hole(o,(x,y,2),1.7,12)
finish(o,'P01_Base_plate',None,GREY)
servo_frame('P02_Yaw_servo_frame',None,(0,0,36),False)

# Split bearing pedestal. Two 6804 bearings: 20 x 32 x 7, 14 mm centre spacing.
for side in (-1,1):
    o=box((0,0,51),(46,44,22),1.5)
    hole(o,(0,0,51),12.4,35)
    for z in (44,58):hole(o,(0,0,z),16.1,7.2)
    boolean(o,box((-side*30,0,51),(60.2,70,40)))
    for y in (-24,24):
        add(o,box((side*25,y,33),(8,10,58),1))
        add(o,box((side*22,y,59),(12,10,6),0.5))
        hole(o,(side*25,y,33),1.7,70)
    # Horizontal housing clamp screws, away from bearing circles.
    for y in (-19,19):hole(o,(0,y,51),1.65,60,'X')
    finish(o,'P03_Bearing_pedestal_'+('L' if side<0 else 'R'),None,GREY,'XZ')
for z in (44,58):
    o=cyl((0,0,z),16,7);hole(o,(0,0,z),10,10)
    finish(o,'HW_6804_'+str(z),None,STEEL,hardware=True,mass=15)

# Rotor can be assembled: bearings slide over its free upper end before turret installation.
o=cyl((0,0,50.75),9.925,23.5)
add(o,cyl((0,0,38.5),12,3));hole(o,(0,0,49),2.7,40)
for a in (0,120,240):
    x,y=7*math.cos(math.radians(a)),7*math.sin(math.radians(a));hole(o,(x,y,58),0.9,12)
for x in (-7,7):hole(o,(x,0,38.5),1.05,6)
finish(o,'P04_Yaw_spindle',BASE,GREY)
# Axial load travels through the upper bearing INNER race, not the servo shaft.
# Shim OD must match the actual bearing inner-race shoulder; nominal envelope only.
for tag,z,h in [('lower',40.25,0.5),('upper',61.95,0.9)]:
    o=cyl((0,0,z),12,h);hole(o,(0,0,z),10.05,h+4)
    finish(o,'HW_20mm_axial_shim_'+tag,BASE,STEEL,hardware=True,mass=math.pi*(12**2-10.05**2)*h*.00785)
o=cyl((0,0,64.5),34,4)
for a in (0,120,240):
    x,y=7*math.cos(math.radians(a)),7*math.sin(math.radians(a));hole(o,(x,y,64.5),1.2,10)
hole(o,(0,0,64.5),2.7,10)
for x in (-16,16):
    for y in (-10,20):
        hole(o,(x,y,64.5),1.65,10)
        boolean(o,cyl((x,y,65.2),3.3,2.6,n=6))
finish(o,'P05_Turret',BASE,GREY)

# Shoulder fixed cheeks carry the axle, motor torque, and bending into the turret.
for y in (-10,20):
    o=box((0,y,99),(52,4,64),0.8)
    add(o,box((0,y,69),(52,12,5),0.8))
    add(o,cyl((0,y,130),8.5,4,'Y'))
    hole(o,(0,y,130),5.1,12,'Y')
    boolean(o,box((0,y,111),(19,10,17),2))
    if y<0:
        hole(o,(0,y,90),7,12,'Y');hole(o,(-6.469,y,90),2.85,12,'Y')
    else:boolean(o,box((-5.2,y,90),(23,10,12.7),0.6))
    for x in (-16,16):hole(o,(x,y,68),1.65,12)
    finish(o,'P06_Shoulder_cheek_'+str(y),BASE,GREY,'XZ')
shoulder_mount=servo_frame('P07_Shoulder_motor_frame',BASE,(0,-13,90))
for x in (-23.2,12.8):
    o=box((x,5,90),(4,25.6,12),0.6)
    hole(o,(x,5,90),1.25,40,'Y')
    add(shoulder_mount,o)
for x in (-19.147,8.747):boolean(shoulder_mount,box((x,-0.9,90),(6.6,2.8,12.65)))
boolean(shoulder_mount,box((12,14.8,90),(12,5,4)))
for cheek in list(PRINT.objects):
    if cheek.name.startswith('P06_Shoulder_cheek'):
        for x in (-23.2,12.8):hole(cheek,(x,cheek.data.vertices[0].co.y,90),1.65,70,'Y')

def bearing_y(name,parent,x,y,z):
    o=cyl((x,y,z),5,4,'Y');hole(o,(x,y,z),1.5,8,'Y')
    return finish(o,name,parent,STEEL,hardware=True,mass=1.8)
for y in (-10,20):bearing_y('HW_623_Shoulder_'+str(y),BASE,0,y,130)
finish(cyl((0,0,130),1.5,66,'Y'),'HW_M3_Shoulder_axle',BASE,STEEL,hardware=True,mass=4.0)
for tag,y,length in [('left',-13.65,3.3),('right',23.8,3.6)]:
    o=cyl((0,y,0),2.8,length,'Y');hole(o,(0,y,0),1.65,length+4,'Y')
    finish(o,'P21_Shoulder_axle_spacer_'+tag,UP,GREY,'XZ')

def involute_gear(n,m=1,backlash=0.18,thick=5):
    rp=m*n/2;rb=rp*math.cos(math.radians(20));rr=rp-1.25*m;ra=rp+m
    inv=lambda r: math.sqrt(max(0,(r/rb)**2-1))-math.acos(min(1,rb/r))
    half=math.pi/(2*n)-backlash/(2*rp)
    pts=[]
    for k in range(n):
        c=2*math.pi*k/n
        pts.append((rr*math.cos(c-math.pi/n),rr*math.sin(c-math.pi/n)))
        radii=[max(rb,rr)+(ra-max(rb,rr))*i/8 for i in range(9)]
        ab=half+inv(rp)-inv(max(rb,rr))
        pts.append((rr*math.cos(c-ab),rr*math.sin(c-ab)))
        for r in radii:
            a=c-(half+inv(rp)-inv(r));pts.append((r*math.cos(a),r*math.sin(a)))
        for r in reversed(radii):
            a=c+(half+inv(rp)-inv(r));pts.append((r*math.cos(a),r*math.sin(a)))
        pts.append((rr*math.cos(c+ab),rr*math.sin(c+ab)))
    verts=[(x,y,z) for z in (-thick/2,thick/2) for x,y in pts];N=len(pts)
    faces=[tuple(reversed(range(N))),tuple(range(N,2*N))]
    faces += [(i,(i+1)%N,(i+1)%N+N,i+N) for i in range(N)]
    mesh=bpy.data.meshes.new('Involute');mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new('gear',mesh);sc.collection.objects.link(o)
    return o
def into_pitch(o,at):
    active(o);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    o.data.transform(Matrix.Translation(Vector(at))@pitch);return o

o=involute_gear(20);hole(o,(0,0,0),2.7,12)
for x in (-7,7):hole(o,(x,0,0),1.05,12)
active(o);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
o.data.transform(Matrix.Rotation(math.radians(9),4,'Z'))
drive=joint('J1_PINION_DRIVE',BASE,(0,-17.8,90))
dc=drive.driver_add('rotation_euler',1).driver;dc.expression='-3*a'
v=dc.variables.new();v.name='a';v.type='SINGLE_PROP';v.targets[0].id=UP;v.targets[0].data_path='rotation_euler[1]'
finish(into_pitch(o,(0,0,0)),'P09_Shoulder_pinion_20T',drive,ORANGE,'XZ')
o=involute_gear(60);hole(o,(0,0,0),1.7,12)
for a in (0,120,240):
    hole(o,(11*math.cos(math.radians(a)),11*math.sin(math.radians(a)),0),1.7,12)
for a in range(0,360,60):
    hole(o,(20*math.cos(math.radians(a)),20*math.sin(math.radians(a)),0),5.5,12)
finish(into_pitch(o,(0,-17.8,0)),'P10_Shoulder_wheel_60T',UP,ORANGE,'XZ')

def rail(name,parent,L,y,width=14,prox=10,dist=10,center=1.7):
    o=box((L/2,y,0),(L,2.8,width),0.6)
    add(o,cyl((0,y,0),prox,2.8,'Y'));add(o,cyl((L,y,0),dist,2.8,'Y'))
    boolean(o,box((L/2,y,0),(L-34,9,6),2))
    hole(o,(0,y,0),center,10,'Y')
    return o
for y in (-25,27):
    o=rail('upper',UP,80,y,prox=14,dist=10)
    for a in (0,120,240):hole(o,(11*math.cos(math.radians(a)),y,11*math.sin(math.radians(a))),1.7,10,'Y')
    hole(o,(80,y,0),2.7 if y<0 else 1.7,10,'Y')
    if y>0:hole(o,(80,y,5),0.85,10,'Z')
    # Bolted cross ties overlap these end tabs, with matching transverse holes.
    for x in (55,):
        add(o,box((x,y,0),(8,3.2,12)))
        for z in (-3,3):hole(o,(x,y,z),1.2,12,'Y')
    finish(o,'P11_Upper_rail_'+str(y),UP,ORANGE,'XZ')
for a in (0,120,240):
    x,z=11*math.cos(math.radians(a)),11*math.sin(math.radians(a))
    o=cyl((x,-21.95,z),2.8,3.3,'Y');hole(o,(x,-21.95,z),1.65,8,'Y')
    finish(o,'P12_Gear_spacer_'+str(a),UP,GREY,'XZ')

def distal_mount(parent,L,ys,tag):
    mount=servo_frame('P_'+tag+'_motor_frame',parent,(L,-13,0))
    for x in (L-25,):
        length=ys[1]-ys[0]-3.4
        o=box((x,sum(ys)/2,0),(6,length,12),0.6)
        for z in (-3,3):hole(o,(x,sum(ys)/2,z),1.0,length+5,'Y')
        add(mount,o)
distal_mount(UP,80,(-25,27),'Elbow')
distal_mount(FORE,70,(-18,22),'Wrist')
for y in (-18,22):
    o=rail('forearm',FORE,70,y,prox=11,dist=13.5,center=2.7 if y<0 else 5.1)
    if y<0:
        for x in (-7,7):hole(o,(x,y,0),1.05,10,'Y')
    hole(o,(70,y,0),9.3 if y<0 else 1.7,10,'Y')
    if y>0:hole(o,(70,y,5),0.85,10,'Z')
    for x in (45,):
        add(o,box((x,y,0),(8,3.2,12)))
        for z in (-3,3):hole(o,(x,y,z),1.2,12,'Y')
    finish(o,'P13_Forearm_rail_'+str(y),FORE,ORANGE,'XZ')
bearing_y('HW_623_Elbow_idler',FORE,0,22,0)
finish(cyl((80,25,0),1.5,10,'Y'),'HW_M3_Elbow_idler',UP,STEEL,hardware=True,mass=1)

# Wrist fork nests OUTSIDE the forearm, leaving axial clearance at both sides.
for y in (-25,29):
    o=cyl((0,y,0),10,2.8,'Y')
    add(o,box((29,y,-3),(58,3.0,9),0.6))
    hole(o,(0,y,0),2.7 if y<0 else 5.1,10,'Y')
    if y<0:
        for x in (-7,7):hole(o,(x,y,0),1.05,10,'Y')
    for x in (45,52):hole(o,(x,y,-5),1.2,12,'Y')
    finish(o,'P14_Wrist_fork_'+str(y),WRIST,ORANGE,'XZ')
bearing_y('HW_623_Wrist_idler',WRIST,0,29,0)
finish(cyl((70,25,0),1.5,12,'Y'),'HW_M3_Wrist_idler',FORE,STEEL,hardware=True,mass=1)
# Horn extension rings put the wrist drive beyond the forearm rail.
o=cyl((0,-19.45,0),9,8.0,'Y');hole(o,(0,-19.45,0),2.7,14,'Y')
for x in (-7,7):hole(o,(x,-19.5,0),1.05,14,'Y')
finish(o,'P15_Wrist_horn_extension',WRIST,GREY,'XZ')
o=box((56.5,2,-7),(43,49,3),1)
boolean(o,box((54.8,0,-7),(23,12.65,10)))
for x in (40.853,68.747):hole(o,(x,0,-7),1.2,10)
for y in (-22.7,26.7):
    add(o,box((48.5,y,-4),(16,1.6,10),0.3))
    for x in (45,52):hole(o,(x,y,-5),1.05,14,'Y')
for x in (71,77):hole(o,(x,-15,-7),1.2,12)
finish(o,'P16_Gripper_palm_servo_frame',WRIST,GREY)

# Asymmetric lever gripper: fixed finger and horn-driven moving finger.
o=box((84,-15,-3),(31,6,5),1)
add(o,box((95,-15,3),(12,6,19),1))
add(o,cyl((87.23,-12.57,3),2.5,17))
for x in (71,77):hole(o,(x,-15,-3),1.2,12)
finish(o,'P17_Fixed_finger',WRIST,ORANGE)
o=cyl((0,0,3.7),10,3)
beam=box((17.5,7,3.7),(38,6,3),1);beam.rotation_euler[2]=math.atan2(14,35)
add(o,beam);add(o,box((35,14,-1),(12,6,12),1))
hole(o,(0,0,3.7),2.7,12)
for x in (-7,7):hole(o,(x,0,3.7),1.05,12)
finish(o,'P18_Moving_finger',JAW,ORANGE)
finish(box((95,-11.5,4),(10,1,12),0.3),'HW_Fixed_foam_pad',WRIST,RUBBER,hardware=True,mass=0.15)
finish(box((35,10.5,-1),(10,1,10),0.3),'HW_Moving_foam_pad',JAW,RUBBER,hardware=True,mass=0.15)

# Actual horn spline stays a purchased part. These visual disks are explicit templates.
for name,parent,at,pitched in [('Yaw',None,(0,0,36.8),False),('Shoulder',BASE,(0,-14.2,90),True),('Elbow',FORE,(0,-14.2,0),True),('Wrist',WRIST,(0,-14.2,0),True),('Gripper',JAW,(0,0,1),False)]:
    o=cyl((0,0,0),9,2)
    hole(o,(0,0,0),1.1,6)
    for x in (-7,7):hole(o,(x,0,0),0.8,6)
    if pitched:into_pitch(o,at)
    else:o.location+=Vector(at)
    finish(o,'HW_Horn_TEMPLATE_'+name,parent,WHITE,hardware=True,mass=0.8)

# Electronics remain fixed, secured with straps through universal slots.
o=box((-48,38,7.1),(34,32,6),2)
for y in (30,46):hole(o,(-48,y,7.1),1.7,12)
for x in (-60,-35):
    for y in (19,45):boolean(o,box((x,y,7),(3,12,12),1))
finish(o,'P19_Electronics_strap_deck',None,GREY)
o=box((-52,-28,7),(32,44,6),2)
for y in (-42,-14):hole(o,(-52,y,7),1.7,12)
add(o,box((-60,-28,58),(6,14,100),1))
add(o,box((-60,-28,123),(5,72,50),2))
for y in (-54,-2):
    for z in (110,137):boolean(o,box((-60,y,z),(12,3,10),1))
boolean(o,box((-60,-28,123),(12,34,22),3))
finish(o,'P20_K230D_fixed_strap_mast',None,GREY,'YZ')
finish(box((-48,-28,123),(15.4,64.3,47.6),1),'HW_K230D_BOX_envelope',None,BLUE,hardware=True,mass=60)

# Fit coupon: measured servo ear pattern, 3 bearing-seat variants and M3 holes.
o=box((0,0,2),(75,35,4),1)
boolean(o,box((-20,0,2),(23,12.65,10)))
for x in (-33.947,-6.053):hole(o,(x,0,2),1.2,10)
for x,d in ((8,10.0),(21,10.15),(34,10.3)):hole(o,(x,0,2),d/2,10)
coupon=finish(o,'TEST_01_Servo_and_623_fit',None,GREY)
coupon.hide_render=True;coupon.hide_set(True)

# Analyze/export all print bodies before posing: mesh dimensions are millimetres.
rows=[]
for o in list(PRINT.objects):
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=0.0001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=0.0001)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
    bm.to_mesh(o.data)
    nonmanifold=sum(not e.is_manifold for e in bm.edges)
    volume=abs(bm.calc_volume(signed=True)); bm.free()
    verts=[v.co for v in o.data.vertices]
    mn=Vector([min(v[i] for v in verts) for i in range(3)])
    mx=Vector([max(v[i] for v in verts) for i in range(3)])
    # STL individually oriented to broad structural plane, on z=0, positive XY.
    plane=o['print_plane'];r=Matrix.Rotation(math.pi/2,4,'X') if plane=='XZ' else Matrix.Rotation(math.pi/2,4,'Y') if plane=='YZ' else Matrix.Identity(4)
    vs=[r@v for v in verts];lo=Vector([min(v[i] for v in vs) for i in range(3)])
    exp=bpy.data.objects.new('export',o.data.copy());sc.collection.objects.link(exp)
    exp.data.transform(Matrix.Translation(-lo)@r)
    active(exp);bpy.ops.wm.stl_export(filepath=str(OUT/'stl'/(o.name+'.stl')),export_selected_objects=True,ascii_format=False,apply_modifiers=True)
    bpy.data.objects.remove(exp,do_unlink=True)
    row={'part':o.name,'volume_mm3':round(volume,2),'solid_PLA_mass_g':round(volume*0.00124,3),'nonmanifold_edges':nonmanifold,'size_mm':[round(x,2) for x in mx-mn],'print_plane':plane}
    o['solid_mass_g']=row['solid_PLA_mass_g'];rows.append(row)

# Conservative horizontal static load with fully solid PLA, measured servo mass,
# fastener/cable allowances at distal joints. Pose dependence is also evaluated.
def desc(o,j):
    p=o.parent
    while p:
        if p==j:return True
        p=p.parent
    return False
bpy.context.view_layer.update()
torques={}
for j,ratio in ((UP,3),(FORE,1),(WRIST,1)):
    xj=j.matrix_world.translation.x;moment=0
    for o in list(PRINT.objects)+list(REF.objects):
        if desc(o,j):
            mass=o.get('solid_mass_g',o.get('mass_g',0))
            center=sum((o.matrix_world@v.co for v in o.data.vertices),Vector())/len(o.data.vertices)
            # Bound along x using object bbox centre; exact volume centroid added in verification.
            xs=[(o.matrix_world@Vector(c)).x for c in o.bound_box]
            cx=(min(xs)+max(xs))/2
            moment+=mass*max(0,cx-xj)/10000
    tipx=247 # 80+70+97 mm from shoulder
    payload_arm=tipx-(xj-130*0) # corrected to joint absolute x, yaw origin x=0
    # Allow 4 g hardware at elbow, 3 g at wrist, 2 g wiring at gripper.
    for x,mass in ((80,4),(150,3),(185,2)):
        if x>=xj:moment+=mass*(x-xj)/10000
    lever=(247-xj)/10000
    budget=1.8*ratio*(0.8 if ratio>1 else 0.9)/2
    torques[j.name]={'dead_load_kgf_cm':round(moment,4),'budget_half_stall_kgf_cm':round(budget,4),'payload_limit_g':round(max(0,(budget-moment)/lever),1),'with_10g_kgf_cm':round(moment+10*lever,4)}

report={'servo_source':str(source),'units':'mm','arm_lengths_mm':[80,70],'gear':{'module':1,'teeth':[20,60],'pressure_angle':20,'center_distance':40,'face_width':5,'tooth_backlash_each_mm':0.18},'parts':rows,'static_horizontal':torques,'notes':['mass estimate uses solid PLA at 1.24 g/cm3, not infill percentage','hardware is referenced, not exported','hole and horn templates need fit test','no certified FEA or rated continuous torque available']}
(OUT/'analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

# Assembly pose and editable joint empties. Geometry remains separable.
UP.rotation_euler[1]=-math.radians(60)
FORE.rotation_euler[1]=math.radians(95)
WRIST.rotation_euler[1]=-math.radians(35)
JAW.rotation_euler[2]=math.radians(-8)
bpy.context.view_layer.update()

# Studio and annotated collection names; no generated image substitution.
floor=box((15,0,-4),(600,600,3),2);finish(floor,'Studio_floor',None,mat('Ground',(0.16,0.20,0.24)),hardware=True)
collect(floor,STUDIO)
def aim(o,p):o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(355,-455,305));cam=bpy.context.object;collect(cam,STUDIO)
aim(cam,(40,0,108));cam.data.type='ORTHO';cam.data.ortho_scale=365;cam.data.clip_end=3000;sc.camera=cam
for pos,power,size in [((80,-170,400),1800000,220),((-170,-30,270),1100000,180),((160,180,320),2200000,170)]:
    bpy.ops.object.light_add(type='AREA',location=pos);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;aim(o,(30,0,95));collect(o,STUDIO)
sc.render.resolution_x=1500;sc.render.resolution_y=1300;sc.render.resolution_percentage=100
sc.view_settings.view_transform='AgX'
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.clip_end=3000
        area.spaces.active.region_3d.view_distance=360
        area.spaces.active.region_3d.view_location=(40,0,100)
        area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
active(UP)
sc.render.filepath=str(OUT/'assembly.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'CyberArm_B2.blend'))
print('BUILD_COMPLETE',len(rows),'print parts. Nonmanifold:',[(r['part'],r['nonmanifold_edges']) for r in rows if r['nonmanifold_edges']])
print('TORQUE',json.dumps(torques))
