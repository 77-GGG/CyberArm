import bpy, json, math
from pathlib import Path
from mathutils import Vector,Matrix

output=Path('E:/CyberArm/mechanical/archive/arduino_reference_replica')
scene=bpy.context.scene
printed=next(c for c in scene.collection.children if c.name.startswith('ARD_01_'))
motors=next(c for c in scene.collection.children if c.name.startswith('ARD_02_'))
hardware=next(c for c in scene.collection.children if c.name.startswith('ARD_03_'))
studio=next(c for c in scene.collection.children if c.name.startswith('ARD_04_'))
controls=bpy.data.collections.new('ARD_05_Joint_controls');scene.collection.children.link(controls)
report=json.loads((output/'assembly_manifest.json').read_text(encoding='utf-8'))

def point_camera(camera,position,target):
    camera.location=position
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()

def preserve_parent(obj,parent):
    bpy.context.view_layer.update()
    transform=obj.matrix_world.copy()
    obj.parent=parent
    obj.matrix_parent_inverse=parent.matrix_world.inverted()
    obj.matrix_world=transform
    bpy.context.view_layer.update()

def joint(name,index,parent=None):
    obj=bpy.data.objects.new(name,None);controls.objects.link(obj)
    source=report['servos'][index]
    axis=Vector(source['shaft_direction'])
    obj.rotation_mode='XYZ'
    obj.rotation_euler=axis.to_track_quat('Z','Y').to_euler()
    obj.location=source['shaft_origin']
    obj.empty_display_type='CIRCLE';obj.empty_display_size=24 if index<3 else 13
    obj.show_in_front=True
    obj['Usage']='Rotate LOCAL Z; downstream assembly follows. No validated motion limits.'
    if parent:preserve_parent(obj,parent)
    return obj

yaw=joint('J01_Base_yaw',0)
shoulder=joint('J02_Shoulder_pitch',1,yaw)
elbow=joint('J03_Elbow_pitch',2,shoulder)
roll=joint('J04_Wrist_roll',3,elbow)
pitch=joint('J05_Wrist_pitch',4,roll)

for obj in list(printed.objects):
    if obj.name.startswith('ARD_03_'):preserve_parent(obj,yaw)
    elif obj.name.startswith('ARD_04_'):preserve_parent(obj,shoulder)
    elif obj.name.startswith('ARD_05_'):preserve_parent(obj,elbow)
    elif obj.name.startswith('ARD_06_'):preserve_parent(obj,roll)
    elif any(obj.name.startswith('ARD_'+prefix) for prefix in ('07_','08_','09_','10_')):preserve_parent(obj,pitch)

for obj in list(motors.objects)+list(hardware.objects):
    name=obj.name
    parent=None
    if name.startswith('ARD_S02_'):parent=yaw if 'Shoulder' in name else shoulder
    elif name.startswith('ARD_S03_'):parent=elbow if 'Elbow' in name else shoulder
    elif name.startswith('ARD_S04_'):parent=elbow if 'Wrist_roll' in name else roll
    elif name.startswith('ARD_S05_'):parent=roll if 'Wrist_pitch' in name else pitch
    elif name.startswith('ARD_S06_'):parent=pitch
    elif name.startswith('ARD_S01_') and 'Base' not in name:parent=yaw
    elif name.startswith(('ARD_Left_','ARD_Right_')):parent=pitch
    if parent:preserve_parent(obj,parent)

for obj in printed.objects:
    mat=obj.data.materials[0]
    shader=next(n for n in mat.node_tree.nodes if n.bl_idname=='ShaderNodeBsdfPrincipled')
    color=(.86,.105,.006,1) if 'Orange' in mat.name else (.27,.32,.38,1)
    shader.inputs['Base Color'].default_value=color;mat.diffuse_color=color
scene.view_settings.exposure=-1.0
rear=scene.camera
rear.name='ARD_Camera_Servo_side'
front_data=rear.data.copy();front=bpy.data.objects.new('ARD_Camera_Front',front_data);studio.objects.link(front)
point_camera(front,(-320,620,350),(76,0,91));front.data.ortho_scale=425
scene.camera=front
scene.render.filepath=str(output/'Arduino_Original_Replica.png')
scene['Joint_controls']='J01 through J05: LOCAL Z rotation. Gripper links retain the checked fixed opening.'
bpy.context.view_layer.update()
errors=[]
for part in report['parts']:
    obj=bpy.data.objects[part['object']]
    expected=Matrix(part['matrix_world'])
    maximum=max(abs(obj.matrix_world[row][col]-expected[row][col]) for row in range(4) for col in range(4))
    errors.append(maximum)
    if maximum>.001:raise RuntimeError('Parent transform changed: '+obj.name)
report['joint_controls']=['J01_Base_yaw','J02_Shoulder_pitch','J03_Elbow_pitch','J04_Wrist_roll','J05_Wrist_pitch']
report['parenting_transform_max_error_mm']=max(errors)
report['geometry_check']='No detected nontrivial surface intersections in original parts and six servo bodies in saved pose; tiny source/contact residuals <0.04 mm3. Fastener clearances and full motion range not evaluated.'
(output/'assembly_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

for obj in scene.objects:obj.select_set(False)
bpy.context.view_layer.objects.active=bpy.data.objects['ARD_04_Arm_01']
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            space=area.spaces.active
            space.clip_end=10000;space.shading.type='SOLID';space.shading.color_type='MATERIAL'
            space.overlay.show_extras=False
            space.region_3d.view_perspective='ORTHO'
            space.region_3d.view_location=(76,0,91)
            space.region_3d.view_distance=460
            space.region_3d.view_rotation=front.rotation_euler.to_quaternion()

bpy.ops.wm.save_as_mainfile(filepath=str(output/'Arduino_Original_Replica.blend'))
print(json.dumps({'saved':str(output/'Arduino_Original_Replica.blend'),'parent_error':max(errors)}))
