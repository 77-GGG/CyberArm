import bpy,bmesh,json,math
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ns={};exec(compile(Path('E:/CyberArm/mechanical/scripts/revC_connections.py').read_text(encoding='utf8'),'helpers','exec'),ns,ns)
servo_names=['REVB_S01_Base_MG996R_SOURCE','REVB_S02_Shoulder_MG996R_SOURCE','REVB_S03_Elbow_MG996R_SOURCE','ARD_S04_Wrist_roll_MG90S_USER_MODEL','ARD_S05_Wrist_pitch_MG90S_USER_MODEL','ARD_S06_Gripper_MG90S_USER_MODEL']
results=[]
for e,sn in zip(ns['ENTRIES'],servo_names):
    F=ns['frame'](e);servo=bpy.data.objects[sn];Ti=F.inverted()@servo.matrix_world
    sv=[Ti@v.co for v in servo.data.vertices];sp=[list(p.vertices) for p in servo.data.polygons];st=BVHTree.FromPolygons(sv,sp)
    pair=[]
    for o in bpy.context.scene.objects:
        if not o.name.startswith('REVC_'+e['id']+'_T'):continue
        T=F.inverted()@o.matrix_world;bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.transform(T)
        tree=BVHTree.FromBMesh(bm);ov=tree.overlap(st);bad=[]
        for j in set(j for i,j in ov):
            pts=[sv[k] for k in sp[j]];pts.append(sum(pts,Vector())/len(pts))
            for pt in pts:
                at,n,idx,dist=tree.find_nearest(pt)
                if dist>.02 and (pt-at).dot(n)<-.015:bad.append({'d':dist,'p':list(pt)})
        pair.append({'hardware':o.name,'surface_pairs':len(ov),'penetrating_samples':len(bad),'deepest':sorted(bad,key=lambda a:-a['d'])[:3]})
        bm.free()
    results.append({'id':e['id'],'servo_hardware':pair})
    if e['id']<'S04':continue
    fixed=bpy.data.objects[{'S04':'ARD_05_Arm_02_v3','S05':'ARD_06_Arm_03','S06':'ARD_07_Gripper_base'}[e['id']]]
    T=fixed.matrix_world.inverted()@F;depths=[]
    for r in [3.5,4.5,6,8.5,11,13.5]:
        for deg in [1,46,91,136,181,226,271,316]:
            a=math.radians(deg);p=T@Vector((r*math.cos(a),r*math.sin(a),1));d=T.to_3x3()@Vector((0,0,-1))
            h,at,n,i=fixed.ray_cast(p,d,distance=15)
            if h:
                h2,at2,n2,i2=fixed.ray_cast(at+d*.002,d,distance=10)
                depths.append([r,deg,round(1-(at-p).length,4),round(1-(at2-p).length,4) if h2 else None])
    print('FIXED',e['id'],fixed.name,json.dumps(depths),flush=True)
(ns['OUT']/'hardware_servo_probe.json').write_text(json.dumps(results,indent=2),encoding='utf8')
print('SERVO',json.dumps(results),flush=True)
