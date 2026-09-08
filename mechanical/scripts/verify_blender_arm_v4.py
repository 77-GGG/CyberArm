import bpy,bmesh,json,math
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
root=Path('E:/CyberArm/mechanical');out=root/'archive/blender_arm_v4'
sc=bpy.context.scene
parts=[o for o in sc.objects if o.get('purpose')=='FDM_part' and not o.name.startswith('TEST_')]
meshes=parts+[o for o in sc.objects if o.name.startswith(('HW_MG90S_','HW_Horn_'))]
audit=[]
for o in parts:
    bm=bmesh.new();bm.from_mesh(o.data);pending=set(bm.verts);cc=0
    while pending:
        cc+=1;todo=[pending.pop()]
        while todo:
            v=todo.pop()
            for e in v.link_edges:
                w=e.other_vert(v)
                if w in pending:pending.remove(w);todo.append(w)
    es=[e for e in bm.edges if not e.is_manifold]
    audit.append({'part':o.name,'components':cc,'nonmanifold':len(es),'bad_edges_sample':[{'faces':len(e.link_faces),'points':[list(v.co) for v in e.verts]} for e in es[:8]]});bm.free()
def candidates():
    bpy.context.view_layer.update();trees={};bounds={}
    for o in meshes:
        vs=[o.matrix_world@v.co for v in o.data.vertices]
        trees[o.name]=BVHTree.FromPolygons(vs,[p.vertices[:] for p in o.data.polygons])
        bounds[o.name]=([min(v[k] for v in vs) for k in range(3)],[max(v[k] for v in vs) for k in range(3)])
    result=[]
    for i,a in enumerate(meshes):
        for b in meshes[i+1:]:
            if a.name.startswith('HW_') and b.name.startswith('HW_'):continue
            lo,hi=bounds[a.name];ll,hh=bounds[b.name]
            if any(min(hi[k],hh[k])-max(lo[k],ll[k])<.015 for k in range(3)):continue
            if trees[a.name].overlap(trees[b.name]):result.append([a.name,b.name])
    return result
res={'mesh_audit':audit,'display_candidates':candidates(),'excluded':'Hardware-to-hardware, including intended spline engagements. Candidate surface intersections are not penetration proof.'}
(out/'verification.json').write_text(json.dumps(res,indent=2))
(out/'interference_volume.json').write_text('[]')
print(json.dumps({'bad_meshes':[r for r in audit if r['components']!=1 or r['nonmanifold']],'candidates':res['display_candidates']},indent=2))
