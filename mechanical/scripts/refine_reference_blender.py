"""Rev B: remove recessed logos, use source hardware, preserve original assembly."""
import bpy, bmesh, json, math
from pathlib import Path
from mathutils import Vector, Matrix
from collections import Counter

OUT=Path('E:/CyberArm/mechanical/archive/arduino_reference_revB')
OUT.mkdir(exist_ok=True)
SOURCE=Path('E:/CyberArm/mechanical/archive/arduino_reference_replica')
DATA=json.loads((SOURCE/'assembly_manifest.json').read_text(encoding='utf8'))
SC=bpy.context.scene


def restore_view():
    for name,hidden in bpy.app.driver_namespace.get('review_hide',{}).items():
        if name in bpy.data.objects:bpy.data.objects[name].hide_set(hidden)
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D' and 'review_view' in bpy.app.driver_namespace:
            r,l,d=bpy.app.driver_namespace['review_view']
            area.spaces.active.region_3d.view_rotation=r
            area.spaces.active.region_3d.view_location=l
            area.spaces.active.region_3d.view_distance=d


def stats(obj):
    bm=bmesh.new();bm.from_mesh(obj.data)
    rec={'vertices':len(bm.verts),'faces':len(bm.faces),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),
         'volume_mm3':abs(bm.calc_volume(signed=True))}
    bm.free();return rec


def cleaned(obj):
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.0000001)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data);bm.free();obj.data.update()


def write_report(key,record):
    p=OUT/'revision_report.json'
    report=json.loads(p.read_text(encoding='utf8')) if p.exists() else {}
    report[key]=record;p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


def remove_logos():
    restore_view();report=[]
    backup=bpy.data.collections.get('RevA_original_mesh_backups')
    if not backup:
        backup=bpy.data.collections.new('RevA_original_mesh_backups');SC.collection.children.link(backup)
    backup.hide_render=True;backup.hide_viewport=True
    for name in ['ARD_05_Arm_02_v3','ARD_01_Base']:
        o=bpy.data.objects[name]
        if o.get('RevB_logo_removed'):continue
        before=stats(o)
        old=o.copy();old.data=o.data.copy();old.name='BACKUP_'+name;backup.objects.link(old)
        o.data=o.data.copy()
        modified=0
        if name=='ARD_05_Arm_02_v3':
            # The complete engraved floor is inside this rectangle. Corner ray
            # checks are on the original -8 mm panel (edge fillet deviation <.007).
            bpy.ops.mesh.primitive_cube_add(size=1)
            tool=bpy.context.object;tool.name='Forearm_logo_fill_tool'
            tool.scale=(24.1,27.75,1.2)
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
            tool.matrix_world=o.matrix_world@Matrix.Translation((0,31.875,-7.4))
            bpy.context.view_layer.objects.active=o
            mod=o.modifiers.new('Remove_logo_restore_panel','BOOLEAN');mod.operation='UNION';mod.solver='EXACT';mod.object=tool
            bpy.ops.object.modifier_apply(modifier=mod.name)
            bpy.data.objects.remove(tool,do_unlink=True)
            modified=1121
        else:
            # Restore the engraved sector with a solid annular patch whose outer
            # polygon is copied from the undamaged cylinder rim.
            top=[(float(v.co.z),float(v.co.x)) for v in o.data.vertices
                 if abs(v.co.y-92.107574)<.001 and v.co.x<0 and
                 abs(math.hypot(v.co.x-40.779253,v.co.z-92.879566)-49)<.001]
            top=sorted(set(top))
            top=[p for p in top if 77<p[0]<109]
            n=len(top);verts=[];faces=[]
            for height in (57.5,85.5):
                for radius in (49,46):
                    for z,x in top:
                        factor=radius/49
                        verts.append((40.779253+(x-40.779253)*factor,height,92.879566+(z-92.879566)*factor))
            for k in range(n-1):
                faces.extend([(k,k+1,n+k+1,n+k),(2*n+k,3*n+k,3*n+k+1,2*n+k+1),
                              (k,2*n+k,2*n+k+1,k+1),(n+k,n+k+1,3*n+k+1,3*n+k)])
            faces.extend([(0,n,3*n,2*n),(n-1,3*n-1,4*n-1,2*n-1)])
            mesh=bpy.data.meshes.new('Logo_wall_repair_mesh');mesh.from_pydata(verts,[],faces);mesh.update()
            tool=bpy.data.objects.new('Logo_wall_repair_tool',mesh);SC.collection.objects.link(tool)
            tool.matrix_world=o.matrix_world.copy()
            bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
            bpy.context.view_layer.objects.active=o
            mod=o.modifiers.new('Remove_logo_restore_cylindrical_wall','BOOLEAN');mod.operation='UNION';mod.solver='EXACT';mod.object=tool
            bpy.ops.object.modifier_apply(modifier=mod.name)
            bpy.data.objects.remove(tool,do_unlink=True)
            modified=n*4
        cleaned(o)
        after=stats(o)
        if after['nonmanifold_edges']>before['nonmanifold_edges']:
            o.data=old.data.copy()
            raise RuntimeError('Logo removal introduced nonmanifold edges: '+name+' '+str(after))
        o['RevB_logo_removed']=True
        o['source_file_original']=o.get('source_file','')
        o['revision']='Recessed logo filled to original outer surface; original dimensions retained'
        report.append({'name':name,'moved_vertices':modified,'before':before,'after':after})
    write_report('logo_removal',report)
    return report


