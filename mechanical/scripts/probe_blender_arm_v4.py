import bpy,bmesh,json
from pathlib import Path
p=Path('E:/CyberArm/mechanical/archive/blender_arm_v4')
data=json.loads((p/'verification.json').read_text());out=p/'interference_volume.json'
results=json.loads(out.read_text()) if out.exists() else []
done={tuple(r['pair']) for r in results}
todo=[pair for pair in data['display_candidates'] if tuple(pair) not in done][:4]
for pair in todo:
    a,b=[bpy.data.objects[n] for n in pair];copies=[]
    for o in (a,b):
        c=bpy.data.objects.new('B4_probe',o.data.copy());bpy.context.scene.collection.objects.link(c)
        c.data.transform(a.matrix_world.inverted()@o.matrix_world);copies.append(c)
    c,d=copies;bpy.ops.object.select_all(action='DESELECT');c.select_set(True);bpy.context.view_layer.objects.active=c
    m=c.modifiers.new('Volume check','BOOLEAN');m.solver='EXACT';m.operation='INTERSECT';m.object=d
    bpy.ops.object.modifier_apply(modifier=m.name)
    bm=bmesh.new();bm.from_mesh(c.data);v=abs(bm.calc_volume());bm.free()
    vs=[v.co for v in c.data.vertices]
    bb=[[round(f(v[k] for v in vs),3) for k in range(3)] for f in (min,max)] if vs else []
    r={'pair':pair,'volume_mm3':round(v,4),'bbox_a_local':bb,'same_parent':a.parent==b.parent};results.append(r)
    for c in copies:bpy.data.objects.remove(c,do_unlink=True)
    out.write_text(json.dumps(results,indent=2))
print(json.dumps({'completed':len(results),'total':len(data['display_candidates']),'new':results[-len(todo):] if todo else []},indent=2))
