"""Reopen validation and actual Blender renders; no scene changes saved here."""
import bpy, json, math, struct, bmesh
from pathlib import Path
from mathutils import Vector
OUT=Path('E:/CyberArm/mechanical/archive/arduino_reference_revB')
sc=bpy.context.scene
ctrl=bpy.data.objects['ARM_CONTROLS']
checks=[]
for key in ['01_Base_deg','02_Shoulder_deg','03_Elbow_deg','04_Wrist_roll_deg','05_Wrist_pitch_deg','06_Gripper_deg']:
    jaw=bpy.data.objects['ARD_10_Jaw_Right'];before=jaw.matrix_world.translation.copy()
    ctrl[key]=5.;ctrl.update_tag();sc.frame_set(sc.frame_current);bpy.context.view_layer.update()
    after=jaw.matrix_world.translation.copy()
    checks.append({'control':key,'test_degrees':5,'jaw_origin_displacement_mm':(after-before).length})
    ctrl[key]=0.;ctrl.update_tag();sc.frame_set(sc.frame_current);bpy.context.view_layer.update()
invalid=[o.name for o in sc.objects if o.animation_data and any(not f.driver.is_valid for f in o.animation_data.drivers)]
result={'reopened_file':bpy.data.filepath,'invalid_driver_objects':invalid,'native_controls':checks}
if invalid or any(r['jaw_origin_displacement_mm']<.01 for r in checks):raise RuntimeError(str(result))
(OUT/'reopen_validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
sc.render.engine='CYCLES';sc.cycles.samples=24;sc.cycles.use_denoising=True
sc.render.resolution_x=1400;sc.render.resolution_y=1100;sc.render.resolution_percentage=100
for camera,file in [('ARD_Camera_Front','RevB_front.png'),('ARD_Camera_Servo_side','RevB_servo_side.png')]:
    sc.camera=bpy.data.objects[camera];sc.render.filepath=str(OUT/file)
    bpy.ops.render.render(write_still=True)
print('REVB_REOPEN_AND_RENDER_OK',json.dumps(result),flush=True)
