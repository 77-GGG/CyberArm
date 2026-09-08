import bpy
from pathlib import Path

scene=bpy.context.scene
output=Path('E:/CyberArm/mechanical/archive/arduino_reference_replica')
scene.cycles.samples=32
for camera_name,filename in [('ARD_Camera_Front','Arduino_Original_Replica.png'),('ARD_Camera_Servo_side','Arduino_Servo_side.png')]:
    scene.camera=bpy.data.objects[camera_name]
    scene.render.filepath=str(output/filename)
    bpy.ops.render.render(write_still=True)
