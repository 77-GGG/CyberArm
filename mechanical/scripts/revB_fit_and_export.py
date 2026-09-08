"""Blender RevB dimensional fit work. Source files are never overwritten."""
import bpy, bmesh, json, math, struct
from pathlib import Path
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

OUT=Path('E:/CyberArm/mechanical/archive/arduino_reference_revB')
ns={}
exec(compile(Path('E:/CyberArm/mechanical/scripts/refine_reference_blender.py').read_text(encoding='utf8'),'refine','exec'),ns,ns)
stats=ns['stats']; cleaned=ns['cleaned']; report=ns['write_report']

def parts():
    return [o for o in next(c for c in bpy.context.scene.collection.children if c.name.startswith('ARD_01_')).objects if o.type=='MESH']

def audit(tag='before'):
    hardware=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and (o.name.startswith('REVB_S') or '_USER_MODEL' in o.name)]
    prints=parts(); boxes={}; trees={}; results=[]
    for o in prints+hardware:
        vs=[o.matrix_world@v.co for v in o.data.vertices]
        boxes[o.name]=[[min(v[i] for v in vs) for i in range(3)],[max(v[i] for v in vs) for i in range(3)]]
        trees[o.name]=BVHTree.FromPolygons(vs,[list(p.vertices) for p in o.data.polygons])
    for a in prints:
        for b in hardware:
            x,y=boxes[a.name],boxes[b.name]
            if any(x[0][k]>y[1][k] or y[0][k]>x[1][k] for k in range(3)):continue
            ov=trees[a.name].overlap(trees[b.name])
            if ov:results.append({'part':a.name,'hardware':b.name,'surface_pairs':len(ov)})
    (OUT/f'fit_surface_{tag}.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    return results

def intersect(a_name,b_name):
    a=bpy.data.objects[a_name];b=bpy.data.objects[b_name]
    tmp=bpy.data.objects.new('REVB_TEMP_CHECK',a.data.copy());bpy.context.scene.collection.objects.link(tmp);tmp.matrix_world=a.matrix_world
    mod=tmp.modifiers.new('Intersection','BOOLEAN');mod.operation='INTERSECT';mod.solver='EXACT';mod.object=b
    ev=tmp.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
    bm=bmesh.new();bm.from_mesh(mesh)
    # Measure in the PRINT PART's native mm coordinates for understandable pockets.
    vs=[v.co.copy() for v in bm.verts]
    r={'part':a_name,'hardware':b_name,'volume_mm3':abs(bm.calc_volume(signed=True)),
       'nonmanifold':sum(not e.is_manifold for e in bm.edges),
       'bounds_local':[[min(v[i] for v in vs) for i in range(3)],[max(v[i] for v in vs) for i in range(3)]] if vs else None}
    bm.free();ev.to_mesh_clear();mesh_copy=tmp.data;bpy.data.objects.remove(tmp,do_unlink=True);bpy.data.meshes.remove(mesh_copy)
    return r

def boolean(o,tool,operation):
    bpy.context.view_layer.objects.active=o
    mod=o.modifiers.new('RevB_'+operation,'BOOLEAN');mod.operation=operation;mod.solver='EXACT';mod.object=tool
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mesh=tool.data;bpy.data.objects.remove(tool,do_unlink=True)
    if mesh.users==0:bpy.data.meshes.remove(mesh)
    cleaned(o)
    if stats(o)['nonmanifold_edges']:raise RuntimeError('Nonmanifold '+o.name)

def cylinder(o,center,radius,depth,axis,operation):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=radius,depth=depth)
    tool=bpy.context.object
    rot=Vector((0,0,1)).rotation_difference(Vector(axis)).to_matrix().to_4x4()
    tool.matrix_world=o.matrix_world@Matrix.Translation(center)@rot
    boolean(o,tool,operation)

def box(o,center,size,operation):
    bpy.ops.mesh.primitive_cube_add(size=1)
    tool=bpy.context.object;tool.scale=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    tool.matrix_world=o.matrix_world@Matrix.Translation(center)
    boolean(o,tool,operation)

