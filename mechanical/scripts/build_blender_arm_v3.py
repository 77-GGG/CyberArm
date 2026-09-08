"""B3 refinement: user-supplied horns, enclosed waist, ribbed arms.
Reuses B2's measured servo/support geometry without modifying the B2 source or file.
Run via blender_mcp_client.py. Millimetres; purchased horns are NEVER print exports.
"""
import bpy,math,json,bmesh
from pathlib import Path
from mathutils import Vector,Matrix
root=Path('E:/CyberArm/mechanical');out3=root/'archive/blender_arm_v3';out3.mkdir(exist_ok=True)
if not (out3/'pre_B3_session_snapshot.blend').exists():
    bpy.ops.wm.save_as_mainfile(filepath=str(out3/'pre_B3_session_snapshot.blend'))
# Keep the previous scene in the session, while freeing predictable new object names.
for scene in bpy.data.scenes:
    if scene.name.startswith('CyberArm_B2_Engineering'):
        for ob in scene.objects:
            if not ob.name.startswith('B2_ARCHIVE_'):ob.name='B2_ARCHIVE_'+ob.name
source=(root/'scripts/build_blender_arm.py').read_text(encoding='utf-8')
source=source.replace("blender_arm_v2","blender_arm_v3").replace('CyberArm_B2','CyberArm_B3')
source=source.replace("(0.85,0.17,0.027)","(0.90,0.135,0.025)")
source=source.replace("(0.075,0.10,0.135)","(0.20,0.245,0.29)")
source=source.replace("o=box((0,0,2),(140,120,4),6)","o=cyl((0,0,2),68,4)")
source=source.replace("o=cyl((0,0,64.5),34,4)","o=cyl((0,0,64.5),44,4)")
source=source.replace("add(o,cyl((0,0,38.5),12,3))","add(o,cyl((0,0,39.5),12,2))")
source=source.replace("[('lower',40.25,0.5),('upper',61.95,0.9)]","[('upper',61.95,0.9)]")
source=source.replace('-17.8','-18.3')
source=source.replace("(0,-18.3,0)),'P10_Shoulder_wheel_60T'","(0,-18.6,0)),'P10_Shoulder_wheel_60T'")
source=source.replace("('left',-13.65,3.3)","('left',-14.05,4.1)")
source=source.replace("o=cyl((x,-21.95,z),2.8,3.3,'Y');hole(o,(x,-21.95,z),1.65,8,'Y')","o=cyl((x,-22.35,z),2.8,2.5,'Y');hole(o,(x,-22.35,z),1.65,8,'Y')")
# All actual horn attachments use measured inner holes at radius 6, not guessed 7.
source=source.replace('for x in (-7,7):','for x in (-6,6):')
# Pinion single horn only has positive-side holes; retain full involute gear.
source=source.replace("for x in (-6,6):hole(o,(x,0,0),1.05,12)","for x in (6,8.5):hole(o,(x,0,0),0.9,12)")
source=source.replace("o=cyl((0,-19.45,0),9,8.0,'Y')","o=cyl((0,-19.5,0),9,8.0,'Y')")
head,tail=source.split('# Analyze/export all print bodies before posing:',1)
exec(compile(head,'B3_base_geometry','exec'),globals())
for ob in PRINT.objects:
    bm=bmesh.new();bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.0001)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    bm.to_mesh(ob.data);bm.free()

def get(n):return bpy.data.objects[n]
def erase(n):
    ob=bpy.data.objects.get(n)
    if ob:bpy.data.objects.remove(ob,do_unlink=True)
def measured_hole(o,c,r=.9,h=16,axis='Y'):hole(o,c,r,h,axis)

# Original nylon horns: source hub points +Z INTO the servo. Flip rigidly about X.
horn_specs=[('single','obj_1_ServoMotor Arms.stl_B.stl',111.455343,138.914075),('double','obj_2_ServoMotor Arms.stl_A_A.stl',125.348794,129.224590),('cross','obj_3_ServoMotor Arms.stl_A_B.stl',125.233263,114.057127)]
horn_meshes={}
for kind,filename,cx,cy in horn_specs:
    bpy.ops.wm.stl_import(filepath=str(root/'servo配件'/filename));ob=bpy.context.object
    for v in ob.data.vertices:v.co=(v.co.x-cx,cy-v.co.y,2.5-v.co.z)
    horn_meshes[kind]=ob.data.copy();bpy.data.objects.remove(ob,do_unlink=True)
for ob in list(REF.objects):
    if ob.name.startswith('HW_Horn_TEMPLATE'):bpy.data.objects.remove(ob,do_unlink=True)
