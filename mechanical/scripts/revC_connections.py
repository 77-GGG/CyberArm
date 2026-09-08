"""RevC explicit horn fastenings. Purchased hardware, no printed screw threads.
M2 through-bolts/nuts need two stock horn holes drilled to 2.2 mm.
Preserves the supplied horns and RevB file as unmachined references.
"""
import bpy,bmesh,math,json,struct
from pathlib import Path
from mathutils import Matrix,Vector
OUT=Path('E:/CyberArm/mechanical/arduino_reference_revC');OUT.mkdir(exist_ok=True)
helpers={}
exec(compile(Path('E:/CyberArm/mechanical/scripts/revB_fit_and_export.py').read_text(encoding='utf8'),'revB_helpers','exec'),helpers,helpers)
stats=helpers['stats'];clean=helpers['cleaned'];stl=helpers['stl']
SC=bpy.context.scene

# Local interface Z points from the horn toward the printed component / bolt head.
ENTRIES=[
 dict(id='S01',label='Base yaw',part='ARD_03_Waist',horn='REVB_S01_MG996R_ROUND_HORN',hub=(0,0,0),u=(0,0,1),n=(0,1,0),holes=[-7,7],t=4,gap=.5,ht=2.3,cb=0,L=10,oldr=1.5,access=7.5),
 dict(id='S02',label='Shoulder',part='ARD_04_Arm_01',horn='REVB_S02_MG996R_ROUND_HORN',hub=(0,0,0),u=(0,1,0),n=(0,0,1),holes=[-7,7],t=6,gap=.2,ht=2.3,cb=1,L=10,oldr=1.5,access=7.5),
 dict(id='S03',label='Elbow',part='ARD_04_Arm_01',horn='REVB_S03_MG996R_ROUND_HORN',hub=(0,120,0),u=(0,1,0),n=(0,0,1),holes=[-7,7],t=6,gap=.2,ht=2.3,cb=1,L=10,oldr=1.5,access=7.5),
 dict(id='S04',label='Wrist roll',part='ARD_06_Arm_03',horn='REVB_S04_MG90S_DOUBLE_HORN',hub=(-5,0,0),u=(1,0,0),n=(0,1,0),holes=[-6,6],t=5,gap=0,ht=2.5,cb=0,L=10,oldr=1.3,access=5),
 dict(id='S05',label='Wrist pitch',part='ARD_07_Gripper_base',horn='REVB_S05_MG90S_CROSS_HORN',hub=(9,-9,-63),u=(0,1,0),n=(1,0,0),holes=[-6,6],t=5,gap=0,ht=2.5,cb=0,L=10,oldr=1.3,access=5),
 dict(id='S06',label='Gripper gear',part='ARD_08_gear2',horn='REVB_S06_MG90S_SINGLE_HORN',hub=(-10.10634,0,0),u=(-1,0,0),n=(0,1,0),holes=[6,11],t=4,gap=0,ht=2.5,cb=1,L=8,oldr=1.1,access=4.8),
]

def col(name):
    c=bpy.data.collections.get(name)
    if not c:c=bpy.data.collections.new(name);SC.collection.children.link(c)
    return c

def frame(e):
    u=Vector(e['u']);n=Vector(e['n']);v=n.cross(u)
    R=Matrix((u,v,n)).transposed().to_4x4();R.translation=e['hub']
    return bpy.data.objects[e['part']].matrix_world@R

def preserve(o,p):
    bpy.context.view_layer.update();M=o.matrix_world.copy();o.parent=p;o.matrix_parent_inverse=p.matrix_world.inverted();o.matrix_world=M
    bpy.context.view_layer.update()

def material(name,color,metal=0):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Metallic'].default_value=metal;bs.inputs['Roughness'].default_value=.27
    return m

def move(o,collection):
    for c in list(o.users_collection):c.objects.unlink(o)
    collection.objects.link(o)