def mounting_holes():
    rules=[('ARD_05_Arm_02_v3',1,1.1,[(13.8,0,5.5),(-13.8,0,5.5)],[(.047,0,0),(-.247,0,0)]),
           ('ARD_06_Arm_03',2,1,[(0,9.2,0),(0,36.8,0)],[(0,-.347,0),(0,-.053,0)]),
           ('ARD_07_Gripper_base',1,1,[(13.1,0,-25),(40.7,0,-25)],[(-.347,0,0),(-.053,0,0)])]
    results=[]
    for name,axis,radius,cs,ds in rules:
        o=bpy.data.objects[name]
        if o.get('RevB_servo_mounts'):continue
        original=o.data.copy();o.data=o.data.copy()
        try:
            count=sum(ns['shift_hole'](o,axis,c,radius,d) for c,d in zip(cs,ds))
            cleaned(o)
            if stats(o)['nonmanifold_edges']:raise RuntimeError('Invalid mounting holes')
        except Exception:
            o.data=original;raise
        o['RevB_servo_mounts']=f'27.894 mm source MG90S ear centers; diameter {radius*2} mm pilot retained'
        results.append({'object':name,'moved_vertices':count,'stats':stats(o)})
    report('mg90s_mounting_holes',results);return results

def gripper_holes():
    o=bpy.data.objects['ARD_08_gear2']
    if o.get('RevB_single_horn'):return 'Already adapted'
    original=o.data.copy();o.data=o.data.copy()
    try:
        # Native source has thickness y=0..4; fully refill old through holes.
        bm=bmesh.new();bm.from_mesh(o.data)
        for x in [-14.60634,-5.60634]:
            walls=[f for f in bm.faces if all(abs(math.hypot(v.co.x-x,v.co.z)-1.3)<.003 for v in f.verts)]
            if len(walls)<12:raise RuntimeError('Hole wall not found')
            bmesh.ops.delete(bm,geom=walls,context='FACES_ONLY')
        # Remove unused diagonal wall edges, then cap the four circular loops.
        bmesh.ops.delete(bm,geom=[e for e in bm.edges if not e.link_faces],context='EDGES')
        filled=bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=0)
        bmesh.ops.triangulate(bm,faces=filled['faces'])
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(o.data);bm.free()
        for radius in [6,11]:cylinder(o,(-10.10634-radius,2,0),1.1,10,(0,1,0),'DIFFERENCE')
        if stats(o)['nonmanifold_edges']:raise RuntimeError('Invalid single horn interface')
    except Exception:
        o.data=original;raise
    o['RevB_single_horn']='Stock single horn drives gear through two 2.2 mm clearance holes, radii 6 and 11 mm; no glue'
    report('single_horn_gear2',stats(o));return stats(o)

def save():
    ns['smooth_surfaces']();return ns['save']()

def framed_box(o,frame,center,size):
    bpy.ops.mesh.primitive_cube_add(size=1)
    tool=bpy.context.object;tool.scale=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    tool.matrix_world=frame@Matrix.Translation(center)
    boolean(o,tool,'DIFFERENCE')

def clear_mounts():
    results=[]
    for part,servo in [('ARD_03_Waist','REVB_S02_Shoulder_MG996R_SOURCE'),('ARD_05_Arm_02_v3','REVB_S03_Elbow_MG996R_SOURCE')]:
        o=bpy.data.objects[part];s=bpy.data.objects[servo]
        if o.get('RevB_ear_pockets'):continue
        old=o.data.copy();o.data=o.data.copy();before=stats(o)
        try:
            # Assembly-entry relief on the servo-back side. 0.25 mm nominal
            # envelope clearance; retain the material in front of the ear seat.
            framed_box(o,s.matrix_world,(-10.45,0,-24.85),(41.4,20.5,39.4))
            for x in (-34.175,13.275):
                framed_box(o,s.matrix_world,(x,0,-28.95),(7.05,20.5,31.1))
                # Actual case has a 1 mm wide triangular rib on each mounting ear.
                framed_box(o,s.matrix_world,(x,0,-12.5),(7.05,1.5,1.7))
            # Source ear centres differ from the original nominal housing by .2 mm.
            inv=o.matrix_world.inverted()@s.matrix_world
            for x in (-34.45,13.55):
                for y in (-5,5):
                    local=inv@Vector((x,y,-12))
                    direction=inv.to_3x3()@Vector((0,0,1))
                    cylinder(o,local,1.4,15,direction,'DIFFERENCE')
        except Exception:
            o.data=old;raise
        o['RevB_ear_pockets']='MG996R source envelope .25 mm lateral clearance, exact nominal axial seat; shoulder seat ~4.6 mm, elbow ~5.1 mm, locally relieved at ribs; physical trial required'
        results.append({'part':part,'before':before,'after':stats(o)})
    o=bpy.data.objects['ARD_07_Gripper_base']
    if not o.get('RevB_cross_clearance'):
        old=o.data.copy();o.data=o.data.copy();before=stats(o)
        try:
            # Cross horn plate is x=6.5..9.0 in the print-part frame. Open the
            # cross arms to the servo side, with .25 clearance around the sides.
            box(o,(6.6,-9,-63),(4.8,37.5,7.5),'DIFFERENCE')
            box(o,(6.6,-9,-63),(4.8,7.5,19.5),'DIFFERENCE')
        except Exception:
            o.data=old;raise
        o['RevB_cross_clearance']='Stock cross plate relief; original 5 mm attachment plate retained from x=9 to14'
        results.append({'part':o.name,'before':before,'after':stats(o)})
    report('mount_clearance',results);return results

