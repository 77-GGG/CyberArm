import bpy,math,json
from pathlib import Path
from mathutils import Vector
ns={};exec(compile(Path('E:/CyberArm/mechanical/scripts/revC_connections.py').read_text(encoding='utf8'),'helpers','exec'),ns,ns)
for e in ns['ENTRIES']:
    o=bpy.data.objects[e['part']];T=o.matrix_world.inverted()@ns['frame'](e)
    result=[]
    for x in e['holes']:
        for z in [.05,.5,(e['t']-e['cb'])/2,e['t']-e['cb']-.1]:
            rays=[]
            for deg in [0,1,45,89,90,91,135,180,181,225,269,270,271,315]:
                a=math.radians(deg);p=T@Vector((x,0,z));d=T.to_3x3()@Vector((math.cos(a),math.sin(a),0))
                h,at,n,i=o.ray_cast(p,d,distance=50)
                rays.append([deg,round((at-p).length,5) if h else None])
            result.append({'x':x,'z':z,'rays':rays})
    print(e['id'],json.dumps(result),flush=True)
