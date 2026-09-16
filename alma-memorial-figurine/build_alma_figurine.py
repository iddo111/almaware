import bpy
import math
import os
from mathutils import Vector


ROOT = r"D:\CLAUDE\alma-memorial-figurine"
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        pass


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.metallic = metallic
    mat.roughness = roughness
    return mat


SKIN = material("Skin", (0.63, 0.32, 0.20), roughness=0.62)
SKIN_LIGHT = material("Skin highlight", (0.78, 0.46, 0.31), roughness=0.58)
HAIR = material("Dark wavy hair", (0.025, 0.014, 0.010), roughness=0.72)
DRESS = material("Black wrap dress", (0.018, 0.020, 0.024), roughness=0.78)
SHOE = material("Black shoes", (0.012, 0.012, 0.014), roughness=0.50)
BASE = material("Memorial base", (0.035, 0.038, 0.045), roughness=0.55)
EYE_WHITE = material("Eye white", (0.82, 0.78, 0.70), roughness=0.65)
EYE_DARK = material("Eyes and brows", (0.018, 0.010, 0.008), roughness=0.65)
LIP = material("Warm smile", (0.32, 0.075, 0.055), roughness=0.72)
LETTER = material("Lettering", (0.22, 0.14, 0.055), metallic=0.15, roughness=0.48)


def smooth(obj):
    if obj.type == "MESH":
        for p in obj.data.polygons:
            p.use_smooth = True
    return obj