def contact_check():
    pairs=audit('checked');results=[]
    for pair in pairs:
        p=bpy.data.objects[pair['part']];s=bpy.data.objects[pair['hardware']]
        tree=BVHTree.FromPolygons([v.co for v in p.data.vertices],[list(f.vertices) for f in p.data.polygons])
        T=p.matrix_world.inverted()@s.matrix_world
        other=BVHTree.FromPolygons([T@v.co for v in s.data.vertices],[list(f.vertices) for f in s.data.polygons])
        ids=set(j for i,j in tree.overlap(other));samples=[]
        for j in ids:
            pts=[T@s.data.vertices[k].co for k in s.data.polygons[j].vertices]
            samples.extend(pts);samples.append(sum(pts,Vector())/len(pts))
        inside=[]
        for pt in samples:
            near,normal,index,d=tree.find_nearest(pt)
            if near is not None and d>.02 and (pt-near).dot(normal)<-.015:
                inside.append({'point_in_part_mm':list(pt),'depth_to_nearest_surface_mm':d})
        r=dict(pair,sampled_points=len(samples),penetrating_sample_count=len(inside),max_sample_depth_mm=max((q['depth_to_nearest_surface_mm'] for q in inside),default=0))
        r['deepest_samples']=sorted(inside,key=lambda q:q['depth_to_nearest_surface_mm'],reverse=True)[:5]
        results.append(r)
    report('surface_contact_check',{'method':'Hardware vertices and face centroids of intersecting triangles; signed nearest face, 0.02 mm threshold. Conservative local test, not continuous collision detection; hardware is non-watertight source display geometry.','results':results})
    return results

def fasteners():
    # Visible heads are envelopes, not certified threads. Their centres now match
    # the adapted PRINT holes and sit on the outside face, not inside the plate.
    rules=[('S01','ARD_03_Waist',[(0,4.6,-7),(0,4.6,7)],(0,1,0)),
           ('S02','ARD_04_Arm_01',[(0,-7,6.6),(0,7,6.6)],(0,0,1)),
           ('S03','ARD_04_Arm_01',[(0,113,6.6),(0,127,6.6)],(0,0,1)),
           ('S04','ARD_06_Arm_03',[(-11,5.6,0),(1,5.6,0)],(0,1,0)),
           ('S05','ARD_07_Gripper_base',[(14.6,-9,-68.1),(14.6,-9,-57.9)],(1,0,0)),
           ('S06','ARD_08_gear2',[(-16.10634,4.6,0),(-21.10634,4.6,0)],(0,1,0))]
    for short,part,cs,axis in rules:
        p=bpy.data.objects[part]
        for suffix,c in zip(('', '.001'),cs):
            o=bpy.data.objects['ARD_'+short+'_horn_screw'+suffix]
            o.matrix_world=p.matrix_world@Matrix.Translation(c)@Vector((0,0,1)).rotation_difference(Vector(axis)).to_matrix().to_4x4()
            o['NOT_FOR_PRINT']=True;o['reference_only']='Fastener head envelope at adapted hole; thread, length and actual head diameter require hardware selection'
    return '12 visible horn fastening heads aligned to current holes'

