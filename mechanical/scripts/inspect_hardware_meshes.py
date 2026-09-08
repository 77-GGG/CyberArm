"""Measure coplanar boundary loops in source hardware meshes, mm coordinates."""
from pathlib import Path
import numpy as np
import struct, json
from collections import Counter, defaultdict
from extract_solidworks_display_mesh import save_stl, blocks, SRC, OUT
import xml.etree.ElementTree as ET


def read_stl(path):
    b=Path(path).read_bytes();n=struct.unpack_from('<I',b,80)[0]
    return np.frombuffer(b,dtype=np.dtype([('n','<f4',3),('v','<f4',(3,3)),('a','<u2')]),count=n,offset=84)['v'].astype(float)


def loops(path):
    tri=read_stl(path)
    v,idx=np.unique(np.round(tri.reshape(-1,3),5),axis=0,return_inverse=True)
    faces=idx.reshape(-1,3);result=[]
    for axis in range(3):
        flat=np.ptp(v[faces][:,:,axis],axis=1)<.00003
        levels=Counter(np.round(v[faces[flat]][:,0,axis],4))
        for level,number in levels.most_common(18):
            ff=faces[flat & (abs(v[faces[:,0],axis]-level)<.0001)]
            counts=Counter(tuple(sorted(e)) for f in ff for e in ((f[0],f[1]),(f[1],f[2]),(f[2],f[0])))
            edges={e for e,n in counts.items() if n==1}
            adj=defaultdict(set)
            for a,b in edges:adj[a].add(b);adj[b].add(a)
            todo=set(adj)
            while todo:
                seed=todo.pop();component={seed};stack=[seed]
                while stack:
                    node=stack.pop()
                    for nei in adj[node]:
                        if nei in todo:todo.remove(nei);component.add(nei);stack.append(nei)
                if len(component)<7:continue
                points=v[list(component)];xy=points[:,[k for k in range(3) if k!=axis]]
                fit=np.linalg.lstsq(np.c_[2*xy,np.ones(len(xy))],np.sum(xy*xy,axis=1),rcond=None)[0]
                radii=np.linalg.norm(xy-fit[:2],axis=1)
                if np.ptp(radii)>.025:continue
                center=np.zeros(3);center[axis]=level;center[[k for k in range(3) if k!=axis]]=fit[:2]
                result.append({'axis':'XYZ'[axis],'center_mm':center.tolist(),'radius_mm':float(radii.mean()),'spread_mm':float(np.ptp(radii))})
    return {'source':str(path),'bounds_mm':[v.min(axis=0).tolist(),v.max(axis=0).tolist()],'circles':result}


def assemble_motor():
    xml=next(p for n,p in blocks((SRC/'MG996R Servo Motor.SLDASM').read_bytes()) if n=='swXmlContents/COMPINSTANCETREE')
    tree=ET.fromstring(xml)
    refs=[e for e in tree.iter() if e.tag.endswith('swReference')]
    assembled=[];record=[]
    norm=np.array([[-1,0,0,-10.45],[0,0,1,0],[0,1,0,-24.55],[0,0,0,1.]])
    for name in ['Case','Output Shaft','Rubber Wire Cable Sleeve']:
        ref=next(e for e in refs if e.attrib['swName']==name)
        m=np.array([float(x) for x in ref.attrib['swTransform'].split()]).reshape(4,4).T
        m[:3,3]*=1000
        full=norm@m
        tri=read_stl(OUT/(name+'_display_mm.stl'))
        tri=tri@full[:3,:3].T+full[:3,3]
        assembled.append(tri)
        record.append({'part':name,'source_assembly_matrix_mm':m.tolist(),'canonical_matrix_mm':full.tolist()})
    mesh=np.concatenate(assembled)
    save_stl(OUT/'MG996R_case_shaft_sleeve_canonical_mm.stl',mesh)
    horn=read_stl(OUT/'Servo Horns_display_mm.stl')
    rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])
    horn=horn@rotation.T+np.array([0,0,1.15])
    save_stl(OUT/'MG996R_round_horn_canonical_mm.stl',horn)
    (OUT/'source_assembly_transforms.json').write_text(json.dumps(record,indent=2),encoding='utf8')


if __name__=='__main__':
    assemble_motor()
    sources=[OUT/'Case_display_mm.stl',OUT/'Servo Horns_display_mm.stl',OUT/'Output Shaft_display_mm.stl']
    sources+=list(Path('E:/CyberArm/mechanical/servo配件').glob('*.stl'))
    report=[loops(p) for p in sources]
    (OUT/'hardware_circle_measurements.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
