import bpy,bmesh,json,math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from pathlib import Path
out=Path('E:/CyberArm/mechanical/archive/blender_arm_v2')
sc=bpy.context.scene
parts=[o for o in sc.objects if o.get('purpose')=='FDM_part' and not o.name.startswith('TEST_')]
refs=[o for o in sc.objects if o.get('purpose')=='purchased_reference' and o.type=='MESH' and not o.name.startswith('Studio')]
meshes=parts+[o for o in sc.objects if o.name.startswith('HW_MG90S_')]
audits=[]
for o in parts:
    bm=bmesh.new();bm.from_mesh(o.data)
    pending=set(bm.verts);cc=[]
    while pending:
        todo=[pending.pop()];n=0
        while todo:
            v=todo.pop();n+=1
            for e in v.link_edges:
                w=e.other_vert(v)
                if w in pending:pending.remove(w);todo.append(w)
        cc.append(n)
    audits.append({'name':o.name,'components':len(cc),'component_vertices':cc,'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),'volume_mm3':abs(bm.calc_volume())})
    bm.free()

def overlap_report():
    bpy.context.view_layer.update()
    trees={};bounds={};overlaps=[]
    for o in meshes:
        verts=[o.matrix_world@v.co for v in o.data.vertices]
        trees[o.name]=BVHTree.FromPolygons(verts,[p.vertices[:] for p in o.data.polygons],all_triangles=False)
        bounds[o.name]=([min(v[i] for v in verts) for i in range(3)],[max(v[i] for v in verts) for i in range(3)])
    for i,a in enumerate(meshes):
        for b in meshes[i+1:]:
            aa,ab=bounds[a.name];ba,bb=bounds[b.name]
            if any(min(ab[k],bb[k])-max(aa[k],ba[k])<0.02 for k in range(3)):continue
            hits=trees[a.name].overlap(trees[b.name])
            if hits:overlaps.append([a.name,b.name,len(hits)])
    return overlaps

poses={}
u=bpy.data.objects['J1_SHOULDER_3_to_1'];f=bpy.data.objects['J2_ELBOW'];w=bpy.data.objects['J3_WRIST']
saved=[u.rotation_euler.copy(),f.rotation_euler.copy(),w.rotation_euler.copy()]
poses['display_pose']=overlap_report()
u.rotation_euler=(0,0,0);f.rotation_euler=(0,0,0);w.rotation_euler=(0,0,0)
poses['horizontal_reference']=overlap_report()
for o,r in zip([u,f,w],saved):o.rotation_euler=r
bpy.context.view_layer.update()
res={'mesh_audit':audits,'surface_intersection_candidates':poses,'note':'BVH reports surface crossings, not interference volume; contact faces can also be reported. Not a continuous collision certification.'}
(out/'verification.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))
