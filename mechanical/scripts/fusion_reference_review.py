"""Fusion MCP entry points; rebuildable review assembly, dimensions in millimetres.

Run with exec(compile(...), namespace, namespace) to give functions one scope.
Source meshes remain unchanged. This is not a print-release certification.
"""
import adsk.core as ac
import adsk.fusion as af
import json, math, pathlib, traceback

OUT = pathlib.Path('E:/CyberArm/mechanical/fusion_reference_review')
MANIFEST = pathlib.Path('E:/CyberArm/mechanical/archive/arduino_reference_replica/assembly_manifest.json')
APP = ac.Application.get()
DESIGN = af.Design.cast(APP.activeProduct)
ROOT = DESIGN.rootComponent
DATA = json.loads(MANIFEST.read_text(encoding='utf-8'))


def matrix(rows):
    m = ac.Matrix3D.create()
    # Blender stores float32 rotations; Fusion rejects their tiny non-orthogonality.
    x=ac.Vector3D.create(*(rows[k][0] for k in range(3)));x.normalize()
    y0=ac.Vector3D.create(*(rows[k][1] for k in range(3)))
    z=x.crossProduct(y0);z.normalize()
    y=z.crossProduct(x);y.normalize()
    m.setWithCoordinateSystem(mm_point([rows[k][3] for k in range(3)]),x,y,z)
    return m


def mm_point(p):
    return ac.Point3D.create(*(float(v)/10 for v in p))


def occurrence(name):
    for o in ROOT.occurrences:
        if o.component.name == name:
            return o
    return None


def start():
    OUT.mkdir(exist_ok=True)
    DESIGN.designIntent = af.DesignIntentTypes.HybridDesignIntentType
    DESIGN.designType = af.DesignTypes.DirectDesignType
    DESIGN.unitsManager.distanceDisplayUnits = af.DistanceUnits.MillimeterDistanceUnits
    ROOT.attributes.add('CyberArm', 'release_status', 'FIT REVIEW ONLY; real horns and MG996R unverified')
    return {'status': 'prepared', 'source_parts': len(DATA['parts'])}


def import_parts(first=0, count=4):
    imported = []
    for rec in DATA['parts'][first:first+count]:
        name = rec['object']
        o = occurrence(name)
        if o is None:
            o = ROOT.occurrences.addNewComponent(ac.Matrix3D.create())
            o.component.name = name
            bodies = o.component.meshBodies.add(rec['source'], af.MeshUnits.MillimeterMeshUnit)
            if not bodies:
                raise RuntimeError('No mesh imported: '+name)
            for b in bodies:
                b.name = pathlib.Path(rec['source']).stem
            o.component.attributes.add('CyberArm', 'source_sha256', rec['sha256'])
            o.component.attributes.add('CyberArm', 'status', 'Original STL; no fit edits')
        o.transform2 = matrix(rec['matrix_world'])
        imported.append({'name':name, 'mesh_count':o.component.meshBodies.count})
    return imported


def rigid(name, a, b):
    for j in ROOT.asBuiltJoints:
        if j.name == name:
            return j
    ji=ROOT.asBuiltJoints.createInput(a,b,None)
    ji.setAsRigidJointMotion()
    j=ROOT.asBuiltJoints.add(ji)
    j.name=name
    return j


def revolute(name, a, b, p, axis):
    for j in ROOT.asBuiltJoints:
        if j.name == name:
            return j
    sk=ROOT.sketches.add(ROOT.xYConstructionPlane)
    sk.name=name+'_datum'
    point=sk.sketchPoints.add(mm_point(p))
    second=sk.sketchPoints.add(mm_point([p[k]+axis[k]*10 for k in range(3)]))
    ai=ROOT.constructionAxes.createInput()
    ai.setByTwoPoints(point,second)
    ax=ROOT.constructionAxes.add(ai)
    ax.name=name+'_axis'
    geom=af.JointGeometry.createByPoint(point)
    ji=ROOT.asBuiltJoints.createInput(a,b,geom)
    ji.setAsRevoluteJointMotion(af.JointDirections.CustomJointDirection,ax)
    j=ROOT.asBuiltJoints.add(ji)
    j.name=name
    sk.isVisible=False
    ax.isLightBulbOn=False
    return j


