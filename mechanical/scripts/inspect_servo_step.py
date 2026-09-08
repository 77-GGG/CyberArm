import sys, json
sys.path.append('C:/Program Files/FreeCAD 1.1/bin')
sys.path.append('C:/Program Files/FreeCAD 1.1/lib')
import FreeCAD as App, Part
from pathlib import Path
p = next(Path('E:/CyberArm/mechanical').rglob('servo_MG90S.STEP'))
s=Part.Shape()
s.read(str(p))
out={'bbox':str(s.BoundBox),'solids':len(s.Solids),'circles':[]}
seen=set()
for edge in s.Edges:
    try:
        c=edge.Curve
    except TypeError:
        continue
    if isinstance(c,Part.Circle):
        key=tuple(round(x,3) for x in (*c.Center,*c.Axis,c.Radius))
        if key not in seen:
            seen.add(key);out['circles'].append(key)
Path('E:/CyberArm/mechanical/inspection_data/servo_geometry.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
