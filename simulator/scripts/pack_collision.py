"""Pack exporter BVH data into typed arrays (no pickle or runtime mesh parsing)."""
from pathlib import Path
import json
import numpy as np

def pack(collision,path):
    arrays={}
    for index,mesh in enumerate(collision):
        bounds=[];children=[];leaves=[];triangles=[]
        for node in mesh['nodes']:
            bounds.append(node[0]+node[1]);children.append(node[2:4])
            faces=node[4] if len(node)>4 else []
            leaves.append([len(triangles),len(faces)]);triangles.extend(faces)
        arrays[f'b{index}']=np.array(bounds,dtype=np.float64)
        arrays[f'c{index}']=np.array(children,dtype=np.int32)
        arrays[f'f{index}']=np.array(leaves,dtype=np.int32)
        arrays[f't{index}']=np.array(triangles,dtype=np.float64)
    np.savez_compressed(path,**arrays)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]/'assets/revc'
    pack(json.loads((root/'collision.json').read_text()),root/'collision.npz')
    print((root/'collision.npz').stat().st_size)
