import adsk.core
import adsk.fusion
import math
import traceback


app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
if not design:
    raise RuntimeError('The active Fusion document is not a Design workspace.')

root = design.rootComponent
temp = adsk.fusion.TemporaryBRepManager.get()


def mm(value):
    return float(value) / 10.0


def point(x, y, z):
    return adsk.core.Point3D.create(mm(x), mm(y), mm(z))


def vector(x, y, z):
    v = adsk.core.Vector3D.create(float(x), float(y), float(z))
    if not v.normalize():
        raise ValueError('Zero-length direction vector')
    return v


def add_parameter(name, expression, unit, comment):
    existing = design.userParameters.itemByName(name)
    if existing:
        existing.expression = expression
        return existing
    return design.userParameters.add(
        name,
        adsk.core.ValueInput.createByString(expression),
        unit,
        comment,
    )


def obb_temp(cx, cy, cz, length, width, height, u=(1, 0, 0), v=(0, 1, 0)):
    box = adsk.core.OrientedBoundingBox3D.create(
        point(cx, cy, cz),
        vector(*u),
        vector(*v),
        mm(length),
        mm(width),
        mm(height),
    )
    return temp.createBox(box)


def cylinder_temp(p1, p2, radius):
    return temp.createCylinderOrCone(point(*p1), mm(radius), point(*p2), mm(radius))


def union(target, tool):
    ok = temp.booleanOperation(target, tool, adsk.fusion.BooleanTypes.UnionBooleanType)
    if not ok:
        raise RuntimeError('Temporary BRep union failed')
    return target


def subtract(target, tool):
    ok = temp.booleanOperation(target, tool, adsk.fusion.BooleanTypes.DifferenceBooleanType)
    if not ok:
        raise RuntimeError('Temporary BRep cut failed')
    return target


def add_body(name, temp_body):
    body = root.bRepBodies.add(temp_body)
    body.name = name
    return body


def rounded_plate_temp(cx, cy, cz, length, width, height, radius):
    body = obb_temp(cx, cy, cz, length - 2 * radius, width, height)
    union(body, obb_temp(cx, cy, cz, length, width - 2 * radius, height))
    z1 = cz - height / 2
    z2 = cz + height / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            corner = cylinder_temp(
                (cx + sx * (length / 2 - radius), cy + sy * (width / 2 - radius), z1),
                (cx + sx * (length / 2 - radius), cy + sy * (width / 2 - radius), z2),
                radius,
            )
            union(body, corner)
    return body