def joints():
    DESIGN.designType=af.DesignTypes.ParametricDesignType
    chain=['ARD_01_Base','ARD_03_Waist','ARD_04_Arm_01','ARD_05_Arm_02_v3','ARD_06_Arm_03','ARD_07_Gripper_base']
    base=occurrence(chain[0]);base.isGrounded=True
    for i in range(1,5):
        rigid('FIX_Foot_'+str(i),base,occurrence('ARD_02_Foot_'+str(i)))
    names=['J01_Base_yaw','J02_Shoulder_pitch','J03_Elbow_pitch','J04_Wrist_roll','J05_Wrist_pitch']
    for i,name in enumerate(names):
        s=DATA['servos'][i]
        revolute(name,occurrence(chain[i]),occurrence(chain[i+1]),s['shaft_origin'],s['shaft_direction'])
    anchors=['ARD_05_Arm_02_v3','ARD_06_Arm_03','ARD_07_Gripper_base']
    for i in range(3,6):
        name=DATA['servos'][i]['name']+'_MG90S_STEP'
        o=occurrence(name)
        if o:rigid('FIX_'+name,occurrence(anchors[i-3]),o)
    return {'revolute':names,'joint_count':ROOT.asBuiltJoints.count}


def source_matrix(name):
    return next(r['matrix_world'] for r in DATA['parts'] if r['object']==name)


