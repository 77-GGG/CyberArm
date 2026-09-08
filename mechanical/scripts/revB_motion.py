"""Native Blender property drivers: five axes and closed gripper four-bars.
No Python driver namespace, handlers, or auto-run script required on reopening.
Motion is kinematic, not motor dynamics / contact simulation.
"""
import bpy, math, json
from pathlib import Path
from mathutils import Matrix, Vector
OUT=Path('E:/CyberArm/mechanical/archive/arduino_reference_revB')

def preserve(o,parent):
    bpy.context.view_layer.update();world=o.matrix_world.copy()
    o.parent=parent;o.matrix_parent_inverse=parent.matrix_world.inverted();o.matrix_world=world
    bpy.context.view_layer.update()

def drv(o,path,index,expression,variables):
    f=o.driver_add(path) if index is None else o.driver_add(path,index)
    d=f.driver;d.type='SCRIPTED';d.expression=expression
    for name,target,prop in variables:
        v=d.variables.new();v.name=name;v.type='SINGLE_PROP';v.targets[0].id=target;v.targets[0].data_path='["'+prop+'"]'

def prop(o,key,value,low=None,high=None,description=''):
    o[key]=value
    if low is not None:o.id_properties_ui(key).update(min=low,max=high,soft_min=low,soft_max=high,description=description)

def empty(name,parent,col):
    o=bpy.data.objects.new(name,None);col.objects.link(o);o.parent=parent
    o.empty_display_type='PLAIN_AXES';o.empty_display_size=5
    return o