def boolean(o,tool,operation,strict=True):
    bpy.context.view_layer.objects.active=o
    m=o.modifiers.new('RevC_'+operation,'BOOLEAN');m.operation=operation;m.solver='MANIFOLD' if strict else 'EXACT';m.object=tool
    bpy.ops.object.modifier_apply(modifier=m.name);data=tool.data;bpy.data.objects.remove(tool,do_unlink=True)
    if data.users==0:bpy.data.meshes.remove(data)
    # Keep the exact Boolean topology; blind proximity welding can collapse
    # narrow but valid fan triangles on the downloaded tessellation.
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-10)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=1e-11)
    # Exact solver occasionally omits a single planar quad on a pad, even for a
    # spatially disjoint later cut. Repair ONLY closed, planar, sub-1 mm loops.
    # Intentional through holes have side walls and do not have boundary edges.
    remaining={e for e in bm.edges if e.is_boundary};repaired=[]
    while remaining:
        stack=[remaining.pop()];edges=[];verts=set()
        while stack:
            edge=stack.pop();edges.append(edge);verts.update(edge.verts)
            for v in edge.verts:
                for nei in v.link_edges:
                    if nei in remaining:remaining.remove(nei);stack.append(nei)
        vv=list(verts);diam=max((a.co-b.co).length for a in vv for b in vv)
        normal=Vector()
        for a in vv[1:]:
            for b in vv[2:]:
                trial=(a.co-vv[0].co).cross(b.co-vv[0].co)
                if trial.length>normal.length:normal=trial
        planar=normal.length>1e-10 and max(abs((v.co-vv[0].co).dot(normal.normalized())) for v in vv)<1e-5
        closed=all(sum(e in edges for e in v.link_edges)==2 for v in vv)
        if closed and planar and diam<1 and len(edges)<=8:
            bmesh.ops.holes_fill(bm,edges=edges,sides=8);repaired.append(diam)
    if repaired:o['RevC_planar_boolean_patch_max_mm']=max(repaired)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
    if strict and stats(o)['nonmanifold_edges']:
        bm=bmesh.new();bm.from_mesh(o.data)
        bad=[e for e in bm.edges if not e.is_manifold]
        details=[{'faces':len(e.link_faces),'ends':[list(v.co) for v in e.verts]} for e in bad]
        bm.free()
        raise RuntimeError('Invalid print mesh '+o.name+' '+operation+' '+str(stats(o))+' edges='+str(details))

def cyl_tool(o,F,xy,r,z0,z1,op='DIFFERENCE',strict=True,vertices=96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=z1-z0)
    tool=bpy.context.object
    # All interface frames are signed permutations of the part axes. Bake the
    # cutter in the same local frame, avoiding world-parent float roundoff at
    # planar mating faces (which can drop a coplanar pad side in a Boolean).
    T=o.matrix_world.inverted()@F@Matrix.Translation((xy[0],xy[1],(z0+z1)/2))
    T=Matrix([[round(v,5) for v in row] for row in T])
    tool.data.transform(T);tool.matrix_world=o.matrix_world.copy()
    boolean(o,tool,op,strict)

def fill_holes(o,axis,centers,radius):
    bm=bmesh.new();bm.from_mesh(o.data)
    for center in centers:
        walls=[f for f in bm.faces if all(abs(math.sqrt(sum((v.co[k]-center[k])**2 for k in range(3) if k!=axis))-radius)<.004 for v in f.verts)]
        if len(walls)<12:raise RuntimeError('Missing old walls '+o.name)
        bmesh.ops.delete(bm,geom=walls,context='FACES_ONLY')
    bmesh.ops.delete(bm,geom=[e for e in bm.edges if not e.link_faces],context='EDGES')
    res=bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=0)
    bmesh.ops.triangulate(bm,faces=res['faces']);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
    clean(o)

def resize_ring(o,center,n,old,new):
    n=Vector(n);center=Vector(center);count=0
    for v in o.data.vertices:
        q=v.co-center;rad=q-n*q.dot(n)
        if abs(rad.length-old)<.004:
            v.co+=rad*(new/old-1);count+=1
    if count<24:raise RuntimeError('Ring not found '+o.name+str(center))
    clean(o);return count

