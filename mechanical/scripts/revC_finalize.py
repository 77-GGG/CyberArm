"""Export local interface fit coupons and check fastener sweeps without posing the arm."""
import bpy,bmesh,json,math
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
ns={};exec(compile(Path('E:/CyberArm/mechanical/scripts/revC_connections.py').read_text(encoding='utf8'),'helpers','exec'),ns,ns)
OUT=ns['OUT'];SC=bpy.context.scene

def sweeps():
    rows=[]
    for e in ns['ENTRIES'][3:]:
        fixed=bpy.data.objects[{'S04':'ARD_05_Arm_02_v3','S05':'ARD_06_Arm_03','S06':'ARD_07_Gripper_base'}[e['id']]]
        F=ns['frame'](e);Ti=F.inverted()@fixed.matrix_world
        tree=BVHTree.FromPolygons([Ti@v.co for v in fixed.data.vertices],[list(f.vertices) for f in fixed.data.polygons])
        hardware=[o for o in SC.objects if o.name.startswith('REVC_'+e['id']+'_T') and '_WASHER' not in o.name]
        angles=list(range(-180,181,15)) if e['id']!='S06' else list(range(-8,9,2))
        suspects=[];count=0
        for deg in angles:
            R=Matrix.Rotation(math.radians(deg),4,'Z')
            for o in hardware:
                T=R@F.inverted()@o.matrix_world;vv=[T@v.co for v in o.data.vertices]
                ot=BVHTree.FromPolygons(vv,[list(p.vertices) for p in o.data.polygons]);ov=tree.overlap(ot)
                for j in set(j for i,j in ov):
                    pts=[vv[k] for k in o.data.polygons[j].vertices];pts.append(sum(pts,Vector())/len(pts))
                    for pt in pts:
                        at,n,idx,d=tree.find_nearest(pt);count+=1
                        if d>.03 and (pt-at).dot(n)<-.02:suspects.append({'deg':deg,'hardware':o.name,'depth':d})
        rows.append({'id':e['id'],'fixed_support':fixed.name,'sampled_angles_deg':angles,'tested_mesh_poses':len(angles)*len(hardware),'intersecting_samples':count,'suspected_penetrations':suspects})
    (OUT/'fastener_rotation_checks.json').write_text(json.dumps({'scope':'New transmission bolts and nuts against adjacent FIXED print support only. Does not certify whole-arm motion, continuous clearance, servo limits, bearings, load or cables.','results':rows},indent=2),encoding='utf8')
    if any(r['suspected_penetrations'] for r in rows):raise RuntimeError('Fastener sweep interferes '+str(rows))
    return rows

def coupons():
    folder=OUT/'PRINT_FIRST_RevC_mm';folder.mkdir(exist_ok=True);rows=[]
    c=ns['col']('REVC_10_Fit_coupons_NOT_ASSEMBLY')
    for e in ns['ENTRIES']:
        # Copy the true cropped plate from the exploded view. Remove all
        # illustration translations; STL helper centres it on its own bed.
        source=bpy.data.objects['VIEW_'+e['id']+'_PRINT_SECTION']
        o=bpy.data.objects.new('FIT_REVC_'+e['id'],source.data.copy());c.objects.link(o)
        o['FIT_COUPON_ONLY']=True;o['NOT_AN_ARM_PART']=True
        path=folder/(e['id']+'_actual_interface_trial_mm.stl')
        dims=ns['stl'](o.data,path)
        with path.open('r+b') as f:f.write(b'CyberArm RevC ACTUAL INTERFACE FIT COUPON ONLY; mm'.ljust(80,b' '))
        rows.append({'id':e['id'],'file':str(path),'bounds_mm':dims,'source_part':e['part'],'check':ns['stats'](o),'scope':'Cropped mating plate; validates horn hole pitch, access, bolt stack. Does NOT validate neighbouring fixed support or full-part strength.'})
    c.hide_render=True;c.hide_viewport=True
    (OUT/'fit_coupon_manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    return rows

def hub_clearance():
    rows=[]
    for e in ns['ENTRIES']:
        horn=bpy.data.objects['REVC_'+e['id']+'_HORN_DRILL_2p2'];T=ns['frame'](e).inverted()@horn.matrix_world
        vv=[T@v.co for v in horn.data.vertices];back=-e['gap']-e['ht']
        hub=[p for p in vv if back-1.65<=p.z<back-.05]
        # A straight cylindrical hub can have only end-ring vertices outside
        # the nut slab. Intersect its actual mesh edges with slab planes too.
        for edge in horn.data.edges:
            a,b=[vv[k] for k in edge.vertices]
            for z in [back-1.6,back-.8,back-.05]:
                if min(a.z,b.z)<z<max(a.z,b.z):hub.append(a+(b-a)*((z-a.z)/(b.z-a.z)))
        if not hub:raise RuntimeError('No source hub section '+e['id']+' back='+str(back)+' z='+str([min(p.z for p in vv),max(p.z for p in vv)]))
        R=max(math.hypot(p.x,p.y) for p in hub)
        rr=[abs(x)-4/math.sqrt(3)-R for x in e['holes']]
        if min(rr)<=0:raise RuntimeError('Nut envelope conflicts with source hub '+e['id']+str(rr))
        rows.append({'id':e['id'],'source_hub_radius_mm':R,'nut_max_corner_radius_mm':4/math.sqrt(3),'worst_orientation_radial_gap_mm':rr,'physical_fit_required':True})
    (OUT/'nut_hub_clearance.json').write_text(json.dumps(rows,indent=2),encoding='utf8');return rows

print('SWEEPS',json.dumps(sweeps()),flush=True)
print('HUB_GAPS',json.dumps(hub_clearance()),flush=True)
print('COUPONS',len(coupons()),flush=True)
SC['Print_release_status']='FIT REVIEW ONLY: source CAD nominal dimensions; physical OEM horns/centre screws and full-load/full-motion use not certified. Read ASSEMBLY_RevC_zh.md first.'
SC['Latest_connection_doc']='E:/CyberArm/mechanical/arduino_reference_revC/ASSEMBLY_RevC_zh.md'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Arduino_Replica_RevC_Connections.blend'))
print('REVC_FINALIZED',flush=True)
