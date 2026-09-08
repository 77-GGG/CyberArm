"""Audit real interface holes, export print parts, build exploded local views."""
import bpy,bmesh,math,json,struct
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
ns={}
exec(compile(Path('E:/CyberArm/mechanical/scripts/revC_connections.py').read_text(encoding='utf8'),'RevC','exec'),ns,ns)
OUT=ns['OUT'];SC=bpy.context.scene;entries=ns['ENTRIES']

def verify():
    rows=[]
    for e in entries:
        o=bpy.data.objects[e['part']];F=ns['frame'](e);T=o.matrix_world.inverted()@F
        probes=[]
        for x in e['holes']:
            start=T@Vector((x,0,e['t']+1));direction=T.to_3x3()@Vector((0,0,-1))
            hit,loc,normal,idx=o.ray_cast(start,direction,distance=e['t']+e['gap']+2)
            radii=[]
            # Cardinal rays lie exactly on cylinder seam edges. Blender's
            # ray_cast can miss BOTH adjacent faces there (confirmed by +/-1
            # degree probes). Test 24 facet-interior angles at three depths.
            for z in [.05,(e['t']-e['cb'])/2,e['t']-e['cb']-.05]:
                for deg in range(1,360,15):
                    angle=math.radians(deg)
                    p=T@Vector((x,0,z));d=T.to_3x3()@Vector((math.cos(angle),math.sin(angle),0))
                    h,at,n,i=o.ray_cast(p,d,distance=2)
                    radii.append((at-p).length if h else None)
            probes.append({'x':x,'axial_path_obstructed':hit,'radial_measurements_mm':radii})
            if hit or any(v is None or abs(v-1.2)>.004 for v in radii):raise RuntimeError('Bore check failed '+e['id']+str(probes))
        # Centre screwdriver access must pass entirely through the printed plate.
        start=T@Vector((0,0,e['t']+1));d=T.to_3x3()@Vector((0,0,-1))
        central=o.ray_cast(start,d,distance=e['t']+e['gap']+2)[0]
        if central:raise RuntimeError('Blocked centre access '+e['id'])
        horn=bpy.data.objects['REVC_'+e['id']+'_HORN_DRILL_2p2'];H=F.inverted()@horn.matrix_world
        horn_radii=[]
        for x in e['holes']:
            radii=[]
            for v in horn.data.vertices:
                p=H@v.co;r=math.hypot(p.x-x,p.y)
                if abs(r-1.1)<.02 and -e['gap']-e['ht']-.02<=p.z<=-e['gap']+.02:radii.append(r)
            if not radii:raise RuntimeError('Missing drilled horn '+e['id'])
            horn_radii.append([min(radii),max(radii)])
        counterbores=[]
        if e['cb']:
            for x in e['holes']:
                rr=[]
                for deg in range(1,360,15):
                    a=math.radians(deg);p=T@Vector((x,0,e['t']-e['cb']/2));d=T.to_3x3()@Vector((math.cos(a),math.sin(a),0))
                    h,at,n,i=o.ray_cast(p,d,distance=3)
                    rr.append((at-p).length if h else None)
                if any(v is None or abs(v-2.4)>.004 for v in rr):raise RuntimeError('Counterbore check failed '+e['id']+str(rr))
                counterbores.append({'x':x,'radial_measurements_mm':rr})
        rows.append({'id':e['id'],'print_mesh':ns['stats'](o),'transmission_bores':probes,'counterbores':counterbores,'centre_access_obstructed':central,'horn_hole_vertex_radii_mm':horn_radii})
    (OUT/'connection_geometry_checks.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    return rows

def export():
    folder=OUT/'STL_RevC_mm';folder.mkdir(exist_ok=True)
    parts=ns['helpers']['parts']();groups={}
    for o in parts:groups.setdefault(Path(o['source_file']).stem,[]).append(o)
    rows=[]
    for stem,objects in groups.items():
        o=objects[0]
        if stem in ['Arm_01','Arm_02_v3']:R=Matrix.Identity(4)
        elif stem in ['Gripper_1','Gripper_1_1']:R=Matrix.Rotation(-math.pi/2,4,'Y')
        else:R=Matrix.Rotation(math.pi/2,4,'X')
        path=folder/(stem+'_RevC_mm.stl');bounds=ns['stl'](o.data,path,R)
        with path.open('r+b') as f:f.write(b'CyberArm RevC M2 connection FIT REVIEW; units=mm'.ljust(80,b' '))
        rows.append({'file':str(path),'object':o.name,'quantity':len(objects),'bounds_mm':bounds,'stats':ns['stats'](o),'final_print_release':False})
    (OUT/'print_manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    return rows

def collision_samples():
    # Test newly added transmission hardware against all PRINT solids. Intended
    # nut/thread engagement is excluded. OEM screw / servo internals not certified.
    prints=ns['helpers']['parts']();trees={};boxes={}
    for o in prints:
        vv=[o.matrix_world@v.co for v in o.data.vertices]
        trees[o.name]=BVHTree.FromPolygons(vv,[list(p.vertices) for p in o.data.polygons])
        boxes[o.name]=[[min(v[k] for v in vv) for k in range(3)],[max(v[k] for v in vv) for k in range(3)]]
    results=[]
    for o in SC.objects:
        if not o.name.startswith('REVC_S') or '_T' not in o.name or o.type!='MESH':continue
        vv=[o.matrix_world@v.co for v in o.data.vertices];box=[[min(v[k] for v in vv) for k in range(3)],[max(v[k] for v in vv) for k in range(3)]]
        tree=BVHTree.FromPolygons(vv,[list(p.vertices) for p in o.data.polygons])
        for p in prints:
            b=boxes[p.name]
            if any(box[0][k]>b[1][k] or b[0][k]>box[1][k] for k in range(3)):continue
            ov=trees[p.name].overlap(tree)
            if not ov:continue
            ids=set(j for i,j in ov);inside=[]
            for j in ids:
                pts=[vv[k] for k in o.data.polygons[j].vertices];pts.append(sum(pts,Vector())/len(pts))
                for pt in pts:
                    at,n,idx,dist=trees[p.name].find_nearest(pt)
                    if dist>.03 and (pt-at).dot(n)<-.02:inside.append(dist)
            if inside:results.append({'hardware':o.name,'print':p.name,'penetrating_samples':len(inside),'max_depth_mm':max(inside)})
    (OUT/'transmission_fastener_collision_samples.json').write_text(json.dumps({'method':'Static vertex/face-centre samples of intersecting triangles against printed solids; .03 mm threshold, not continuous collision detection','suspected_interferences':results},indent=2),encoding='utf8')
    return results

def exploded_scene(e):
    scene=bpy.data.scenes.new('EXPLODED_'+e['id']+'_'+e['label'].replace(' ','_'))
    bpy.context.window.scene=scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.001;scene.unit_settings.length_unit='MILLIMETERS'
    F=ns['frame'](e);Ti=F.inverted()
    def copy_local(source,name,dz):
        o=bpy.data.objects.new(name,source.data.copy());scene.collection.objects.link(o)
        o.data.transform(Ti@source.matrix_world);o.location.z=dz
        o['ILLUSTRATION_ONLY']=True;o['NOT_FOR_PRINT']=True;return o
    # Real print geometry, cropped around this interface; not a new printed part.
    p=copy_local(bpy.data.objects[e['part']],'VIEW_'+e['id']+'_PRINT_SECTION',0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=128,radius=15.5,depth=e['t']+e['gap']+2)
    tool=bpy.context.object;tool.location.z=(e['t']-e['gap'])/2
    ns['boolean'](p,tool,'INTERSECT');p.location.z=13
    horn=copy_local(bpy.data.objects['REVC_'+e['id']+'_HORN_DRILL_2p2'],'VIEW_'+e['id']+'_STOCK_HORN',0)
    for obj in list(SC.objects):
        if obj.name.startswith('REVC_'+e['id']+'_T'):
            shift=-11 if '_NUT' in obj.name else 23 if '_WASHER' in obj.name else 33
            copy_local(obj,'VIEW_'+obj.name,shift)
    copy_local(bpy.data.objects['REVC_'+e['id']+'_CENTRE_OEM_LOCK'],'VIEW_'+e['id']+'_OEM_CENTRE_LOCK',50)
    servo_names={'S01':'REVB_S01_Base_MG996R_SOURCE','S02':'REVB_S02_Shoulder_MG996R_SOURCE','S03':'REVB_S03_Elbow_MG996R_SOURCE',
                 'S04':'ARD_S04_Wrist_roll_MG90S_USER_MODEL','S05':'ARD_S05_Wrist_pitch_MG90S_USER_MODEL','S06':'ARD_S06_Gripper_MG90S_USER_MODEL'}
    copy_local(bpy.data.objects[servo_names[e['id']]],'VIEW_'+e['id']+'_SERVO',-30)
    # Short dashed axes leave the real screw and hole surfaces clearly visible.
    guide_mat=ns['material']('REVC_Guide',(.18,.25,.3))
    for x in [0]+e['holes']:
        for z in range(-24,49,4):
            bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.055,depth=1.6,location=(x,0,z))
            line=bpy.context.object;line.name='VIEW_axis';line.data.materials.append(guide_mat)
    world=bpy.data.worlds.new('REVC_Exploded_world');scene.world=world;world.use_nodes=True
    bg=world.node_tree.nodes.get('Background');bg.inputs[0].default_value=(.7,.76,.86,1);bg.inputs[1].default_value=.5
    camdata=bpy.data.cameras.new('EXPLODED_Camera');cam=bpy.data.objects.new('EXPLODED_Camera',camdata);scene.collection.objects.link(cam)
    cam.location=(88,-180,105);target=Vector((0,0,-4));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();camdata.type='ORTHO';camdata.ortho_scale=158;camdata.clip_end=2000;scene.camera=cam
    for loc,power,size in [((-70,-80,160),1400000,130),((100,30,80),1000000,110)]:
        data=bpy.data.lights.new('Exploded_light','AREA');data.energy=power;data.size=size
        o=bpy.data.objects.new('Exploded_light',data);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(target-o.location).to_track_quat('-Z','Y').to_euler()
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
    scene.render.resolution_x=1300;scene.render.resolution_y=1600;scene.render.resolution_percentage=100
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=-.6
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/('Connection_'+e['id']+'_exploded.png'))
    scene['NOTICE']='Exploded illustration; print component shown as cropped section. Centre screw is OEM retaining screw, not M2 transmission fastener. No exploded objects for printing.'
    return scene