def link_temp(p0, p1, thickness, plate_width, hole_diameter, lighten=True):
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    dz = p1[2] - p0[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    u = (dx / length, dy / length, dz / length)
    v = (0, 1, 0)
    cx = (p0[0] + p1[0]) / 2
    cy = (p0[1] + p1[1]) / 2
    cz = (p0[2] + p1[2]) / 2
    body = obb_temp(cx, cy, cz, length, thickness, plate_width, u, v)
    for p in (p0, p1):
        boss = cylinder_temp(
            (p[0], p[1] - thickness / 2, p[2]),
            (p[0], p[1] + thickness / 2, p[2]),
            plate_width / 2,
        )
        union(body, boss)
    if lighten and length > 45:
        slot_length = length - 30
        slot = obb_temp(cx, cy, cz, slot_length, thickness + 2, max(4, plate_width - 10), u, v)
        subtract(body, slot)
    for p in (p0, p1):
        hole = cylinder_temp(
            (p[0], p[1] - thickness / 2 - 2, p[2]),
            (p[0], p[1] + thickness / 2 + 2, p[2]),
            hole_diameter / 2,
        )
        subtract(body, hole)
    return body


def cradle_temp(center, u, overall_length=36, overall_width=30, overall_height=32, wall=4):
    ux, uy, uz = u
    px, py, pz = (-uz, 0, ux)
    cx, cy, cz = center
    body = obb_temp(
        cx - px * (overall_height / 2 - wall / 2),
        cy,
        cz - pz * (overall_height / 2 - wall / 2),
        overall_length,
        overall_width,
        wall,
        u,
        (0, 1, 0),
    )
    for sign in (-1, 1):
        cheek = obb_temp(
            cx,
            cy + sign * (overall_width / 2 - wall / 2),
            cz,
            overall_length,
            wall,
            overall_height,
            u,
            (0, 1, 0),
        )
        union(body, cheek)
    axis_hole = cylinder_temp(
        (cx, cy - overall_width / 2 - 1, cz),
        (cx, cy + overall_width / 2 + 1, cz),
        2.2,
    )
    subtract(body, axis_hole)
    return body


def l_jaw_temp(name, y_sign):
    y = y_sign * 20
    body = obb_temp(168, y, 106, 38, 6, 8)
    finger = obb_temp(184, y, 94, 8, 6, 30)
    union(body, finger)
    pivot = cylinder_temp((151, y - 5, 106), (151, y + 5, 106), 2.1)
    subtract(body, pivot)
    return add_body(name, body)


# FusionMCP executes scripts with distinct globals/locals dictionaries. Publish
# the initialized API objects and helpers so nested helper calls resolve normally.
globals().update(locals())


try:
    if root.bRepBodies.count or root.sketches.count:
        raise RuntimeError('Current design is not empty; refusing to overwrite existing geometry.')

    # Regeneration parameters. Geometry is script-driven so these values remain the
    # single source of truth for the printable prototype.
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    add_parameter('upper_arm_length', '90 mm', 'mm', 'Shoulder axis to elbow axis')
    add_parameter('forearm_length', '80 mm', 'mm', 'Elbow axis to wrist axis')
    add_parameter('link_thickness', '8 mm', 'mm', 'FDM printed link thickness')
    add_parameter('link_width', '20 mm', 'mm', 'FDM printed link plate width')
    add_parameter('joint_bore', '4.4 mm', 'mm', 'Clearance bore for M4 shoulder bolts')
    add_parameter('print_clearance', '0.4 mm', 'mm', 'Nominal FDM sliding clearance')
    add_parameter('min_wall', '4 mm', 'mm', 'Minimum structural wall')
    add_parameter('base_size', '120 mm', 'mm', 'Square desktop footprint')
    add_parameter('k230d_width', '64.3 mm', 'mm', 'K230D BOX nominal width')
    add_parameter('k230d_height', '47.6 mm', 'mm', 'K230D BOX nominal height')
    add_parameter('k230d_depth', '15.4 mm', 'mm', 'K230D BOX nominal body depth')

    # Temporary-BRep construction is most reliable in Fusion's direct-design mode.
    # The source script and named parameters remain the regeneration interface.
    design.designType = adsk.fusion.DesignTypes.DirectDesignType

    # Base plate: rounded corners, four M4 mounting holes and a 6.4 mm central shaft.
    base = rounded_plate_temp(0, 0, 4, 120, 120, 8, 10)
    for x in (-50, 50):
        for y in (-50, 50):
            subtract(base, cylinder_temp((x, y, -1), (x, y, 9), 2.2))
    subtract(base, cylinder_temp((0, 0, -1), (0, 0, 9), 3.2))
    add_body('PRINT_01_BasePlate', base)

    # Bearing-supported turntable. The servo drives rotation, but the disk carries axial load.
    turntable = cylinder_temp((0, 0, 8), (0, 0, 16), 38)
    subtract(turntable, cylinder_temp((0, 0, 7), (0, 0, 17), 3.2))
    for angle in (0, 90, 180, 270):
        a = math.radians(angle)
        x = 27 * math.cos(a)
        y = 27 * math.sin(a)
        subtract(turntable, cylinder_temp((x, y, 7), (x, y, 17), 1.7))
    add_body('PRINT_02_Turntable', turntable)

    # Shoulder U-bracket with a mechanically supported cross-axis.
    shoulder_axis = (0, 0, 61)
    shoulder = obb_temp(0, 0, 19, 46, 42, 6)
    for side in (-1, 1):
        cheek = obb_temp(0, side * 18.5, 40, 38, 5, 48)
        union(shoulder, cheek)
    subtract(shoulder, cylinder_temp((0, -23, 61), (0, 23, 61), 2.2))
    add_body('PRINT_03_ShoulderBracket', shoulder)

    # Neutral demonstration pose, chosen to show the entire kinematic chain clearly.
    upper_length = 90.0
    upper_angle = math.radians(50)
    elbow_axis = (
        shoulder_axis[0] + upper_length * math.cos(upper_angle),
        0,
        shoulder_axis[2] + upper_length * math.sin(upper_angle),
    )
    forearm_length = 80.0
    forearm_angle = math.radians(-15)
    wrist_axis = (
        elbow_axis[0] + forearm_length * math.cos(forearm_angle),
        0,
        elbow_axis[2] + forearm_length * math.sin(forearm_angle),
    )

    add_body('PRINT_04_UpperArm', link_temp(shoulder_axis, elbow_axis, 8, 20, 4.4, True))
    add_body('PRINT_05_ElbowCradle', cradle_temp(elbow_axis, (math.cos(upper_angle), 0, math.sin(upper_angle))))
    add_body('PRINT_06_Forearm', link_temp(elbow_axis, wrist_axis, 8, 18, 4.4, True))
    add_body('PRINT_07_WristCradle', cradle_temp(wrist_axis, (math.cos(forearm_angle), 0, math.sin(forearm_angle)), 32, 28, 30, 4))

    # Wrist-to-gripper palm adapter.
    adapter_center = (wrist_axis[0] + 13, 0, wrist_axis[2])
    adapter = obb_temp(adapter_center[0], 0, adapter_center[2], 30, 32, 10)
    subtract(adapter, cylinder_temp((wrist_axis[0], -18, wrist_axis[2]), (wrist_axis[0], 18, wrist_axis[2]), 2.2))
    add_body('PRINT_08_GripperPalm', adapter)

    l_jaw_temp('PRINT_09_LeftJaw', 1)
    l_jaw_temp('PRINT_10_RightJaw', -1)

    # Fixed K230D support: base foot, mast, ventilated backplate, and M3 mounting holes.
    mount = obb_temp(-47, 0, 11, 32, 80, 6)
    union(mount, obb_temp(-50, 0, 52, 8, 18, 76))
    union(mount, obb_temp(-50, 0, 121, 5, 74, 64))
    for y in (-26, 26):
        for z in (101, 141):
            subtract(mount, cylinder_temp((-54, y, z), (-46, y, z), 1.7))
    for z in (113, 130):
        subtract(mount, obb_temp(-50, 0, z, 8, 38, 9))
    add_body('PRINT_11_K230D_Mount', mount)

    # Non-printing reference envelopes used for collision and packaging checks.
    add_body('REF_MG90S_Base', obb_temp(0, 0, 3, 23.2, 12.5, 29.0))
    add_body('REF_MG90S_Shoulder', obb_temp(0, 0, 48, 23.2, 12.5, 29.0))
    add_body('REF_MG90S_Elbow', obb_temp(elbow_axis[0], 0, elbow_axis[2], 29.0, 12.5, 23.2, (math.cos(upper_angle), 0, math.sin(upper_angle)), (0, 1, 0)))
    add_body('REF_MG90S_Wrist', obb_temp(wrist_axis[0], 0, wrist_axis[2], 29.0, 12.5, 23.2, (math.cos(forearm_angle), 0, math.sin(forearm_angle)), (0, 1, 0)))
    add_body('REF_MG90S_Gripper', obb_temp(adapter_center[0] + 4, 0, adapter_center[2] + 10, 23.2, 12.5, 29.0))
    add_body('REF_K230D_BOX', obb_temp(-42.3, 0, 124, 15.4, 64.3, 47.6))
    add_body('REF_K230D_Camera_FOV_Origin', cylinder_temp((-33.5, 0, 124), (-28.5, 0, 124), 4.5))

    # Packaging keep-out for the side USB cable and heat sink/air space.
    add_body('REF_K230D_USB_Keepout', obb_temp(-42, 39, 112, 22, 14, 14))
    add_body('REF_K230D_Heatsink_Keepout', obb_temp(-55, 0, 124, 10, 42, 32))

    # Return to parametric mode and republish the design-intent parameters. Fusion
    # discards user parameters while switching through direct-design mode.
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    add_parameter('upper_arm_length', '90 mm', 'mm', 'Shoulder axis to elbow axis')
    add_parameter('forearm_length', '80 mm', 'mm', 'Elbow axis to wrist axis')
    add_parameter('link_thickness', '8 mm', 'mm', 'FDM printed link thickness')
    add_parameter('link_width', '20 mm', 'mm', 'FDM printed link plate width')
    add_parameter('joint_bore', '4.4 mm', 'mm', 'Clearance bore for M4 shoulder bolts')
    add_parameter('print_clearance', '0.4 mm', 'mm', 'Nominal FDM sliding clearance')
    add_parameter('min_wall', '4 mm', 'mm', 'Minimum structural wall')
    add_parameter('base_size', '120 mm', 'mm', 'Square desktop footprint')
    add_parameter('k230d_width', '64.3 mm', 'mm', 'K230D BOX nominal width')
    add_parameter('k230d_height', '47.6 mm', 'mm', 'K230D BOX nominal height')
    add_parameter('k230d_depth', '15.4 mm', 'mm', 'K230D BOX nominal body depth')

    app.activeViewport.fit()
    adsk.doEvents()
    result['output'] = (
        'CyberArm printable prototype created: 11 PRINT bodies, 9 REF envelopes, '
        '90 mm upper arm, 80 mm forearm, fixed K230D mount.'
    )
except Exception:
    result['output'] = traceback.format_exc()
    raise
