import bpy,bmesh,json,math
from pathlib import Path
p=Path('E:/CyberArm/mechanical/archive/blender_arm_v2')
d=json.loads((p/'final_checks.json').read_text())
js=[bpy.data.objects[n] for n in ['J0_YAW','J1_SHOULDER_3_to_1','J2_ELBOW','J3_WRIST','J4_GRIPPER']]
saved=[o.rotation_euler.copy() for o in js]
cases={}
for row in d['sampled_poses']:
    for pair in row['crossing_candidates']:cases.setdefault(tuple(pair),row['angles_deg'])
for row in d['gripper_samples']:
    for pair in row['crossing_candidates']:cases[tuple(pair)+(str(row['jaw_deg']),)]={'jaw':row['jaw_deg']}
result=[]
for key,pose in cases.items():
    for o,r in zip(js,saved):o.rotation_euler=r
    if 'yaw' in pose:
        for o,axis,deg in [(js[0],2,pose['yaw']),(js[1],1,-pose['shoulder_elevation']),(js[2],1,-pose['elbow_relative']),(js[3],1,pose['wrist_euler_y'])]:o.rotation_euler[axis]=math.radians(deg)
    js[4].rotation_euler[2]=math.radians(pose['jaw'])
    bpy.context.view_layer.update()
    a,b=[bpy.data.objects[n] for n in key[:2]];copies=[]
    for o in (a,b):
        c=bpy.data.objects.new('motion_boolean_probe',o.data.copy());bpy.context.scene.collection.objects.link(c)
        # Work in A's coordinates to reduce floating-point noise.
        c.data.transform(a.matrix_world.inverted()@o.matrix_world);copies.append(c)
    c,other=copies
    bpy.ops.object.select_all(action='DESELECT');c.select_set(True);bpy.context.view_layer.objects.active=c
    m=c.modifiers.new('Intersection','BOOLEAN');m.operation='INTERSECT';m.solver='EXACT';m.object=other
    bpy.ops.object.modifier_apply(modifier=m.name)
    bm=bmesh.new();bm.from_mesh(c.data);vol=abs(bm.calc_volume());bm.free()
    result.append({'pair':key[:2],'pose':pose,'volume_mm3':vol,'rigid_same_parent':a.parent==b.parent})
    for c in copies:bpy.data.objects.remove(c,do_unlink=True)
for o,r in zip(js,saved):o.rotation_euler=r
bpy.context.view_layer.update()
(p/'motion_interference_volumes.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
