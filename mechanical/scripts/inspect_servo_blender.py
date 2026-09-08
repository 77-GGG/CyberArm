import bpy, json, numpy as np
from pathlib import Path
p = next(Path('E:/CyberArm/mechanical').rglob('servo_MG90S.STL'))
bpy.ops.wm.stl_import(filepath=str(p))
o = bpy.context.object
o.name = 'MG90S_SOURCE_INSPECTION'
v = np.array([tuple(v.co) for v in o.data.vertices])
print('SERVO_BOUNDS_MM', v.min(axis=0).tolist(), v.max(axis=0).tolist())
for axis in range(3):
    levels, cnt = np.unique(np.round(v[:,axis], 3), return_counts=True)
    inds = np.argsort(cnt)[-25:]
    print('PLANES', axis, sorted(zip(levels[inds].tolist(),cnt[inds].tolist())))
Path('E:/CyberArm/mechanical/inspection_data/servo_bounds.json').write_text(json.dumps({'min':v.min(axis=0).tolist(),'max':v.max(axis=0).tolist()}))
for a in bpy.context.screen.areas:
    if a.type == 'VIEW_3D':
        a.spaces.active.region_3d.view_distance = 90
        a.spaces.active.region_3d.view_location = o.location
