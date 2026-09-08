import bpy, json
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
parts=list(next(c for c in scene.collection.children if c.name.startswith('ARD_01_')).objects)
motors=[o for o in scene.objects if o.type=='MESH' and ('_BODY' in o.name or '_USER_MODEL' in o.name)]
objects=parts+motors
trees={}
boxes={}
for obj in objects:
    vertices=[obj.matrix_world@v.co for v in obj.data.vertices]
    trees[obj.name]=BVHTree.FromPolygons(vertices,[list(p.vertices) for p in obj.data.polygons])
    boxes[obj.name]=[[min(v[i] for v in vertices) for i in range(3)], [max(v[i] for v in vertices) for i in range(3)]]
intersections=[]
for index,first in enumerate(objects):
    for second in objects[index+1:]:
        if first in motors and second in motors:continue
        box1,box2=boxes[first.name],boxes[second.name]
        if any(box1[0][i]>box2[1][i] or box2[0][i]>box1[1][i] for i in range(3)):continue
        overlap=trees[first.name].overlap(trees[second.name])
        if overlap:intersections.append({'first':first.name,'second':second.name,'triangle_pairs':len(overlap)})
result={'intersections_to_review':intersections,'part_scales':{o.name:list(o.scale) for o in parts},'bounds':boxes}
Path('E:/CyberArm/mechanical/archive/arduino_reference_replica/static_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(intersections))
