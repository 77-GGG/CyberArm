"""Background Blender exporter. Never saves or changes the source .blend on disk."""
import bpy
import json
import math
import hashlib
import random
from pathlib import Path
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'simulator/assets/revc'
OUT.mkdir(parents=True, exist_ok=True)
scene = bpy.data.scenes['Arduino_Original_Replica']
bpy.context.window.scene = scene
ctrl = bpy.data.objects['ARM_CONTROLS']
keys = ['01_Base_deg','02_Shoulder_deg','03_Elbow_deg','04_Wrist_roll_deg','05_Wrist_pitch_deg','06_Gripper_deg']
names = ['J01_Base_yaw','J02_Shoulder_pitch','J03_Elbow_pitch','J04_Wrist_roll','J05_Wrist_pitch']
frames = names + ['MECH_Gripper_reference'] + ['MECH_'+side+'_'+part for side in ['Left','Right'] for part in ['gear','link','jaw','crank_pin','link_tip_pin']]

def pose(q):
    for k,v in zip(keys,q): ctrl[k]=float(v)
    ctrl.update_tag()
    bpy.context.view_layer.update()
    scene.frame_set(scene.frame_current)
    bpy.context.view_layer.update()

def mat(m):
    result = [list(row) for row in m]
    for i in range(3): result[i][3] *= .001
    return result

pose([0]*6)
zero = [bpy.data.objects[n].matrix_world.copy() for n in frames]
local = [zero[0]]+[zero[i-1].inverted()@zero[i] for i in range(1,5)]
palm = zero[4].inverted() @ zero[5]
# Fixed tool frame, close to the reference jaw tips; explicitly a simulation TCP.
tip = Matrix.Translation((18.45,12.8,50.0))
reference=[]
rng=random.Random(20260914)
samples=[[0]*6]+[[a if j==i else 0 for j in range(6)] for i in range(5) for a in [-15,15]]
samples += [[rng.uniform(-25,25) for _ in range(5)]+[rng.uniform(-8,8)] for _ in range(35)]
samples += [[0]*5+[-8+16*i/20] for i in range(21)]
for q in samples:
    pose(q)
    reference.append({'q_deg':q,'frames':[mat(bpy.data.objects[n].matrix_world) for n in frames],
                      'tcp':mat(bpy.data.objects[frames[5]].matrix_world@tip)})
pose([0]*6)

def anchor(o):
    parent=o
    while parent:
        if parent.name in frames:return frames.index(parent.name)
        parent=parent.parent
    return -1

import numpy as np
collision=[]
def hierarchy(mesh):
    mesh.calc_loop_triangles()
    v=np.array([v.co[:] for v in mesh.vertices])
    triangles=v[np.array([t.vertices[:] for t in mesh.loop_triangles])]
    lower=triangles.min(axis=1);upper=triangles.max(axis=1);centers=(lower+upper)/2
    nodes=[]
    def build(ids):
        lo=lower[ids].min(axis=0);hi=upper[ids].max(axis=0)
        index=len(nodes);nodes.append([lo.tolist(),hi.tolist(),-1,-1])
        if len(ids)>4:
            axis=int(np.argmax(hi-lo));ids=ids[np.argsort(centers[ids,axis])];middle=len(ids)//2
            nodes[index][2]=build(ids[:middle]);nodes[index][3]=build(ids[middle:])
        else:nodes[index].append(triangles[ids].tolist())
        return index
    build(np.arange(len(triangles)))
    return nodes

meshes=[]
copies=[]
dep=bpy.context.evaluated_depsgraph_get()
for o in list(scene.objects):
    if o.type!='MESH' or o.hide_render or o.hide_get() or not o.visible_get():continue
    if o.name.startswith(('REVC_LABEL','LABEL','TEXT')):continue
    evaluated=o.evaluated_get(dep)
    mesh=bpy.data.meshes.new_from_object(evaluated,depsgraph=dep)
    transform=Matrix.Scale(.001,4)@o.matrix_world
    mesh.transform(transform)
    mesh.update()
    obj=bpy.data.objects.new('VIS_'+o.name,mesh)
    obj['source_name']=o.name
    obj['frame_index']=anchor(o)
    copies.append(obj)
    collision.append({'name':o.name,'frame':anchor(o),'nodes':hierarchy(mesh)})
    vertices=[v.co[:] for v in mesh.vertices]
    lo=[min(v[k] for v in vertices) for k in range(3)]
    hi=[max(v[k] for v in vertices) for k in range(3)]
    meshes.append({'name':obj.name,'source':o.name,'frame':anchor(o),'bounds':[lo,hi],
                   'vertices':len(vertices),'material':o.active_material.name if o.active_material else None})
export=bpy.data.scenes.new('CyberArm_SIM_export')
bpy.context.window.scene=export
for obj in copies:export.collection.objects.link(obj)
bpy.ops.export_scene.gltf(filepath=str(OUT/'robot.glb'),export_format='GLB',use_selection=False,
    use_active_scene=True,export_yup=False,export_extras=True,export_animations=False,
    export_cameras=False,export_lights=False,export_apply=False)
source=Path(bpy.data.filepath)
model={'schema_version':1,'model_id':'revc-sim-1','source':str(source),
       'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
       'units':'m_rad','coordinate_system':'right-handed Z-up, source base origin',
       'frame_names':frames,'joint_local':[mat(m) for m in local],
       'palm_local':mat(palm),'tcp_local':mat(tip),'zero_frames':[mat(m) for m in zero],
       'limits_deg':[[-30,30]]*5+[[-8,8]],'limits_status':'temporary simulation preview limits; not hardware calibrated',
       'max_velocity_deg_s':[25,20,25,35,35,12],'max_acceleration_deg_s2':[50,40,50,70,70,24],
       'meshes':meshes,'hardware_calibration':None,'joint_feedback':False,
       'tcp_status':'simulation tool reference, to validate against geometry'}
(OUT/'robot.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pack_collision import pack
pack(collision,OUT/'collision.npz')
(OUT/'reference_poses.json').write_text(json.dumps(reference,indent=2),encoding='utf-8')
print('EXPORT_REPORT '+json.dumps({'meshes':len(meshes),'frames':len(frames),'reference_poses':len(reference),'glb_bytes':(OUT/'robot.glb').stat().st_size}))
