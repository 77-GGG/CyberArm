"""Static mass/moment screening, not a rated payload or structural analysis."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector
OUT=Path('E:/CyberArm/mechanical/archive/arduino_reference_revB')

def centroid(o):
    mesh=o.data;mesh.calc_loop_triangles();vol=0.;first=Vector()
    for t in mesh.loop_triangles:
        a,b,c=[mesh.vertices[i].co for i in t.vertices]
        v=a.dot(b.cross(c))/6;vol+=v;first+=(a+b+c)*(v/4)
    return abs(vol),o.matrix_world@(first/vol)

def downstream(o,root):
    while o:
        if o==root:return True
        o=o.parent
    return False

def run():
    items=[];sc=bpy.context.scene
    collection=next(c for c in sc.collection.children if c.name.startswith('ARD_01_'))
    for o in collection.objects:
        if o.type!='MESH':continue
        vol,com=centroid(o)
        items.append((o,vol*.00124,com,'100% solid PLA proxy density 1.24 g/cm3'))
    for o in sc.objects:
        if o.name.startswith('REVB_S') and o.name.endswith('MG996R_SOURCE'):
            items.append((o,55,o.matrix_world@Vector((-10.45,0,-24.2)),'Vendor nominal mass; approximate body centroid'))
        elif o.name.endswith('MG90S_USER_MODEL'):
            items.append((o,13.4,o.matrix_world@Vector((-5.2,0,-19)),'Vendor nominal mass; approximate body centroid'))
    G=bpy.data.objects['ARD_07_Gripper_base'].matrix_world
    jaws=[bpy.data.objects[n] for n in ['ARD_10_Jaw_Left','ARD_10_Jaw_Right']]
    verts=[G.inverted()@o.matrix_world@v.co for o in jaws for v in o.data.vertices]
    zmax=max(v.z for v in verts)
    point=G@Vector((18.45,12.8,zmax))
    rows=[]
    for name,stall in [('J02_Shoulder_pitch',9.4),('J03_Elbow_pitch',9.4),('J04_Wrist_roll',1.8),('J05_Wrist_pitch',1.8)]:
        root=bpy.data.objects[name];origin=root.matrix_world.translation;axis=(root.matrix_world.to_3x3()@Vector((0,0,1))).normalized()
        moving=[row for row in items if downstream(row[0],root)]
        # 8 g lumped allowance for horns / fasteners / wires at the test point.
        selected=[(mass,pos) for o,mass,pos,note in moving]+[(8,point)]
        empty=abs(sum(axis.dot(((pos-origin)/1000).cross(Vector((0,0,-mass/1000*9.80665)))) for mass,pos in selected))
        test=abs(sum(axis.dot(((pos-origin)/1000).cross(Vector((0,0,-mass/1000*9.80665)))) for mass,pos in selected+[(10,point)]))
        bound=sum(mass/1000*9.80665*((pos-origin).cross(axis)).length/1000 for mass,pos in selected+[(10,point)])
        rows.append({'joint':name,'downstream_solid_proxy_mass_g':sum(x[1] for x in moving)+8,'no_payload_saved_pose_Nm':empty,'with_10g_saved_pose_Nm':test,
                     'shape_fixed_gravity_upper_bound_with_10g_Nm':bound,'vendor_stall_4p8V_Nm':stall*.0980665,'saved_pose_percent_of_stall':test/(stall*.0980665)*100})
    result={'scope':'Saved pose only. Solid PLA is a mass proxy, not slicing estimate. No acceleration, continuous-torque rating, thermal, cable drag, bearing friction, deflection, print anisotropy, tipping or all-pose load analysis. Not a load certification.',
            'sources':['https://towerpro.com.tw/product/mg996r/','https://towerpro.com.tw/product/mg90s-3/'],
            'payload_test_point_world_mm':list(point),'all_printed_solid_proxy_mass_g':sum(m for o,m,p,n in items if n.startswith('100%')),
            'joint_screen':rows,'component_masses':[{'object':o.name,'mass_g':m,'com_world_mm':list(p),'basis':n} for o,m,p,n in items]}
    (OUT/'load_screen_NOT_RATING.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return {k:v for k,v in result.items() if k!='component_masses'}