def print_interfaces():
    records=[]
    for e in ENTRIES:
        o=bpy.data.objects[e['part']];key='RevC_'+e['id']+'_holes'
        if o.get(key):continue
        backup=o.data.copy();o.data=o.data.copy();before=stats(o);F=frame(e)
        try:
            if e['id']=='S05':
                # A standard M2 nut AF4 cannot fit beside the 6.9 mm hub at r5.1.
                # Use the cross horn LONG-arm pair r6 instead; fill old short pair.
                fill_holes(o,0,[(9,-9,-68.1),(9,-9,-57.9)],1.3)
            else:
                axis=max(range(3),key=lambda k:abs(e['n'][k]))
                centers=[Vector(e['hub'])+Vector(e['u'])*x for x in e['holes']]
                fill_holes(o,axis,centers,e['oldr'])
            # Integral compression pads fill the CAD's prior air gaps.
            if e['gap']:
                for x in e['holes']:
                    cyl_tool(o,F,(x,0),2.5,-e['gap'],.15,'UNION')
            for x in e['holes']:cyl_tool(o,F,(x,0),1.2,-e['gap']-1,e['t']+1)
            if e['cb']:
                for x in e['holes']:cyl_tool(o,F,(x,0),2.4,e['t']-e['cb'],e['t']+.5)
            # This is a driver / OEM screw access opening, not an M2 nut trap.
            cyl_tool(o,F,(0,0),(e['access']+.2)/2,-e['gap']-1,e['t']+1)
            if stats(o)['nonmanifold_edges']:raise RuntimeError('Invalid final interface')
        except Exception:
            o.data=backup;raise
        o[key]=True;o['RevC_connection']='M2 through hole dia2.4; see connection_manifest.json for counterbore and stack'
        records.append({'id':e['id'],'part':o.name,'before':before,'after':stats(o)})
    (OUT/'print_interface_changes.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    return records

def machined_horns():
    collection=col('REVC_08_Machined_stock_horns_NOT_FOR_PRINT');records=[]
    for e in ENTRIES:
        name='REVC_'+e['id']+'_HORN_DRILL_2p2'
        if name in bpy.data.objects:continue
        source=bpy.data.objects[e['horn']];o=source.copy();o.data=source.data.copy();o.name=name;collection.objects.link(o)
        o.hide_render=False;o.hide_set(False);F=frame(e)
        # The display mesh is not watertight; enlarge measured circular boundary
        # vertices instead of an unreliable solid Boolean on the source hardware.
        Ti=F.inverted()@o.matrix_world;back=Ti.inverted();count=0;old=.75 if e['id']<'S04' else .9
        for x in e['holes']:
            for v in o.data.vertices:
                q=Ti@v.co;d=math.hypot(q.x-x,q.y)
                if abs(d-old)<.015 and -e['gap']-e['ht']-.02<=q.z<=-e['gap']+.02:
                    q.x=x+(q.x-x)*1.1/d;q.y*=1.1/d;v.co=back@q;count+=1
        if count<40:raise RuntimeError('Not enough source hole vertices '+name+' '+str(count))
        o.data.update();o['NOT_FOR_PRINT']=True;o['physical_operation']='Drill ONLY the two chosen holes to 2.2 mm off-servo, deburr both faces; do not modify spline or centre hole'
        o['source_unmodified_object']=source.name;source.hide_render=True;source.hide_set(True)
        records.append({'id':e['id'],'object':name,'hole_vertices_adjusted':count,'hole_diameter_mm':2.2,'requires_physical_drilling':True})
    (OUT/'horn_machining.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    return records

def clear_fixed_supports():
    """Real clearance cuts for nuts/bolt ends in the FIXED adjacent supports.

    Wrist openings were already radius 7.5; enlarge just the lip to 8.7.
    Do not leave a 0.2 mm membrane by making a shallow nut pocket. The
    gripper only uses +/-8 degree preview travel: two localized +/-10 degree
    swept slots preserve the rest of its mounting plate.
    """
    rows=[]
    for e in ENTRIES[3:]:
        target={'S04':'ARD_05_Arm_02_v3','S05':'ARD_06_Arm_03','S06':'ARD_07_Gripper_base'}[e['id']]
        o=bpy.data.objects[target];key='RevC_'+e['id']+'_fixed_clearance'
        if o.get(key):continue
        F=frame(e);before=stats(o);backup=o.data.copy();o.data=o.data.copy()
        try:
            if e['id'] in ['S04','S05']:
                cyl_tool(o,F,(0,0),8.7,-6.0,-2.3)
                spec={'opening_diameter_mm':17.4,'z_range_mm':[-6,-2.3],'angular_clearance':'360 degree nut sweep ONLY; not whole-joint collision clearance'}
            else:
                for x in e['holes']:
                    for deg in range(-10,11,2):
                        a=math.radians(deg);cyl_tool(o,F,(x*math.cos(a),x*math.sin(a)),2.6,-5.3,-2.3)
                spec={'swept_hole_radii_mm':e['holes'],'tool_diameter_mm':5.2,'z_range_mm':[-5.3,-2.3],'sweep_degrees':[-10,10],'sample_step_degrees':2,'operating_preview_limit_degrees':[-8,8]}
        except Exception:
            o.data=backup;raise
        o[key]=True;o['RevC_nut_clearance']='See fixed_support_clearance.json; front lip/slots are real mesh cuts, not a cosmetic cover'
        rows.append({'id':e['id'],'modified_fixed_support':target,'before':before,'after':stats(o),'cut':spec})
    (OUT/'fixed_support_clearance.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    return rows

def ring_mesh(name,outer,inner,z0,z1,sides=96,hex_outer=False):
    vs=[];fs=[]
    for z in [z0,z1]:
        for outside in [True,False]:
            for i in range(sides):
                a=2*math.pi*i/sides
                r=outer/math.cos((a+math.pi/6)%(math.pi/3)-math.pi/6) if outside and hex_outer else (outer if outside else inner)
                vs.append((r*math.cos(a),r*math.sin(a),z))
    n=sides
    for i in range(n):
        j=(i+1)%n
        fs.extend([(i,j,2*n+j,2*n+i),(n+i,3*n+i,3*n+j,n+j),(i,n+i,n+j,j),(2*n+i,2*n+j,3*n+j,3*n+i)])
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vs,[],fs);mesh.update()
    return mesh

def screw_mesh(name,L=10,d=2,pitch=.4,hd=3.8,hh=2,drive='HEX'):
    # Nominal helical ridge for visual clarity, not a manufacturing-thread model.
    n=48;nz=math.ceil(L/pitch*12);vs=[];fs=[];minor=d/2-.27*pitch/.4
    for j in range(nz+1):
        z=-L+j*L/nz;taper=min(1,(z+L+.05)/.25)
        for i in range(n):
            a=2*math.pi*i/n;phase=(z/pitch-a/(2*math.pi))%1
            r=(minor+(d/2-minor)*max(0,1-abs(phase-.5)/.42))*taper
            vs.append((r*math.cos(a),r*math.sin(a),z))
    for j in range(nz):
        for i in range(n):
            k=(i+1)%n;fs.append((j*n+i,j*n+k,(j+1)*n+k,(j+1)*n+i))
    fs.extend([tuple(reversed(range(n))),tuple(nz*n+i for i in range(n))])
    mesh=bpy.data.meshes.new(name+'_thread');mesh.from_pydata(vs,[],fs);mesh.update()
    thread=bpy.data.objects.new(name+'_thread',mesh);SC.collection.objects.link(thread)
    bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=hd/2,depth=hh)
    head=bpy.context.object;head.location.z=hh/2
    bpy.ops.object.transform_apply(location=True,rotation=False,scale=False)
    if drive=='HEX':cyl_tool(head,Matrix.Identity(4),(0,0),1.5/math.sqrt(3),hh-1,hh+1,vertices=6)
    else:
        for dims in [(hd*.65,.6,1.1),(.6,hd*.65,1.1)]:
            bpy.ops.mesh.primitive_cube_add(size=1);tool=bpy.context.object;tool.scale=dims;tool.location.z=hh-.15
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);boolean(head,tool,'DIFFERENCE')
    for o in bpy.context.selected_objects:o.select_set(False)
    thread.select_set(True);head.select_set(True);bpy.context.view_layer.objects.active=head;bpy.ops.object.join()
    data=head.data;data.name=name+'_mesh';data.use_fake_user=True;bpy.data.objects.remove(head,do_unlink=True)
    return data

