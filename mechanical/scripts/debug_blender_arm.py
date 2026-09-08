import bpy,bmesh,json
from mathutils import Vector
for o in bpy.context.scene.objects:
    if o.name.startswith('P11_Upper_rail_-25'):
        bm=bmesh.new();bm.from_mesh(o.data)
        print('BAD_EDGES',[[list(v.co) for v in e.verts] for e in bm.edges if not e.is_manifold]);bm.free()
for n in ['P_Wrist_motor_frame','P16_Gripper_palm_servo_frame','HW_MG90S_3_Wrist','HW_MG90S_4_Gripper','P20_K230D_fixed_strap_mast']:
    o=bpy.data.objects[n];vs=[o.matrix_world@Vector(v) for v in o.bound_box]
    print(n, [[min(v[i] for v in vs) for i in range(3)],[max(v[i] for v in vs) for i in range(3)]])
