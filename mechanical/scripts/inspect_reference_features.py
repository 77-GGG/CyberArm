"""Read native STL features for a faithful assembly; no source mesh modifications."""
import bpy,bmesh,json,math,numpy as np
from pathlib import Path
from collections import Counter
root=Path('E:/下载/大白爱模型_机械臂资料/arduino机械臂/files')
out=Path('E:/CyberArm/mechanical/archive/arduino_reference_replica');out.mkdir(exist_ok=True)
previous=bpy.context.window.scene;sc=bpy.data.scenes.new('Arduino_Reference_Feature_Inspection');bpy.context.window.scene=sc
records=[]
for path in sorted(root.glob('*.stl')):
    if '(1)' in path.name:continue
    bpy.ops.wm.stl_import(filepath=str(path));o=bpy.context.object;o.name='REF_SCAN_'+path.stem
    bm=bmesh.new();bm.from_mesh(o.data);rec={'part':path.stem,'bounds':[[f(v.co[k] for v in bm.verts) for k in range(3)] for f in (min,max)],'features':[]}
    for axis in range(3):
        other=[k for k in range(3) if k!=axis]
        levels=[v for v,n in Counter(round(v.co[axis],3) for v in bm.verts).most_common(14)]
        for level in levels:
            edges=[e for e in bm.edges if all(abs(v.co[axis]-level)<.002 for v in e.verts) and any(abs(f.normal[axis])>.999 for f in e.link_faces) and any(abs(f.normal[axis])<.95 for f in e.link_faces)]
            pending=set(edges)
            while pending:
                todo=[pending.pop()];vs=set()
                while todo:
                    e=todo.pop();vs.update(e.verts)
                    for v in e.verts:
                        for ee in v.link_edges:
                            if ee in pending:pending.remove(ee);todo.append(ee)
                if len(vs)<7:continue
                a=np.array([[v.co[k] for k in other] for v in vs]);xy=np.column_stack([2*a,np.ones(len(a))]);rhs=np.sum(a*a,axis=1)
                c=np.linalg.lstsq(xy,rhs,rcond=None)[0];rads=np.sqrt(np.sum((a-c[:2])**2,axis=1));r=float(np.mean(rads));err=float(max(rads)-min(rads))
                center=[0.,0.,0.];center[axis]=level
                for k,v in zip(other,c[:2]):center[k]=float(v)
                rec['features'].append({'axis':'XYZ'[axis],'plane':level,'points':len(vs),'center':center,'radius_fit':r,'radial_error':err,'bbox':[[round(f(v.co[k] for v in vs),4) for k in range(3)] for f in (min,max)]})
    bm.free();records.append(rec)
(out/'source_features.json').write_text(json.dumps(records,indent=2))
bpy.context.window.scene=previous
print(json.dumps([{'part':r['part'],'circular_features':[f for f in r['features'] if f['radial_error']<.05]} for r in records],indent=2))
