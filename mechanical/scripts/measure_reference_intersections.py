import bpy,bmesh,json
from pathlib import Path

output=Path('E:/CyberArm/mechanical/archive/arduino_reference_replica')
pairs=json.loads((output/'static_check.json').read_text())['intersections_to_review']
results=[]
for pair in pairs:
    first=bpy.data.objects[pair['first']]
    second=bpy.data.objects[pair['second']]
    temp=bpy.data.objects.new('ARD_CHECK_TEMP',first.data.copy())
    bpy.context.scene.collection.objects.link(temp)
    temp.matrix_world=first.matrix_world
    modifier=temp.modifiers.new('Intersection','BOOLEAN')
    modifier.operation='INTERSECT';modifier.solver='EXACT';modifier.object=second
    depsgraph=bpy.context.evaluated_depsgraph_get()
    evaluated=temp.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    bm=bmesh.new();bm.from_mesh(mesh);bm.transform(temp.matrix_world)
    volume=abs(bm.calc_volume(signed=True))
    vertices=[v.co for v in bm.verts]
    bounds=[[min(v[i] for v in vertices) for i in range(3)],[max(v[i] for v in vertices) for i in range(3)]] if vertices else None
    result=dict(pair,volume_mm3=volume,non_manifold=sum(not e.is_manifold for e in bm.edges),bounds=bounds)
    print(json.dumps(result),flush=True);results.append(result)
    bm.free();evaluated.to_mesh_clear();bpy.data.objects.remove(temp,do_unlink=True)
    (output/'intersection_volumes.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
