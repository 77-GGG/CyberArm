"""Extract CRC-verified display tessellation, NOT exact B-rep, from local SLDPRT.

Container and six-array layout reference: cadmpeg project, CC-BY-4.0:
https://github.com/cadmpeg/cadmpeg/blob/main/docs/formats/sldprt.md
Display coordinates are f32 metres. Exports use millimetres.
"""
from pathlib import Path
import struct, zlib, json
import numpy as np

SRC=Path('E:/CyberArm/mechanical/MG996R Servo Motor')
OUT=Path('E:/CyberArm/mechanical/fusion_reference_review/mg996r_extracted')
MAGIC=bytes.fromhex('140006000800')


def blocks(data):
    pos=0
    while True:
        pos=data.find(MAGIC,pos)
        if pos<0:return
        start=pos;pos+=6
        if start+26>len(data):continue
        typ,crc,cs,us,ns=struct.unpack_from('<5I',data,start+6)
        if ns>1000 or us>100_000_000 or cs>len(data) or start+26+ns+cs>len(data):continue
        name=bytes(((x<<4)&255)|(x>>4) for x in data[start+26:start+26+ns]).decode('utf8','replace')
        try:payload=zlib.decompress(data[start+26+ns:start+26+ns+cs],-15)
        except zlib.error:continue
        if len(payload)!=us or zlib.crc32(payload)!=crc:continue
        yield name,payload
        pos=start+26+ns+cs


def tables(data):
    marker=struct.pack('<3I',4,8,2)
    pos=0
    pairs=[(4,8),(12,100),(12,100),(4,8),(4,8),(1,8)]
    while True:
        start=data.find(marker,pos)
        if start<0:return
        pos=start+1;cur=start;arrays=[]
        for size,kind in pairs:
            if cur+16>len(data):break
            sz,k,flags,n=struct.unpack_from('<4I',data,cur);cur+=16
            if (sz,k,flags)!=(size,kind,2) or n>10_000_000 or cur+sz*n>len(data):break
            arrays.append((n,data[cur:cur+sz*n]));cur+=sz*n
        if len(arrays)!=6:continue
        lengths=np.frombuffer(arrays[0][1],dtype='<u4')
        if len(lengths)==0 or min(lengths)<3 or int(sum(lengths))!=arrays[1][0]:continue
        if arrays[2][0] not in (0,arrays[1][0]):continue
        c=np.frombuffer(arrays[4][1],dtype='<u4')
        if len(c)!=len(lengths) or not np.array_equal(c,2*lengths-2):continue
        v=np.frombuffer(arrays[1][1],dtype='<f4').reshape(-1,3).astype(float)*1000
        if not np.isfinite(v).all():continue
        normals=np.frombuffer(arrays[2][1],dtype='<f4').reshape(-1,3) if arrays[2][0] else None
        tris=[];offset=0
        for n in lengths:
            for j in range(int(n)-2):
                ids=[offset+j,offset+j+1,offset+j+2]
                if j%2:ids[0],ids[1]=ids[1],ids[0]
                tri=v[ids]
                cross=np.cross(tri[1]-tri[0],tri[2]-tri[0])
                if np.linalg.norm(cross)<1e-12:continue
                if normals is not None and np.dot(cross,normals[ids].mean(axis=0))<0:tri=tri[[0,2,1]]
                tris.append(tri)
            offset+=int(n)
        if tris:yield np.array(tris)
        pos=cur


def save_stl(path,tri):
    dtype=np.dtype([('normal','<f4',3),('verts','<f4',(3,3)),('attr','<u2')])
    records=np.zeros(len(tri),dtype=dtype)
    n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
    records['normal']=n;records['verts']=tri
    path.write_bytes(b'SW cached display mesh; millimetres; not exact BREP'.ljust(80,b' ')+struct.pack('<I',len(tri))+records.tobytes())


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report=[]
    for path in list(SRC.glob('*.SLDPRT'))+list(SRC.glob('*.SLDASM')):
        parts=list(blocks(path.read_bytes()))
        rec={'source':str(path),'blocks':[{'name':n,'bytes':len(p)} for n,p in parts]}
        tess=[]
        for name,payload in parts:
            if 'DisplayLists' in name:
                tess.extend(tables(payload))
        if tess:
            tri=np.concatenate(tess)
            stl=OUT/(path.stem+'_display_mm.stl')
            save_stl(stl,tri)
            v=tri.reshape(-1,3)
            rec.update({'stl':str(stl),'tables':len(tess),'triangles':len(tri),
                        'bounds_mm':[v.min(axis=0).tolist(),v.max(axis=0).tolist()],
                        'size_mm':np.ptp(v,axis=0).tolist(),
                        'status':'CRC verified source tessellation; tessellation error unknown'})
        report.append(rec)
    (OUT/'extraction_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps([{k:v for k,v in r.items() if k!='blocks'} for r in report],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
