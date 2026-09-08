import bpy,bmesh,json,math
from pathlib import Path
from mathutils import Vector
out=Path('E:/CyberArm/mechanical/archive/blender_arm_v3');out.mkdir(exist_ok=True)
previous=bpy.context.window.scene
sc=bpy.data.scenes.new('B3_Source_Inspection');bpy.context.window.scene=sc
sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=.001
records=[];models=[]
horns=sorted(Path('E:/CyberArm/mechanical/servo配件').glob('*.stl'))
refs=sorted(Path('E:/下载/大白爱模型_机械臂资料/arduino机械臂/files').glob('*.stl'))
for path in horns+[p for p in refs if '(1)' not in p.name]:
    bpy.ops.wm.stl_import(filepath=str(path));o=bpy.context.object
    vs=[v.co.copy() for v in o.data.vertices]
    lo=[min(v[k] for v in vs) for k in range(3)];hi=[max(v[k] for v in vs) for k in range(3)]
    record={'file':str(path),'bounds':[lo,hi],'size':[hi[k]-lo[k] for k in range(3)],'vertices':len(vs)}
    if path in horns:
        from collections import Counter
        record['planes']=[Counter(round(v[k],3) for v in vs).most_common(10) for k in range(3)]
        # Planar face boundary loops expose all horn through-hole circles.
        bm=bmesh.new();bm.from_mesh(o.data)
        zlevels=sorted(set(round(v.co.z,3) for v in bm.verts))
        contours=[]
        for level in zlevels:
            es=[e for e in bm.edges if all(abs(v.co.z-level)<.002 for v in e.verts)]
            # Edges bounding horizontal versus nonhorizontal surfaces, not triangulation.
            es=[e for e in es if any(abs(f.normal.z)>.99 for f in e.link_faces) and any(abs(f.normal.z)<.8 for f in e.link_faces)]
            pending=set(es)
            while pending:
                todo=[pending.pop()];edges=[];verts=set()
                while todo:
                    e=todo.pop();edges.append(e);verts.update(e.verts)
                    for v in e.verts:
                        for ee in v.link_edges:
                            if ee in pending:pending.remove(ee);todo.append(ee)
                if len(verts)>5:
                    cx=sum(v.co.x for v in verts)/len(verts);cy=sum(v.co.y for v in verts)/len(verts)
                    radii=[math.hypot(v.co.x-cx,v.co.y-cy) for v in verts]
                    contours.append({'z':level,'center_xy':[cx,cy],'r_mean':sum(radii)/len(radii),'r_spread':max(radii)-min(radii),'vertices':len(verts)})
        record['contours']=contours;bm.free()
    records.append(record);models.append(o)
    shift=Vector((len(models)%4*140,len(models)//4*180,0))-Vector(lo)
    for v in o.data.vertices:v.co+=shift
    if path in horns:
        o.scale=(3,3,3);o.location=(-420+horns.index(path)*140,-100,0)
(out/'source_inventory.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'source_inspection.blend'))
bpy.context.window.scene=previous
print(json.dumps(records,indent=2))