if __name__=='__main__':
    print('VERIFY',len(verify()),'interfaces passed',flush=True)
    print('EXPORT',len(export()),flush=True)
    suspected=collision_samples();print('COLLISION',json.dumps(suspected),flush=True)
    if suspected:raise RuntimeError('Resolve hardware/print interference before delivery')
    scenes=[exploded_scene(e) for e in entries]
    bpy.context.window.scene=SC
    for o in SC.objects:o.select_set(False)
    bpy.data.objects['ARM_CONTROLS'].select_set(True);bpy.context.view_layer.objects.active=bpy.data.objects['ARM_CONTROLS']
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Arduino_Replica_RevC_Connections.blend'))
    # Render the critical cross-horn interface first, then the other five.
    for scene in sorted(scenes,key=lambda s:0 if s.name.startswith('EXPLODED_S05') else 1):
        bpy.context.window.scene=scene;bpy.ops.render.render(write_still=True)
    bpy.context.window.scene=SC;SC.camera=bpy.data.objects['ARD_Camera_Servo_side'];SC.render.resolution_x=1400;SC.render.resolution_y=1100;SC.cycles.samples=24
    SC.render.filepath=str(OUT/'RevC_assembly.png');bpy.ops.render.render(write_still=True)
    print('REV_C_DELIVERY_COMPLETE',flush=True)
