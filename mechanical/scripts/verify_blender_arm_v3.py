import bpy,bmesh,json
from pathlib import Path
p=Path('E:/CyberArm/mechanical')
code=(p/'scripts/verify_blender_arm.py').read_text().replace('blender_arm_v2','blender_arm_v3')
code=code.replace("and not o.name.startswith('TEST_')","and not o.name.startswith('TEST_') and not o.get('optional')")
code=code.replace("meshes=parts+[o for o in sc.objects if o.name.startswith('HW_MG90S_')]","meshes=parts+[o for o in sc.objects if o.name.startswith(('HW_MG90S_','HW_Horn_'))]")
exec(compile(code,'B3_verify','exec'),globals())
bad=[]
for o in parts:
    bm=bmesh.new();bm.from_mesh(o.data)
    es=[e for e in bm.edges if not e.is_manifold]
    if es:
        bad.append({'name':o.name,'edges':[{'faces':len(e.link_faces),'points':[list(v.co) for v in e.verts]} for e in es[:20]]})
    bm.free()
(p/'archive/blender_arm_v3/nonmanifold_diagnostics.json').write_text(json.dumps(bad,indent=2))