def build():
    if 'ARM_CONTROLS' in bpy.data.objects:return 'Controls already exist'
    sc=bpy.context.scene
    col=bpy.data.collections.new('REVB_06_Motion');sc.collection.children.link(col)
    ctrl=empty('ARM_CONTROLS',None,col);ctrl.location=(-95,0,70)
    ctrl.empty_display_type='CUBE';ctrl.empty_display_size=10;ctrl.show_in_front=True
    ctrl['Instructions']='Object Properties > Custom Properties. Angles are offsets from saved pose, NOT calibrated servo PWM. Demo ranges only, not verified safe limits.'
    keys=['01_Base_deg','02_Shoulder_deg','03_Elbow_deg','04_Wrist_roll_deg','05_Wrist_pitch_deg']
    joints=['J01_Base_yaw','J02_Shoulder_pitch','J03_Elbow_pitch','J04_Wrist_roll','J05_Wrist_pitch']
    for key,name in zip(keys,joints):
        prop(ctrl,key,0.0,-30,30,'Pose preview offset only; collision and servo limits not certified')
        o=bpy.data.objects[name];drv(o,'delta_rotation_euler',2,'q*pi/180',[('q',ctrl,key)])
        o.lock_location=(True,True,True);o.lock_scale=(True,True,True)
    prop(ctrl,'06_Gripper_deg',0.0,-8,8,'Coupled gears and solved four-bar closure; limited preview range, no contact stop')
    palm=bpy.data.objects['ARD_07_Gripper_base']
    root=empty('MECH_Gripper_reference',None,col);root.matrix_world=palm.matrix_world.copy();preserve(root,bpy.data.objects['J05_Wrist_pitch'])
    qvar=[('q',ctrl,'06_Gripper_deg')]
    saved={o.name:[list(r) for r in o.matrix_world] for o in sc.objects if o.name.startswith(('ARD_08_','ARD_09_','ARD_10_','REVB_S06'))}
    solvers=[]
    for side,cx,theta,sgn,dx,dz,ax in [('Left',5,-155,1,30.75,0,13),('Right',31.9,147.5,-1,-30.486231,4.01368,23)]:
        solver=empty('MECH_'+side+'_solver',root,col)
        for k,v in [('cx',cx),('cz',-25),('d',30),('a',0),('h',20),('bx',0),('bz',0)]:prop(solver,k,float(v))
        t=f'({theta}+({sgn})*q)*pi/180'
        drv(solver,'["cx"]',None,f'{cx}+({dx})*cos({t})+({dz})*sin({t})',qvar)
        drv(solver,'["cz"]',None,f'-25-({dx})*sin({t})+({dz})*cos({t})',qvar)
        def vs(*names):return [(k,solver,k) for k in names]
        drv(solver,'["d"]',None,f'sqrt(({ax}-cx)**2+(-5-cz)**2)',vs('cx','cz'))
        drv(solver,'["a"]',None,'(22**2-31**2+d*d)/(2*d)',vs('d'))
        drv(solver,'["h"]',None,'sqrt(max(0,22**2-a*a))',vs('a'))
        # Choose the upper-z circle intersection, on the same assembly branch.
        drv(solver,'["bx"]',None,f'cx+a*({ax}-cx)/d-({sgn})*h*(-5-cz)/d',vs('cx','cz','a','d','h'))
        drv(solver,'["bz"]',None,f'cz+a*(-5-cz)/d+({sgn})*h*({ax}-cx)/d',vs('cx','cz','a','d','h'))
        gp=empty('MECH_'+side+'_gear',root,col);gp.location=(cx,8.4,-25)
        gp.rotation_euler.y=math.radians(theta);drv(gp,'rotation_euler',1,t,qvar)
        gear=bpy.data.objects['ARD_08_gear1' if side=='Left' else 'ARD_08_gear2']
        gear.parent=gp;gear.matrix_parent_inverse=Matrix.Identity(4);gear.matrix_basis=Matrix.Translation((10.10634,0,0))
        lp=empty('MECH_'+side+'_link',root,col);lp.location=(ax,8.4,-5)
        drv(lp,'rotation_euler',1,f'atan2(-(bz+5),bx-{ax})',vs('bx','bz'))
        link=bpy.data.objects['ARD_09_Link_'+side];link.parent=lp;link.matrix_parent_inverse=Matrix.Identity(4);link.matrix_basis=Matrix.Identity(4)
        jp=empty('MECH_'+side+'_jaw',root,col);jp.location.y=12.8
        drv(jp,'location',0,'cx',vs('cx'));drv(jp,'location',2,'cz',vs('cz'))
        drv(jp,'rotation_euler',1,'atan2(cx-bx,cz-bz)',vs('cx','cz','bx','bz'))
        jaw=bpy.data.objects['ARD_10_Jaw_'+side];jaw.parent=jp;jaw.matrix_parent_inverse=Matrix.Identity(4)
        jaw.matrix_basis=Matrix.Rotation(math.radians(90*sgn),4,'Z')@Matrix.Translation((0 if side=='Left' else -8.5,-5,5))
        cp=empty('MECH_'+side+'_crank_pin',root,col);cp.location.y=11.8
        bp=empty('MECH_'+side+'_link_tip_pin',root,col);bp.location.y=11.8
        for o,px,pz in [(cp,'cx','cz'),(bp,'bx','bz')]:
            drv(o,'location',0,px,vs(px));drv(o,'location',2,pz,vs(pz))
        bpy.context.view_layer.update()
        for kind,parent in [('crank',cp),('link_tip',bp)]:
            for suffix in ('pin','head'):
                o=bpy.data.objects.get('ARD_'+side+'_'+kind+'_'+suffix)
                if o:preserve(o,parent)
        if side=='Right':
            preserve(bpy.data.objects['REVB_S06_MG90S_SINGLE_HORN'],gp)
            for n in ['ARD_S06_center_screw','ARD_S06_horn_screw','ARD_S06_horn_screw.001']:
                if n in bpy.data.objects:preserve(bpy.data.objects[n],gp)
            # This pivot is the servo shaft, not an extra M3 pin through the servo.
            for n in ['ARD_Right_gear_pin','ARD_Right_gear_head']:
                bpy.data.objects[n].hide_render=True;bpy.data.objects[n].hide_set(True)
        solvers.append(solver)
    bpy.context.view_layer.update()
    errors={n:max(abs(bpy.data.objects[n].matrix_world[i][j]-m[i][j]) for i in range(4) for j in range(4)) for n,m in saved.items()}
    result={'initial_pose_matrix_max_error':errors,'description':'Five native local-axis offset drivers and two native four-bar solvers, independent of Python auto-run. Kinematic only.'}
    if max(errors.values())>.005:raise RuntimeError('Rig changed original pose '+str(errors))
    invalid=[o.name for o in sc.objects if o.animation_data and any(not f.driver.is_valid for f in o.animation_data.drivers)]
    result['invalid_driver_objects']=invalid
    (OUT/'motion_report.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    for o in sc.objects:o.select_set(False)
    ctrl.select_set(True);bpy.context.view_layer.objects.active=ctrl
    sc['Joint_controls']='ARM_CONTROLS custom properties: five joints and closed gripper linkage. Preview only; no collision response.'
    return result

def validate():
    ctrl=bpy.data.objects['ARM_CONTROLS'];rows=[]
    for angle in [-8,-4,0,4,8]:
        ctrl['06_Gripper_deg']=float(angle);ctrl.update_tag();bpy.context.view_layer.update()
        bpy.context.scene.frame_set(bpy.context.scene.frame_current)
        for side,ax in [('Left',13),('Right',23)]:
            s=bpy.data.objects['MECH_'+side+'_solver']
            c=Vector((s['cx'],0,s['cz']));b=Vector((s['bx'],0,s['bz']));a=Vector((ax,0,-5))
            rows.append({'angle_deg':angle,'side':side,'link_length':(b-a).length,'jaw_pitch':(c-b).length,'d':s['d'],'branch_valid':9<s['d']<53})
    ctrl['06_Gripper_deg']=0.0;ctrl.update_tag();bpy.context.view_layer.update()
    (OUT/'gripper_closure_checks.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    return rows

def fix_axes():
    # Blender delta Euler rotation is not a post-multiplied local Z rotation.
    # A zero-frame parent makes the driven joint's basis identity, unambiguous.
    ctrl=bpy.data.objects['ARM_CONTROLS'];col=bpy.data.collections['REVB_06_Motion'];checks=[]
    names=['J01_Base_yaw','J02_Shoulder_pitch','J03_Elbow_pitch','J04_Wrist_roll','J05_Wrist_pitch']
    keys=['01_Base_deg','02_Shoulder_deg','03_Elbow_deg','04_Wrist_roll_deg','05_Wrist_pitch_deg']
    for name,key in zip(names,keys):
        o=bpy.data.objects[name]
        if 'ZERO_'+name not in bpy.data.objects:
            world=o.matrix_world.copy();parent=o.parent
            z=empty('ZERO_'+name,None,col);z.matrix_world=world
            if parent:preserve(z,parent)
            o.driver_remove('delta_rotation_euler',2);o.delta_rotation_euler=(0,0,0)
            o.parent=z;o.matrix_parent_inverse=Matrix.Identity(4);o.matrix_basis=Matrix.Identity(4)
            drv(o,'rotation_euler',2,'q*pi/180',[('q',ctrl,key)])
        bpy.context.view_layer.update();original=o.matrix_world.copy()
        ctrl[key]=10.0;ctrl.update_tag();bpy.context.view_layer.update()
        expected=original@Matrix.Rotation(math.radians(10),4,'Z')
        err=max(abs(o.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4))
        checks.append({'joint':name,'local_axis_rotation_matrix_error':err})
        ctrl[key]=0.0;ctrl.update_tag();bpy.context.view_layer.update()
        if err>.0001:raise RuntimeError('Joint axis mismatch '+name)
    (OUT/'joint_axis_checks.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
    return checks