def uv(name, loc, scale, mat, segments=64, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return smooth(obj)


def cylinder(name, loc, radius, depth, mat, vertices=96, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Soft printable edges", "BEVEL")
        mod.width = bevel
        mod.segments = 4
    return smooth(obj)


def cone(name, loc, r1, r2, depth, mat, vertices=128, bevel=1.2):
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices, radius1=r1, radius2=r2, depth=depth, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Soft fabric edge", "BEVEL")
        mod.width = bevel
        mod.segments = 4
    return smooth(obj)


def capsule(name, p1, p2, radius, mat, squash_y=1.0):
    p1, p2 = Vector(p1), Vector(p2)
    mid = (p1 + p2) / 2
    length = (p2 - p1).length
    obj = uv(name, mid, (radius, radius * squash_y, length / 2 + radius * 0.25), mat, 48, 24)
    direction = p2 - p1
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
    return obj


def curve_tube(name, points, bevel, mat):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 12
    data.bevel_depth = bevel
    data.bevel_resolution = 5
    data.use_fill_caps = True
    spl = data.splines.new("BEZIER")
    spl.bezier_points.add(len(points) - 1)
    for bp, co in zip(spl.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def add_text(text, loc, size, extrude, mat):
    data = bpy.data.curves.new("Base inscription", "FONT")
    data.body = text
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.extrude = extrude
    data.bevel_depth = 0.20
    data.bevel_resolution = 3
    obj = bpy.data.objects.new("ALMA inscription", data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.radians(90), 0, 0)
    obj.data.materials.append(mat)
    return obj


def build():
    reset_scene()

    # Stable low display base, sized to leave the open gesture visually dominant.
    cylinder("Base lower", (0, 0, 6), 43, 12, BASE, bevel=2.0)
    cylinder("Base upper", (0, 0, 13), 38.5, 5, BASE, bevel=1.5)
    add_text("ALMA", (0, -43.0, 9.0), 8.2, 0.85, LETTER)

    # Feet and legs. Slight asymmetry makes the stance feel warm rather than rigid.
    uv("Left shoe", (-14, -5, 23), (12.5, 23, 7.5), SHOE)
    uv("Right shoe", (14, -4, 23), (12.5, 23, 7.5), SHOE)
    capsule("Left calf", (-14, 0, 27), (-13, 0, 88), 12.0, SKIN, 0.88)
    capsule("Right calf", (14, 0, 27), (13, 0, 88), 12.0, SKIN, 0.88)
    uv("Left knee", (-13, -2, 88), (13.5, 12.5, 14), SKIN)
    uv("Right knee", (13, -2, 88), (13.5, 12.5, 14), SKIN)

    # Dress: closed printable volumes with a raised wrap line and soft folds.
    cone("Dress skirt", (0, 2, 119), 43, 31.5, 74, DRESS, bevel=1.6)
    uv("Dress torso", (0, 1, 171), (35, 24, 43), DRESS)
    curve_tube(
        "Wrap neckline",
        [(-24, -22.5, 191), (0, -25.5, 171), (24, -22.5, 191)],
        1.25,
        DRESS,
    )
    for x, y, z, sx in [
        (-22, -25.0, 126, 1.0),
        (-8, -28.0, 118, 1.0),
        (9, -27.0, 121, 1.0),
        (25, -24.0, 129, 1.0),
    ]:
        curve_tube(
            f"Dress fold {x}",
            [(x, y, z + 28), (x * 1.06, y - 1.2, z), (x * 1.15, y + 0.4, z - 27)],
            0.85 * sx,
            DRESS,
        )

    # Neck and mature face proportions.
    cylinder("Neck", (0, 1, 205), 12.5, 26, SKIN, bevel=2.2)
    uv("Head", (0, -2, 231), (27.5, 24.0, 34.0), SKIN)
    uv("Left cheek", (-12.0, -22.0, 225), (11.5, 5.0, 10.0), SKIN_LIGHT)
    uv("Right cheek", (12.0, -22.0, 225), (11.5, 5.0, 10.0), SKIN_LIGHT)
    uv("Nose bridge", (0, -24.2, 232), (4.7, 7.0, 10.0), SKIN_LIGHT, 48, 24)
    uv("Nose tip", (0, -30.0, 225.5), (6.2, 4.8, 5.0), SKIN_LIGHT, 48, 24)
    uv("Left ear", (-27.0, -1.5, 231), (4.2, 3.5, 8.0), SKIN)
    uv("Right ear", (27.0, -1.5, 231), (4.2, 3.5, 8.0), SKIN)

    # Eyes, brows, and the characteristic warm smile.
    for side in (-1, 1):
        x = 9.5 * side
        uv(f"Eye white {side}", (x, -24.9, 236.5), (5.6, 2.0, 2.6), EYE_WHITE, 48, 20)
        uv(f"Iris {side}", (x, -27.0, 236.2), (2.25, 1.1, 2.25), EYE_DARK, 40, 20)
        curve_tube(
            f"Eyebrow {side}",
            [(x - 6.0, -25.1, 244.2), (x, -27.0, 246.5), (x + 6.0, -25.0, 244.5)],
            1.35,
            EYE_DARK,
        )
    curve_tube(
        "Smile upper",
        [(-10.5, -27.2, 216.0), (0, -30.1, 211.2), (10.5, -27.2, 216.0)],
        1.65,
        LIP,
    )
    curve_tube(
        "Smile lower",
        [(-9.0, -27.0, 213.9), (0, -29.2, 209.8), (9.0, -27.0, 213.9)],
        1.25,
        LIP,
    )
    uv("Smile opening", (0, -28.1, 212.8), (7.8, 1.3, 2.3), EYE_DARK, 48, 20)

    # Dark, shoulder-length wavy hair kept close to the body for FDM strength.
    uv("Hair back", (0, 7.5, 233), (30.0, 24.0, 38.0), HAIR)
    uv("Hair crown", (0, 1.0, 255), (28.8, 23.0, 15.0), HAIR)
    for side in (-1, 1):
        sx = side
        curve_tube(
            f"Hair wave outer {side}",
            [(sx * 22, -2, 254), (sx * 30, 2, 230), (sx * 28, 4, 205)],
            7.0,
            HAIR,
        )
        curve_tube(
            f"Hair wave inner {side}",
            [(sx * 12, -17, 256), (sx * 23, -18, 236), (sx * 22, -15, 211)],
            5.0,
            HAIR,
        )

    # Open, welcoming arms. Elbows are gently lowered and hands turn toward the viewer.
    left_shoulder = (-31, -1, 189)
    right_shoulder = (31, -1, 189)
    left_elbow = (-79, -9, 178)
    right_elbow = (79, -9, 178)
    left_wrist = (-126, -19, 172)
    right_wrist = (126, -19, 172)
    capsule("Left upper arm", left_shoulder, left_elbow, 10.8, SKIN, 0.92)
    capsule("Right upper arm", right_shoulder, right_elbow, 10.8, SKIN, 0.92)
    uv("Left elbow", left_elbow, (11.3, 10.0, 11.0), SKIN)
    uv("Right elbow", right_elbow, (11.3, 10.0, 11.0), SKIN)
    capsule("Left forearm", left_elbow, left_wrist, 9.2, SKIN, 0.88)
    capsule("Right forearm", right_elbow, right_wrist, 9.2, SKIN, 0.88)

    for side, wrist in [(-1, left_wrist), (1, right_wrist)]:
        x, y, z = wrist
        palm = uv(f"Palm {side}", (x + side * 12, y - 2, z), (17, 7.2, 13.0), SKIN_LIGHT, 48, 24)
        palm.rotation_euler[1] = math.radians(-side * 8)
        # Four simplified, separated-but-thick fingers, angled up and toward the viewer.
        for i, dz in enumerate((-7.0, -2.5, 2.0, 6.5)):
            p1 = (x + side * 20, y - 2.0, z + dz)
            p2 = (x + side * (34 - i * 1.4), y - 4.5, z + dz + 1.0)
            capsule(f"Finger {side} {i}", p1, p2, 2.35 - i * 0.12, SKIN_LIGHT, 0.82)
        capsule(
            f"Thumb {side}",
            (x + side * 9, y - 5.0, z - 5.5),
            (x + side * 21, y - 8.0, z - 12.5),
            2.8,
            SKIN_LIGHT,
            0.88,
        )

    # Slight shoulder caps ensure a continuous silhouette at slicing time.
    uv("Left shoulder", left_shoulder, (13.8, 12.0, 14.0), SKIN)
    uv("Right shoulder", right_shoulder, (13.8, 12.0, 14.0), SKIN)

    # Use nearly the full K2 Plus bed while retaining a 7 mm total safety margin.
    for obj in bpy.context.scene.objects:
        if obj.type in {"MESH", "CURVE", "FONT"}:
            obj.location.x *= 1.043
            obj.scale.x *= 1.043


def setup_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.curvature_ridge_factor = 1.8
    scene.display.shading.curvature_valley_factor = 1.4
    scene.display.shading.background_type = "WORLD"
    scene.display.shading.background_color = (0.035, 0.040, 0.052)

    bpy.ops.object.camera_add(location=(0, -720, 245))
    cam = bpy.context.object
    cam.name = "Preview camera"
    cam.data.lens = 62
    direction = Vector((0, 0, 150)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    scene.render.filepath = os.path.join(OUT, "alma_figurine_preview_front.png")
    bpy.ops.render.render(write_still=True)

    cam.location = (380, -590, 265)
    direction = Vector((0, 0, 150)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(OUT, "alma_figurine_preview_3q.png")
    bpy.ops.render.render(write_still=True)


def export():
    printable = [
        o for o in bpy.context.scene.objects
        if o.type in {"MESH", "CURVE", "FONT"} and o.name not in {"Preview camera"}
    ]
    for o in printable:
        if o.type != "MESH":
            bpy.ops.object.select_all(action="DESELECT")
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.convert(target="MESH")
    bpy.ops.object.select_all(action="DESELECT")
    printable = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in printable:
        o.select_set(True)
    bpy.context.view_layer.objects.active = printable[0]

    stl_path = os.path.join(OUT, "ALMA_WELCOME_338MM.stl")
    bpy.ops.wm.stl_export(
        filepath=stl_path,
        export_selected_objects=True,
        apply_modifiers=True,
        ascii_format=False,
    )
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "ALMA_WELCOME_MASTER.blend"))

    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    triangles = 0
    for o in printable:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            mins.x, mins.y, mins.z = min(mins.x, w.x), min(mins.y, w.y), min(mins.z, w.z)
            maxs.x, maxs.y, maxs.z = max(maxs.x, w.x), max(maxs.y, w.y), max(maxs.z, w.z)
        triangles += sum(max(0, len(p.vertices) - 2) for p in o.data.polygons)

    report = os.path.join(OUT, "verification.txt")
    with open(report, "w", encoding="utf-8") as fh:
        dims = maxs - mins
        fh.write("ALMA WELCOME FIGURINE\n")
        fh.write(f"objects={len(printable)}\n")
        fh.write(f"triangles_approx={triangles}\n")
        fh.write(f"min_mm={mins.x:.3f},{mins.y:.3f},{mins.z:.3f}\n")
        fh.write(f"max_mm={maxs.x:.3f},{maxs.y:.3f},{maxs.z:.3f}\n")
        fh.write(f"dimensions_mm={dims.x:.3f},{dims.y:.3f},{dims.z:.3f}\n")
        fh.write("target_printer=Creality K2 Plus 350x350x350 mm\n")
        fh.write("pose=one-piece open-arm welcoming pose\n")
        fh.write("source_policy=only manually reviewed Alma-labelled archive references\n")


build()
setup_render()
export()