def horn(kind,name,parent,at,pitched=True,angle=0):
    ob=bpy.data.objects.new('HW_Horn_'+kind+'_'+name,horn_meshes[kind].copy());REF.objects.link(ob)
    ob.parent=parent;ob.matrix_basis=Matrix.Translation(Vector(at))@(pitch if pitched else Matrix.Identity(4))@Matrix.Rotation(math.radians(angle),4,'Z')
    ob.data.materials.clear();ob.data.materials.append(WHITE)
    ob['purpose']='purchased_reference';ob['mass_g']={'single':.5,'double':.8,'cross':1.0}[kind]
    ob['source']='servo配件/'+next(s[1] for s in horn_specs if s[0]==kind)
    ob['seat_note']='Model arm underside at servo shaft tip; physical spline seating depth must be measured.'
    return ob
horn('cross','Yaw',BASE,(0,0,36),False)
horn('single','Shoulder',drive,(0,5.3,0),True,9)
horn('double','Elbow',FORE,(0,-13,0))
horn('double','Wrist',WRIST,(0,-13,0))
horn('single','Gripper',JAW,(0,0,0),False,math.degrees(math.atan2(14,35)))

# Add horn-contact faces and use actual 1.8 mm holes (M1.6 clearance).
o=get('P04_Yaw_spindle')
for x,y in [(6,0),(-6,0),(0,5.1),(0,-5.1)]:hole(o,(x,y,39.5),.9,6)
o=get('P13_Forearm_rail_-18')
add(o,cyl((0,-16.1,0),11,1.2,'Y'));hole(o,(0,-16.05,0),3.6,10,'Y')
for x in (-6,6):hole(o,(x,-18,0),.9,12,'Y')
# Gripper lever's mating plane is now the measured horn top, z=2.5.
o=get('P18_Moving_finger')
for v in o.data.vertices:v.co.z+=.3
for radius in (6,11):
    a=math.atan2(14,35);hole(o,(radius*math.cos(a),radius*math.sin(a),4),.9,12)
# Narrow single-horn rear pocket in pinion, meeting the horn face at y=-15.5.
o=get('P09_Shoulder_pinion_20T')
collar=cyl((0,0,0),10,.4)
for x in (6,8.5):hole(collar,(x,0,0),.9,8)
hole(collar,(0,0,0),3.6,8)
collar.data.transform(Matrix.Rotation(math.radians(9),4,'Z'))
into_pitch(collar,(0,2.6,0));add(o,collar)

# Smooth structural side webs and raised longitudinal edges; all fused to rails.
for L,parent,names,ys in [(80,UP,['P11_Upper_rail_-25','P11_Upper_rail_27'],[-25,27]),(70,FORE,['P13_Forearm_rail_-18','P13_Forearm_rail_22'],[-18,22])]:
    for name,y in zip(names,ys):
        o=get(name)
        add(o,box((L/2,y,0),(L-32,1.0,7),.45))
        # Trough lips along the two long edges increase section stiffness.
        for z in (-7,7):add(o,box((L/2,y+(1.4 if y<0 else -1.4),z),(L-30,4.6,1.6),.6))
        # Shallow exterior styling recess (not a through-hole).
        exterior=y+(-1.3 if y<0 else 1.3)
        boolean(o,box((L/2,exterior,0),(L-42,.45,2.4),.2))

# Main cylindrical waist shell with an open service top and cable vents.
base=get('P01_Base_plate')
for deg in (0,120,240):
    a=math.radians(deg);x,y=76*math.cos(a),76*math.sin(a)
    add(base,cyl((x,y,2),9,4));add(base,box((x*.85,y*.85,2),(23,23,4),4))
    hole(base,(x,y,2),2.25,12)
o=cyl((0,0,32.9),44,57.8);hole(o,(0,0,32.9),42.4,70)
for deg in (0,120,240):
    a=math.radians(deg);x,y=39.2*math.cos(a),39.2*math.sin(a)
    add(o,cyl((x,y,5.6),4.2,3.2));hole(o,(x,y,5.6),1.2,12);hole(base,(x,y,2),1.0,10)
for y in (-10,0,10):boolean(o,box((-43,y,27),(9,3,18),1))
finish(o,'P30_Round_waist_shell',None,GREY)

# Fixed front gearbox cover: removable, no material inside the rotating gear pair.
o=cyl((0,-34,130),34,1.6,'Y');add(o,cyl((0,-34,90),14,1.6,'Y'))
add(o,box((0,-34,96),(30,1.6,12),1))
for z,ro,ri in [(130,34,32.0),(90,14,12.2)]:
    rim=cyl((0,-27.7,z),ro,11.2,'Y');hole(rim,(0,-27.7,z),ri,15,'Y')
    if z==130:boolean(rim,box((15,-27.65,164),(42,20,68)))
    else:boolean(rim,box((0,-27.65,106),(25,20,12)))
    add(o,rim)
