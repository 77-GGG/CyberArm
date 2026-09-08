import bpy,bmesh,json
from pathlib import Path
from mathutils import Matrix,Vector
p=Path('E:/CyberArm/mechanical/archive/blender_arm_v2')
data=json.loads((p/'verification.json').read_text())
result=[]
for an,bn,_ in data['surface_intersection_candidates']['display_pose']:
    a,b=bpy.data.objects[an],bpy.data.objects[bn]
    copies=[]
    for o in (a,b):
        c=bpy.data.objects.new('interference_probe',o.data.copy());bpy.context.scene.collection.objects.link(c)
        c.data.transform(o.matrix_world);copies.append(c)
    c,d=copies
    bpy.ops.object.select_all(action='DESELECT');c.select_set(True);bpy.context.view_layer.objects.active=c
    mod=c.modifiers.new('Probe','BOOLEAN');mod.operation='INTERSECT';mod.solver='EXACT';mod.object=d
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bm=bmesh.new();bm.from_mesh(c.data);vol=abs(bm.calc_volume());bm.free()
        verts=[a.matrix_world.inverted()@v.co for v in c.data.vertices]
        bbox=[[round(f(v[k] for v in verts),3) for k in range(3)] for f in (min,max)] if verts else []
        result.append({'a':an,'b':bn,'volume_mm3':round(vol,4),'bbox_in_a_local_mm':bbox})
    except Exception as e:result.append({'a':an,'b':bn,'error':str(e)})
    for c in copies:bpy.data.objects.remove(c,do_unlink=True)
(p/'interference_volume.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
