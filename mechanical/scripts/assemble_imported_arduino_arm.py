import adsk.core
import adsk.fusion
import math
import traceback


app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
if not design:
    raise RuntimeError('The active Fusion document is not a Design workspace.')

root = design.rootComponent


def mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def rot_x(degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def rot_y(degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def rot_z(degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def transform_point(r, p):
    return [sum(r[row][col] * p[col] for col in range(3)) for row in range(3)]


def anchor_matrix(rx, ry, rz, local_anchor, world_target):
    # Apply local X, then world Y, then world Z rotations.
    r = mat_mul(rot_z(rz), mat_mul(rot_y(ry), rot_x(rx)))
    rp = transform_point(r, local_anchor)
    t = [world_target[i] - rp[i] for i in range(3)]
    m = adsk.core.Matrix3D.create()
    for row in range(3):
        for col in range(3):
            m.setCell(row, col, r[row][col])
        m.setCell(row, 3, t[row])
    return m


def place(occ, rx, ry, rz, local_anchor, world_target):
    occ.transform2 = anchor_matrix(rx, ry, rz, local_anchor, world_target)


def new_component_for_mesh(mesh_body):
    identity = adsk.core.Matrix3D.create()
    occ = root.occurrences.addNewComponent(identity)
    occ.component.name = mesh_body.name
    moved = mesh_body.moveToComponent(occ)
    if not moved:
        raise RuntimeError('Could not move mesh into component: ' + mesh_body.name)
    return occ


globals().update(locals())


try:
    if root.occurrences.count:
        raise RuntimeError('Assembly already contains occurrences; refusing to duplicate it.')
    if root.meshBodies.count != 12:
        raise RuntimeError('Expected 12 imported root mesh bodies, found %d.' % root.meshBodies.count)

    meshes = [root.meshBodies.item(i) for i in range(root.meshBodies.count)]
    occs = {}
    for mesh in meshes:
        name = mesh.name
        occs[name] = new_component_for_mesh(mesh)

    # Ground structure. Base and waist were authored on their circular faces, so
    # rotate their source Y axes vertical and center them on the assembly Z axis.
    place(occs['Base'], 90, 0, 0, (4.078, 3.611, 9.288), (0, 0, 0))
    place(occs['Waist'], 90, 0, 0, (0, 0, 0), (0, 0, 4.8))

    # Four instances of the single support-foot STL.
    foot_component = occs['Pata_de_Soporte'].component
    foot_anchor = (10.313, 3.611, 15.570)
    foot_targets = [(9.5, 0, 0), (0, 9.5, 0), (-9.5, 0, 0), (0, -9.5, 0)]
    foot_angles = [0, 90, 180, 270]
    place(occs['Pata_de_Soporte'], 90, 0, foot_angles[0], foot_anchor, foot_targets[0])
    for index in range(1, 4):
        extra = root.occurrences.addExistingComponent(foot_component, adsk.core.Matrix3D.create())
        place(extra, 90, 0, foot_angles[index], foot_anchor, foot_targets[index])

    # Main arm in a neutral, readable pose matching the supplied photograph.
    shoulder = (0, 0, 9.8)
    elbow = (9.91, 0, 16.74)
    wrist = (19.43, 0, 12.30)
    wrist_adapter = (23.60, 0, 10.36)

    place(occs['Arm_01'], 90, 55, 0, (0, 0, 1.05), shoulder)
    place(occs['Arm_02_v3'], 90, -65, 0, (0, 5.5, 0.55), elbow)
    place(occs['Arm_03'], 90, -65, 0, (0, 4.6, 0), wrist)
    place(occs['Gripper_base'], 0, -25, 0, (2.2, -0.9, 0), wrist_adapter)

    # Gripper mechanism. The source package contains mirrored jaw meshes, two
    # sector gears and one linkage; the linkage is instantiated twice.
    place(occs['gear1'], 0, -25, 0, (-0.9, 0.2, 0), (25.95, -0.35, 4.35))
    place(occs['gear2'], 0, -25, 0, (-0.4, 0.2, 0), (27.65, 0.35, 4.35))
    place(occs['Gripper_1'], 0, -25, 0, (0.775, 1.02, -0.3), (27.4, 1.15, 3.55))
    place(occs['Gripper_1_1'], 0, -25, 0, (0.075, 1.02, -0.3), (27.4, -1.15, 3.55))
    place(occs['grip_link_1'], 0, -25, 0, (0, 0.2, 0), (25.55, 0.85, 4.0))
    link_component = occs['grip_link_1'].component
    link2 = root.occurrences.addExistingComponent(link_component, adsk.core.Matrix3D.create())
    place(link2, 0, -25, 180, (0, 0.2, 0), (28.05, -0.85, 4.0))

    app.activeViewport.fit()
    adsk.doEvents()
    result['output'] = (
        'Assembled 12 unique STL meshes into 16 occurrences: 4 support feet, '
        '3 arm sections, wrist/gripper base, mirrored jaws, 2 gears and 2 links.'
    )
except Exception:
    result['output'] = traceback.format_exc()
    raise
