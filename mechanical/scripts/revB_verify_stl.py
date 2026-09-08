"""Independent binary STL roundtrip checks without modifying artifacts."""
import struct,json,math
from pathlib import Path
from collections import Counter,defaultdict
root=Path('E:/CyberArm/mechanical/archive/arduino_reference_revB')
rows=[]
for folder in ['STL_FIT_REVIEW_mm','PRINT_FIRST_horn_tests_mm']:
    for path in sorted((root/folder).glob('*.stl')):
        raw=path.read_bytes();n=struct.unpack_from('<I',raw,80)[0]
        assert len(raw)==84+50*n,(path,'Invalid binary STL length')
        indices={};vertices=[];edges=Counter();adj=defaultdict(set);bad=0;volume6=0.
        for i in range(n):
            t=struct.unpack_from('<12fH',raw,84+50*i)
            pts=[tuple(t[k:k+3]) for k in (3,6,9)];ids=[]
            for v in pts:
                assert all(math.isfinite(x) for x in v)
                if v not in indices:indices[v]=len(vertices);vertices.append(v)
                ids.append(indices[v])
            if len(set(ids))!=3:bad+=1
            for a,b in zip(ids,ids[1:]+ids[:1]):
                edges[tuple(sorted((a,b)))]+=1;adj[a].add(b);adj[b].add(a)
            a,b,c=pts
            volume6+=a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0])
        unseen=set(range(len(vertices)));components=[]
        while unseen:
            todo=[unseen.pop()];count=0
            while todo:
                a=todo.pop();count+=1
                for b in adj[a]:
                    if b in unseen:unseen.remove(b);todo.append(b)
            components.append(count)
        row={'file':str(path),'triangles':n,'vertices':len(vertices),'nonmanifold_edges':sum(v!=2 for v in edges.values()),'degenerate_index_triangles':bad,
             'connected_vertex_components':sorted(components,reverse=True),'signed_volume_mm3':volume6/6,'bounds_mm':[[min(p[k] for p in vertices),max(p[k] for p in vertices)] for k in range(3)]}
        rows.append(row)
(root/'export_roundtrip_checks.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
print(json.dumps([dict(file=Path(r['file']).name,nonmanifold=r['nonmanifold_edges'],components=len(r['connected_vertex_components']),degenerate=r['degenerate_index_triangles'],volume=r['signed_volume_mm3']) for r in rows],indent=2))
if any(r['nonmanifold_edges'] or r['degenerate_index_triangles'] or r['signed_volume_mm3']<=0 for r in rows):raise SystemExit(1)