for x in (-23.2,23.2):
    add(o,box((x/2,-34,90),(abs(x)+8,1.6,10),1))
    add(o,cyl((x,-22.6,90),2.6,21.2,'Y'));hole(o,(x,-22,90),1.65,40,'Y')
    hole(get('P06_Shoulder_cheek_-10'),(x,-10,90),1.65,15,'Y')
hole(o,(0,-34,130),3.8,10,'Y');hole(o,(0,-34,90),3.2,10,'Y')
# Concentric shallow groove makes the joint face legible, without an extra loose cover.
groove=cyl((0,-34.7,130),28,.5,'Y');hole(groove,(0,-34.7,130),27,2,'Y');boolean(o,groove)
finish(o,'P31_Removable_round_gearcase',BASE,ORANGE,'XZ')

# Rounded distal joint faces, attached to the fixed side by two service screws.
for parent,L,y,rail_name,tag in [(UP,80,-25,'P11_Upper_rail_-25','Elbow'),(WRIST,0,-25,'P14_Wrist_fork_-25','Wrist')]:
    rad=19 if tag=='Elbow' else 14
    o=cyl((L,-29,0),rad,1.2,'Y')
    for x in (-6,6):
        add(o,cyl((L+x,-27.45,0),2,2.1,'Y'));hole(o,(L+x,-28,0),.9,12,'Y')
        hole(get(rail_name),(L+x,y,0),.9,12,'Y')
    hole(o,(L,-29,0),3,10,'Y')
    finish(o,'P32_'+tag+'_round_service_cap',parent,ORANGE,'XZ')

# Servo shells form shallow U covers with mount flanges; measured cable exit remains open.
for parent,L,tag in [(UP,80,'Elbow'),(FORE,70,'Wrist')]:
    # Body: canonical local x[-16.4,6], z[-32.1,-9.5], transform to joint coordinates.
    shell=box((-5.2,0,-24.85),(26,15.6,16.7),1.2)
    boolean(shell,box((-5.2,0,-24.85),(23.6,13.2,19),.6))
    boolean(shell,box((10,0,-27),(14,8,12),1))
    # Open bottom end and keep tabs by the frame on the fixed component.
    for x in (-17.1,6.7):
        add(shell,box((x,0,-17.5),(3,19,2),.5))
        for y in (-8,8):hole(shell,(x,y,-17.5),.9,10)
    into_pitch(shell,(L,-13,0))
    frame=get('P_'+tag+'_motor_frame')
    for x in (-17.1,6.7):
        for z in (-8,8):hole(frame,(L+x,1.95,z),.75,8,'Y')
    finish(shell,'P33_'+tag+'_servo_U_shell',parent,ORANGE,'XZ')

# Keep fixed camera/electronics modules available, but outside the core aesthetic view.
optional=bpy.data.collections.new('05_OPTIONAL_FIXED_VISION_AND_ELECTRONICS');sc.collection.children.link(optional)
for name in ['P19_Electronics_strap_deck','P20_K230D_fixed_strap_mast','HW_K230D_BOX_envelope']:
    ob=get(name);collect(ob,optional);ob.hide_render=True;ob.hide_set(True);ob['optional']=True

# Replace the old fit coupon with a measured three-pattern horn interface gauge.
o=box((0,0,2),(80,55,4),1)
for center in [(-20,11),(20,11),(0,-14)]:hole(o,(*center,2),3.6,10)
for x in (6,8.5,11,13.5,16):hole(o,(-20+x,11,2),.9,10)
for sign in (-1,1):
    for x in (6,8.5,11,13.5,16):hole(o,(20+sign*x,11,2),.9,10)
    for x in (6,8.5,11,13.5,16):hole(o,(sign*x,-14,2),.9,10)
    for y in (5.1,7.7):hole(o,(0,-14+sign*y,2),.9,10)
fit=finish(o,'TEST_02_Actual_horn_patterns',None,GREY);fit.hide_render=True;fit.hide_set(True)

# Reviewable provenance & horn-to-joint mapping.
sc['revision']='B3: reference-inspired structural refinement, actual horn CAD, prototype only'
sc['reference_folder']='E:/下载/大白爱模型_机械臂资料/arduino机械臂'
sc['horn_mapping']='cross: yaw; single: shoulder and gripper; double: elbow and wrist'
exec(compile('# Analyze/export all print bodies before posing:'+tail,'B3_export_and_pose','exec'),globals())
print('B3_REFINEMENT_COMPLETE')