def instance(name,mesh,F,parent,mat,collection,category):
    if name in bpy.data.objects:return bpy.data.objects[name]
    o=bpy.data.objects.new(name,mesh);collection.objects.link(o);o.matrix_world=F
    if parent:preserve(o,parent)
    o.data.materials.clear();o.data.materials.append(mat);o['NOT_FOR_PRINT']=True;o['connection_role']=category
    return o

def hardware():
    collection=col('REVC_09_Fasteners_NOT_FOR_PRINT');steel=material('REVC_M2_steel',(.26,.36,.43),.8)
    brass=material('REVC_Nut_brass',(.55,.29,.06),.7);washermat=material('REVC_Washer_steel',(.55,.59,.65),.8)
    screws={L:screw_mesh('REVC_M2x'+str(L),L) for L in [8,10]}
    washer=ring_mesh('REVC_DIN433_M2',2.25,1.1,0,.3)
    nut=ring_mesh('REVC_M2_AF4_h1p6',2,1,-1.6,0,hex_outer=True)
    records=[]
    for e in ENTRIES:
        F=frame(e);parent=bpy.data.objects[e['part']];screw_z=e['t']-e['cb']+.3;nut_z=-e['gap']-e['ht']
        for j,x in enumerate(e['holes'],1):
            base='REVC_'+e['id']+'_T'+str(j)
            bolt=instance(base+'_M2x'+str(e['L']),screws[e['L']],F@Matrix.Translation((x,0,screw_z)),parent,steel,collection,'Transmission bolt: through printed clearance hole and drilled horn, threads only into M2 nut')
            instance(base+'_WASHER',washer,F@Matrix.Translation((x,0,e['t']-e['cb'])),parent,washermat,collection,'M2 small washer ID2.2 OD4.5 thickness0.3')
            instance(base+'_NUT_M2',nut,F@Matrix.Translation((x,0,nut_z)),parent,brass,collection,'M2 nut AF4 height1.6; internal thread represented by nominal bore')
            bolt['thread']='M2x0.4 nominal visual helix';bolt['head']='ISO4762/DIN912 nominal: diameter3.8 height2 hex1.5'
        for o in SC.objects:
            if o.name.startswith('ARD_'+e['id']+'_horn_screw') or o.name=='ARD_'+e['id']+'_center_screw':o.hide_render=True;o.hide_set(True)
        records.append(dict(e,frame_world=[list(r) for r in F],print_hole_diameter=2.4,horn_drill_diameter=2.2,centre_access_diameter=e['access']+.2,counterbore_diameter=4.8 if e['cb'] else None,
            washer=dict(id=2.2,od=4.5,t=.3),nut=dict(thread='M2x0.4',AF=4,height=1.6),
            bolt_underhead_z=screw_z,bolt_tip_z=screw_z-e['L'],nut_front_z=nut_z,nut_back_z=nut_z-1.6,tip_protrusion_mm=nut_z-1.6-(screw_z-e['L'])))
    (OUT/'connection_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    return records

def centre_screws():
    collection=col('REVC_09_Fasteners_NOT_FOR_PRINT');mat=material('REVC_OEM_centre_screw',(.18,.19,.21),.7)
    pending=material('REVC_MG90S_OEM_CHECK',(.8,.26,.015),.45)
    p=Path('E:/CyberArm/mechanical/fusion_reference_review/mg996r_extracted/Pan Head Cross Screw M3_display_mm.stl')
    bpy.ops.wm.stl_import(filepath=str(p));tmp=bpy.context.object
    radial=[v for v in tmp.data.vertices if math.hypot(v.co.y,v.co.z)>2]
    under_x=max(v.co.x for v in radial)
    hh=under_x-min(v.co.x for v in tmp.data.vertices);length=max(v.co.x for v in tmp.data.vertices)-under_x
    # Source tip X=0, under-head X=-6, crown at negative X. Outward is -X.
    for v in tmp.data.vertices:
        x,y,z=v.co;v.co=(y,-z,under_x-x)
    mesh=tmp.data;mesh.use_fake_user=True;bpy.data.objects.remove(tmp,do_unlink=True)
    mini=screw_mesh('REVC_MG90S_OEM_M2x5_ENVELOPE',5,2,.4,3.5,1.6,'CROSS')
    records=[]
    for e in ENTRIES:
        large=e['id']<'S04';F=frame(e)@Matrix.Translation((0,0,-e['gap']))
        o=instance('REVC_'+e['id']+'_CENTRE_OEM_LOCK',mesh if large else mini,F,bpy.data.objects[e['part']],mat if large else pending,collection,
                   'OEM centre retaining screw into servo output shaft; does NOT fasten printed component')
        o['fit_status']='M3 source screw geometry; verify against physical OEM screw' if large else 'M2x5 ENVELOPE ONLY; physical OEM thread/length UNCONFIRMED, use supplied screw'
        records.append({'id':e['id'],'object':o.name,'nominal':f'M3 source head-under length {length:.4f}' if large else 'M2x5 envelope, NOT a purchase specification',
                        'source_head_height_mm':hh if large else 1.6,'print_driver_access_diameter_mm':e['access']+.2,'physical_confirmation_required':True})
    (OUT/'centre_screw_manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    return records

def save():
    SC['Revision']='RevC explicit M2 transmission bolts/nuts, OEM centre locks and real printed holes; FIT REVIEW'
    for o in SC.objects:
        if o.type=='MESH' and not o.hide_render:
            o.data.set_sharp_from_angle(angle=math.radians(35))
            for p in o.data.polygons:p.use_smooth=True
    path=OUT/'Arduino_Replica_RevC_Connections.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path));return str(path)