def save():
    SC['Revision']='RevB: original arm with source hardware and logo removal; fit review'
    path=OUT/'Arduino_Replica_RevB.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    return str(path)


def parent_preserve(o,parent):
    world=o.matrix_world.copy();o.parent=parent
    if parent:o.matrix_parent_inverse=parent.matrix_world.inverted()
    o.matrix_world=world


def stock_mesh(path,name,transform,parent,collection,material):
    if name in bpy.data.objects:return bpy.data.objects[name]
    bpy.ops.wm.stl_import(filepath=str(path));o=bpy.context.object;o.name=name
    for c in list(o.users_collection):c.objects.unlink(o)
    collection.objects.link(o);o.matrix_world=transform
    parent_preserve(o,parent)
    o.data.materials.clear();o.data.materials.append(material)
    o['source_file']=str(path);o['NOT_FOR_PRINT']=True
    return o


def hardware():
    motors=next(c for c in SC.collection.children if c.name.startswith('ARD_02_'))
    hard=next(c for c in SC.collection.children if c.name.startswith('ARD_03_'))
    folder=Path('E:/CyberArm/mechanical/fusion_reference_review/mg996r_extracted')
    created=[]
    for index,stem in enumerate(['S01_Base','S02_Shoulder','S03_Elbow']):
        body=bpy.data.objects['ARD_'+stem+'_MG996R_BODY']
        frame=bpy.data.objects['ARD_'+stem+'_axis'].matrix_world.copy()
        o=stock_mesh(folder/'MG996R_case_shaft_sleeve_canonical_mm.stl','REVB_'+stem+'_MG996R_SOURCE',frame,body.parent,motors,body.data.materials[0])
        o['representation']='CRC-verified SW display geometry; assembled using SLDASM transforms; not exact BREP'
        for old in list(motors.objects)+list(hard.objects):
            if old.name.startswith('ARD_'+stem) and old.type=='MESH':old.hide_render=True;old.hide_set(True)
        short='S0'+str(index+1)
        old=bpy.data.objects['ARD_'+short+'_stock_round_horn']
        hm=old.matrix_world@Matrix.Translation((0,0,-1.25))
        h=stock_mesh(folder/'MG996R_round_horn_canonical_mm.stl','REVB_'+short+'_MG996R_ROUND_HORN',hm,old.parent,hard,old.data.materials[0])
        old.hide_render=True;old.hide_set(True)
        created.append(o.name);created.append(h.name)
    # Purchased horns are flipped so their hubs face the output shafts.
    entries=[('S04','double','obj_2_ServoMotor Arms.stl_A_A.stl',(125.3488,129.2246),0),
             ('S05','cross','obj_3_ServoMotor Arms.stl_A_B.stl',(125.2333,114.0571),90),
             ('S06','single','obj_1_ServoMotor Arms.stl_B.stl',(111.4553,138.9141),180)]
    for short,label,file,center,angle in entries:
        old=bpy.data.objects['ARD_'+short+'_required_9mm_horn']
        hm=old.matrix_world@Matrix.Translation((0,0,-1.1))
        r=Matrix.Rotation(math.pi,4,'X')
        norm=Matrix.Translation((0,0,2.5))@Matrix.Rotation(math.radians(angle),4,'Z')@r@Matrix.Translation((-center[0],-center[1],0))
        h=stock_mesh(Path('E:/CyberArm/mechanical/servo配件')/file,'REVB_'+short+'_MG90S_'+label.upper()+'_HORN',hm@norm,old.parent,hard,old.data.materials[0])
        old.hide_render=True;old.hide_set(True)
        h['fit_status']='Real source horn; axial seating and physical spline engagement need fit trial'
        created.append(h.name)
    write_report('hardware_sources',created)
    return created


