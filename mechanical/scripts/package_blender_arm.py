"""Generate audited, millimetre 3MF geometry plates from exported binary STL.
No printer profile or toolpath is embedded; user must slice in Bambu Studio.
"""
import struct, json, csv, zipfile, collections
from pathlib import Path
import xml.etree.ElementTree as ET
root=Path('E:/CyberArm/mechanical/archive/blender_arm_v2')
dest=root/'plates_3mf';dest.mkdir(exist_ok=True)
ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('',ns)
def tag(s):return '{'+ns+'}'+s
models=[]
for file in sorted((root/'stl').glob('*.stl')):
    data=file.read_bytes();n=struct.unpack_from('<I',data,80)[0]
    assert len(data)==84+50*n,file.name
    verts=[];tris=[];index={};edges=collections.Counter();vol=0
    for k in range(n):
        row=struct.unpack_from('<12fH',data,84+50*k);tri=[]
        for j in range(3):
            v=tuple(round(x,5) for x in row[3+3*j:6+3*j])
            if v not in index:index[v]=len(verts);verts.append(v)
            tri.append(index[v])
        assert len(set(tri))==3,(file.name,'degenerate triangle')
        tris.append(tri)
        for a,b in zip(tri,tri[1:]+tri[:1]):edges[tuple(sorted([a,b]))]+=1
    assert all(v==2 for v in edges.values()),(file.name,'open/nonmanifold exported mesh')
    lo=[min(v[k] for v in verts) for k in range(3)];hi=[max(v[k] for v in verts) for k in range(3)]
    dims=[hi[k]-lo[k] for k in range(3)]
    assert max(dims)<=256 and min(lo)>=-.001,(file.name,dims,lo)
    models.append({'name':file.stem,'verts':verts,'tris':tris,'dimensions_mm':dims})

def make3mf(filename,placements):
    model=ET.Element(tag('model'),{'unit':'millimeter','xml:lang':'en-US'})
    meta=ET.SubElement(model,tag('metadata'),{'name':'Title'});meta.text='CyberArm B2 - fit-test prototype - geometry only'
    resources=ET.SubElement(model,tag('resources'));build=ET.SubElement(model,tag('build'))
    for oid,(p,x,y) in enumerate(placements,1):
        ob=ET.SubElement(resources,tag('object'),{'id':str(oid),'type':'model','name':p['name']})
        mesh=ET.SubElement(ob,tag('mesh'));vs=ET.SubElement(mesh,tag('vertices'));ts=ET.SubElement(mesh,tag('triangles'))
        for v in p['verts']:ET.SubElement(vs,tag('vertex'),dict(zip(['x','y','z'],map(str,v))))
        for t in p['tris']:ET.SubElement(ts,tag('triangle'),dict(zip(['v1','v2','v3'],map(str,t))))
        ET.SubElement(build,tag('item'),{'objectid':str(oid),'transform':f'1 0 0 0 1 0 0 0 1 {x} {y} 0'})
    with zipfile.ZipFile(dest/filename,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
    return {'file':filename,'parts':[{'part':p['name'],'xy_mm':[x,y],'dimensions_mm':p['dimensions_mm']} for p,x,y in placements]}

plate_reports=[]
test=next(p for p in models if p['name'].startswith('TEST'))
plate_reports.append(make3mf('00_PRINT_FIRST_fit_coupon.3mf',[(test,85,100)]))
remaining=sorted([p for p in models if not p['name'].startswith('TEST')],key=lambda p:-p['dimensions_mm'][1])
plate=[];x=y=8.;row_h=0.;number=1
for p in remaining:
    w,h=p['dimensions_mm'][:2]
    if x+w>248:x=8;y+=row_h+8;row_h=0
    if y+h>248:
        plate_reports.append(make3mf(f'{number:02d}_prototype_geometry.3mf',plate));number+=1
        plate=[];x=y=8.;row_h=0
    plate.append((p,x,y));x+=w+8;row_h=max(row_h,h)
if plate:plate_reports.append(make3mf(f'{number:02d}_prototype_geometry.3mf',plate))
(root/'print_manifest.json').write_text(json.dumps({'units':'mm','profile':'NONE: select P1S, 0.4 mm nozzle, actual PLA spool in Bambu Studio','exported_closed_mesh_count':len(models),'plates':plate_reports},indent=2),encoding='utf-8')
with (root/'print_parts.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['Part','Quantity','Print_X_mm','Print_Y_mm','Print_Z_mm','Triangles'])
    for p in models:w.writerow([p['name'],1,*[round(v,3) for v in p['dimensions_mm']],len(p['tris'])])
with zipfile.ZipFile(root/'CyberArm_B2_print_package.zip','w',zipfile.ZIP_DEFLATED) as z:
    for folder in ['stl','plates_3mf']:
        for file in (root/folder).iterdir():z.write(file,file.relative_to(root))
    for name in ['engineering_report.md','print_parts.csv','print_manifest.json']:
        file=root/name
        if file.exists():z.write(file,name)
print(json.dumps({'closed_STLs':len(models),'plates':len(plate_reports),'package':str(root/'CyberArm_B2_print_package.zip')},indent=2))