def mult(a,b):
    return [[sum(a[r][k]*b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def servo_matrix(i):
    t=[[0,0,1],[1,0,0],[0,1,0]]
    s=math.sqrt(.5)
    rotations=[[[0,-1,0],[1,0,0],[0,0,1]],
       mult(t,[[0,0,1],[s,s,0],[-s,s,0]]),
       mult(source_matrix('ARD_05_Arm_02_v3'),[[0,-1,0],[-1,0,0],[0,0,-1]]),
       mult(source_matrix('ARD_05_Arm_02_v3'),[[-1,0,0],[0,0,1],[0,1,0]]),
       mult(source_matrix('ARD_06_Arm_03'),[[0,1,0],[1,0,0],[0,0,-1]]),
       mult(source_matrix('ARD_07_Gripper_base'),[[1,0,0],[0,0,1],[0,-1,0]])]
    r=rotations[i]
    p=DATA['servos'][i]['shaft_origin']
    return [r[k]+[p[k]] for k in range(3)]+[[0,0,0,1]]


def hardware_mg90():
    lib=occurrence('LIB_MG90S_STEP_original')
    if lib is None or lib.component.occurrences.count!=1:
        raise RuntimeError('Import MG90S STEP into library first')
    original=lib.component.occurrences.item(0).component
    norm=matrix([[1,0,0,6],[0,0,-1,6],[0,1,0,-9.5],[0,0,0,1]])
    anchors=['ARD_05_Arm_02_v3','ARD_06_Arm_03','ARD_07_Gripper_base']
    out=[]
    for idx in range(3,6):
        name=DATA['servos'][idx]['name']+'_MG90S_STEP'
        o=occurrence(name)
        if o is None:
            o=ROOT.occurrences.addNewComponent(ac.Matrix3D.create())
            o.component.name=name
            for body in original.bRepBodies:
                copied=body.copyToComponent(o)
                coll=ac.ObjectCollection.create();coll.add(copied)
                mi=o.component.features.moveFeatures.createInput2(coll)
                mi.defineAsFreeMove(norm)
                o.component.features.moveFeatures.add(mi)
            o.transform2=matrix(servo_matrix(idx))
            o.component.attributes.add('CyberArm','status','User STEP geometry; shaft frame normalized, physical sample unverified')
        out.append({'name':name,'bodies':o.component.bRepBodies.count})
    lib.isLightBulbOn=False
    return out


def horn_library():
    horn_dir=pathlib.Path('E:/CyberArm/mechanical/servo配件')
    entries=[('single','obj_1_ServoMotor Arms.stl_B.stl',(111.4553,138.9141)),
             ('double','obj_2_ServoMotor Arms.stl_A_A.stl',(125.3488,129.2246)),
             ('cross','obj_3_ServoMotor Arms.stl_A_B.stl',(125.2333,114.0571))]
    out=[]
    for idx,(label,filename,center) in enumerate(entries):
        name='LIB_Horn_'+label+'_USER_STL'
        o=occurrence(name)
        if o is None:
            o=ROOT.occurrences.addNewComponent(ac.Matrix3D.create())
            o.component.name=name
            o.component.meshBodies.add(str(horn_dir/filename),af.MeshUnits.MillimeterMeshUnit)
            o.transform2=matrix([[1,0,0,-center[0]+idx*50],[0,1,0,-center[1]-115],[0,0,1,0],[0,0,0,1]])
            o.component.attributes.add('CyberArm','status','Actual downloaded geometry; purchased horn, not printable spline')
        bb=o.component.meshBodies.item(0).boundingBox
        out.append({'name':name,'size_mm':[10*(bb.maxPoint.asArray()[k]-bb.minPoint.asArray()[k]) for k in range(3)]})
    return out


def import_mesh_component(name,path,transform):
    o=occurrence(name)
    if o:return o
    o=ROOT.occurrences.addNewComponent(ac.Matrix3D.create())
    o.component.name=name
    bf=o.component.features.baseFeatures.add()
    bf.startEdit()
    try:
        mesh=o.component.meshBodies.add(str(path),af.MeshUnits.MillimeterMeshUnit,bf)
        if not mesh:raise RuntimeError('Mesh import failed: '+name)
    finally:
        bf.finishEdit()
    o.transform2=matrix(transform)
    o.component.attributes.add('CyberArm','source',str(path))
    return o


def hardware_mg996():
    folder=OUT/'mg996r_extracted'
    anchors=['ARD_01_Base','ARD_03_Waist','ARD_05_Arm_02_v3']
    horn_anchors=['ARD_03_Waist','ARD_04_Arm_01','ARD_04_Arm_01']
    upper=source_matrix('ARD_04_Arm_01')
    # Align the two opposing circular-horn holes with the original arm's Y axis.
    r=[[upper[k][1],-upper[k][0],upper[k][2]] for k in range(3)]
    out=[]
    for i in range(3):
        name=DATA['servos'][i]['name']+'_MG996R_SOURCE_MESH'
        o=import_mesh_component(name,folder/'MG996R_case_shaft_sleeve_canonical_mm.stl',servo_matrix(i))
        o.component.attributes.add('CyberArm','status','Source display mesh assembled using SLDASM transforms; shaft origin at output tip')
        rigid('FIX_'+name,occurrence(anchors[i]),o)
        p=DATA['servos'][i]['shaft_origin']
        hm=([[1,0,0,p[0]],[0,1,0,p[1]],[0,0,1,p[2]],[0,0,0,1]] if i==0 else [r[k]+[p[k]] for k in range(3)]+[[0,0,0,1]])
        hn=DATA['servos'][i]['name']+'_ROUND_HORN_14mm_PITCH'
        h=import_mesh_component(hn,folder/'MG996R_round_horn_canonical_mm.stl',hm)
        h.component.attributes.add('CyberArm','status','Actual source circular horn; original printed 14.5 mm pitch needs adaptation to 14 mm')
        rigid('FIX_'+hn,occurrence(horn_anchors[i]),h)
        out.append(name)
    return out


def transformed_point(m,p):
    return [sum(m[k][j]*p[j] for j in range(3))+m[k][3] for k in range(3)]


def gripper_joints():
    palm=occurrence('ARD_07_Gripper_base')
    g=source_matrix('ARD_07_Gripper_base')
    axis=[g[k][1] for k in range(3)]
    created=[]
    for side,stem,cx in [('Left','gear1',5),('Right','gear2',31.9)]:
        gear=occurrence('ARD_08_'+stem)
        link=occurrence('ARD_09_Link_'+side)
        jaw=occurrence('ARD_10_Jaw_'+side)
        gm=source_matrix('ARD_08_'+stem)
        lm=source_matrix('ARD_09_Link_'+side)
        center=transformed_point(g,[cx,8.4,-25])
        crank=transformed_point(gm,[20.64366,0,0] if side=='Left' else [-40.592571,0,4.01368])
        base=transformed_point(lm,[0,0,0])
        tip=transformed_point(lm,[31,0,0])
        for suffix,a,b,p in [('gear',palm,gear,center),('link',palm,link,base),('crank_pin',gear,jaw,crank),('tip_pin',link,jaw,tip)]:
            name='JG_'+side+'_'+suffix
            revolute(name,a,b,p,axis)
            created.append(name)
    return created


def checkpoint():
    OUT.mkdir(exist_ok=True)
    path=OUT/'CyberArm_Reference_Assembly_REVIEW.f3d'
    ok=DESIGN.exportManager.execute(DESIGN.exportManager.createFusionArchiveExportOptions(str(path)))
    report={'archive':str(path),'exported':ok,'components':[],'joints':[],'status':'Fit review; no print release'}
    for o in ROOT.occurrences:
        report['components'].append({'name':o.component.name,'mesh':o.component.meshBodies.count,'bodies':o.component.bRepBodies.count,'visible':o.isLightBulbOn})
    for j in ROOT.asBuiltJoints:
        report['joints'].append({'name':j.name,'type':j.jointMotion.jointType,'valid':j.isValid})
    (OUT/'fusion_review_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    APP.activeViewport.fit()
    return report