def stl(mesh,path,R=None):
    R=R or Matrix.Identity(4)
    pts=[R@v.co for v in mesh.vertices]
    # Put each part independently on the plate, centred in X/Y, in raw mm.
    mid=Vector(((min(v.x for v in pts)+max(v.x for v in pts))/2,(min(v.y for v in pts)+max(v.y for v in pts))/2,min(v.z for v in pts)))
    pts=[v-mid for v in pts]
    # Raw STL uses float32. After rotating/recentring, originally distinct
    # sub-micron Boolean vertices can round onto exactly the same coordinate.
    # Weld the TRANSFORMED export mesh, not the source assembly mesh.
    tmp=bpy.data.meshes.new('REVB_EXPORT_ROUNDING_REPAIR')
    tmp.from_pydata(pts,[],[list(p.vertices) for p in mesh.polygons]);tmp.update()
    bm=bmesh.new();bm.from_mesh(tmp)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.0000001)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(tmp);bm.free()
    tmp.validate();tmp.update();tmp.calc_loop_triangles()
    pts=[v.co for v in tmp.vertices]
    with path.open('wb') as f:
        f.write(b'CyberArm RevB FIT REVIEW; units=mm'.ljust(80,b' '));f.write(struct.pack('<I',len(tmp.loop_triangles)))
        for tri in tmp.loop_triangles:
            a,b,c=[pts[k] for k in tri.vertices];n=(b-a).cross(c-a).normalized()
            f.write(struct.pack('<12fH',*n,*a,*b,*c,0))
    bounds=[max(v[k] for v in pts)-min(v[k] for v in pts) for k in range(3)]
    bpy.data.meshes.remove(tmp)
    return bounds

def export_parts():
    folder=OUT/'STL_FIT_REVIEW_mm';folder.mkdir(exist_ok=True)
    groups={}
    for o in parts():
        stem=Path(o.get('source_file','')).stem
        groups.setdefault(stem,[]).append(o)
    rows=[]
    for stem,objs in groups.items():
        o=objs[0];s=stats(o)
        if s['nonmanifold_edges']:raise RuntimeError('Cannot export open mesh: '+o.name)
        if stem in ('Arm_01','Arm_02_v3'):R=Matrix.Identity(4)
        elif stem in ('Gripper_1','Gripper_1_1'):R=Matrix.Rotation(-math.pi/2,4,'Y')
        else:R=Matrix.Rotation(math.pi/2,4,'X')
        path=folder/(stem+'_RevB_mm.stl');bounds=stl(o.data,path,R)
        o['geometry_policy']='RevB: see revision_report.json; preserve original source elsewhere'
        rows.append({'source_stem':stem,'object':o.name,'quantity':len(objs),'file':str(path),'bounds_mm':bounds,'check':s,'fit_release':False})
    (OUT/'print_manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    return rows

def coupons():
    col=bpy.data.collections.get('REVB_07_Fit_coupons_NOT_ASSEMBLY')
    if not col:col=bpy.data.collections.new('REVB_07_Fit_coupons_NOT_ASSEMBLY');bpy.context.scene.collection.children.link(col)
    folder=OUT/'PRINT_FIRST_horn_tests_mm';folder.mkdir(exist_ok=True);rows=[]
    rules=[('01_MG996R_14mm',(26,24,4),(0,0,2),[(0,0,3.75),(-7,0,1.5),(7,0,1.5)]),
           ('02_MG90S_double_12mm',(42,14,3),(0,0,1.5),[(0,0,2.5),(-6,0,1.3),(6,0,1.3)]),
           ('03_MG90S_cross_10p2mm',(42,26,3),(0,0,1.5),[(0,0,2.5),(0,-5.1,1.3),(0,5.1,1.3)]),
           ('04_MG90S_single_r6_r11',(30,14,4),(9,0,2),[(0,0,2.4),(6,0,1.1),(11,0,1.1)])]
    for name,size,c,holes in rules:
        on='FIT_'+name;o=bpy.data.objects.get(on)
        if not o:
            bpy.ops.mesh.primitive_cube_add(size=1);o=bpy.context.object;o.name=on;o.scale=size
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
            for v in o.data.vertices:v.co+=Vector(c)
            for x,y,r in holes:cylinder(o,(x,y,2),r,15,(0,0,1),'DIFFERENCE')
            for old in list(o.users_collection):old.objects.unlink(o)
            col.objects.link(o)
        path=folder/(name+'.stl');bounds=stl(o.data,path)
        rows.append({'file':str(path),'bounds_mm':bounds,'holes_x_y_radius_mm':holes,'check':stats(o)})
    col.hide_render=True;col.hide_viewport=True
    (OUT/'fit_coupon_manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    return rows