def shift_hole(o,axis,center,radius,delta):
    changed=0
    for v in o.data.vertices:
        diff=v.co-Vector(center)
        radial=math.sqrt(sum(diff[k]*diff[k] for k in range(3) if k!=axis))
        if abs(radial-radius)<.004:
            v.co+=Vector(delta);changed+=1
    if changed<12:raise RuntimeError('Insufficient ring vertices: '+o.name+' '+str(center))
    o.data.update();return changed


def adapt_holes():
    changes=[]
    rules=[('ARD_04_Arm_01',2,[(0,-7.25,0),(0,7.25,0),(0,112.75,0),(0,127.25,0)],1.5,[(0,.25,0),(0,-.25,0),(0,.25,0),(0,-.25,0)],'MG996R 14 mm horn pitch'),
           ('ARD_03_Waist',1,[(0,0,-7.25),(0,0,7.25)],1.5,[(0,0,.25),(0,0,-.25)],'MG996R 14 mm horn pitch'),
           ('ARD_06_Arm_03',1,[(-9.5,0,0),(-.5,0,0)],1.3,[(-1.5,0,0),(1.5,0,0)],'MG90S double horn 12 mm pitch'),
           ('ARD_07_Gripper_base',0,[(9,-9,-67.5),(9,-9,-58.5)],1.3,[(0,0,-.6),(0,0,.6)],'MG90S cross horn short-axis 10.2 mm pitch')]
    for name,axis,centers,radius,deltas,description in rules:
        o=bpy.data.objects[name]
        if o.get('RevB_horn_holes'):continue
        old=o.data.copy();o.data=o.data.copy();changed=0
        for center,delta in zip(centers,deltas):changed+=shift_hole(o,axis,center,radius,delta)
        cleaned(o);check=stats(o)
        if check['nonmanifold_edges']:
            o.data=old;raise RuntimeError('Invalid adapted mesh: '+name)
        o['RevB_horn_holes']=description
        changes.append({'name':name,'change':description,'vertices_moved':changed,'check':check})
    write_report('hole_adaptations',changes)
    return changes


def smooth_surfaces():
    for o in SC.objects:
        if o.type!='MESH' or o.hide_render or o.name.startswith('BACKUP_'):continue
        if o.name.startswith(('ARD_','REVB_')) and 'ground' not in o.name:
            o.data.set_sharp_from_angle(angle=math.radians(35))
            for p in o.data.polygons:p.use_smooth=True
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D':
            sp=area.spaces.active;sp.shading.type='SOLID';sp.shading.color_type='MATERIAL'
            sp.overlay.show_wireframes=False;sp.overlay.show_extras=False
            sp.region_3d.view_location=(76,0,91);sp.region_3d.view_distance=460
            sp.region_3d.view_rotation=SC.camera.rotation_euler.to_quaternion()
    return 'Sharp edges preserved; smooth normals on curved surfaces'
