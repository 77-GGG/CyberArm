"""Local Fusion reconstruction helpers: analytic prismatic recognition and features.

Uses native Fusion feature APIs; source STL files are never overwritten.
The recognition feature remains in the timeline. It is not a recovered original
sketch history. New interface edits are ordinary native modeling features.
"""
import adsk.core as ac
import adsk.fusion as af
from pathlib import Path
import json,math

APP=ac.Application.get()
DESIGN=af.Design.cast(APP.activeProduct)
ROOT=DESIGN.rootComponent
OUT=Path('E:/CyberArm/mechanical/fusion_reference_review')


def comp(name):
    return next(o.component for o in ROOT.occurrences if o.component.name==name)


def rebuild(name):
    c=comp(name)
    if c.bRepBodies.count:
        return inspect(name)
    mesh=c.meshBodies.item(0)
    before={'mesh_triangles':mesh.displayMesh.triangleCount}
    gf=c.features.meshGenerateFaceGroupsFeatures
    gi=gf.createInput(mesh)
    gi.meshGenerateFaceGroupsMethodType=af.MeshGenerateFaceGroupsMethodTypes.AccurateGenerateFaceGroupsType
    gi.boundaryTolerance=0.0005
    g=gf.add(gi)
    g.name='Recognize_planes_cylinders_'+name
    ci=c.features.meshConvertFeatures.createInput([mesh])
    ci.meshConvertMethodType=af.MeshConvertMethodTypes.PrismaticMeshConvertMethodType
    ci.meshConvertOperationType=af.MeshConvertOperationTypes.ParametricFeatureMeshConvertOperationType
    cf=c.features.meshConvertFeatures.add(ci)
    cf.name='Native_analytic_solid_'+name
    for b in c.bRepBodies:b.name=name+'_Native'
    c.attributes.add('CyberArm','native_method','Fusion prismatic recognition, analytic surfaces; not faceted conversion')
    r=inspect(name);r.update(before)
    save_record(r)
    return r


def inspect(name):
    c=comp(name);bodies=[]
    for b in c.bRepBodies:
        types={}
        for f in b.faces:
            t=f.geometry.objectType.split('::')[-1]
            types[t]=types.get(t,0)+1
        bb=b.boundingBox
        bodies.append({'name':b.name,'solid':b.isSolid,'faces':b.faces.count,'surface_types':types,'volume_mm3':b.volume*1000,
                       'bounds_mm':[[v*10 for v in bb.minPoint.asArray()],[v*10 for v in bb.maxPoint.asArray()]]})
    return {'component':name,'bodies':bodies}


def save_record(r):
    p=OUT/'native_rebuild_report.json'
    data=json.loads(p.read_text(encoding='utf8')) if p.exists() else {}
    data[r['component']]=r
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')


def face_info(name):
    b=comp(name).bRepBodies.item(0)
    out=[]
    for i,f in enumerate(b.faces):
        g=f.geometry;p=f.pointOnFace
        rec={'index':i,'type':g.objectType.split('::')[-1],'area_mm2':f.area*100,'point_mm':[v*10 for v in p.asArray()]}
        if hasattr(g,'normal'):rec['normal']=g.normal.asArray()
        if hasattr(g,'radius'):rec['radius_mm']=g.radius*10
        bb=f.boundingBox;rec['bounds_mm']=[[v*10 for v in bb.minPoint.asArray()],[v*10 for v in bb.maxPoint.asArray()]]
        out.append(rec)
    (OUT/(name+'_native_faces.json')).write_text(json.dumps(out,indent=2),encoding='utf8')
    return out
