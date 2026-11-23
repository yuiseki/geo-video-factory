"""Replace a PLATEAU LOD2 box with a hand-checked landmark mass (e.g. QFRONT's curved front).

The outline comes from OpenStreetMap (ODbL) and is smoothed with a Catmull-Rom curve except at
vertices marked sharp; PLATEAU faces inside the outline are deleted so the two never overlap.
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector

import blender_geo as bg


def delete_inside(objects: list, outline_xy: list, margin: float = 1.5) -> int:
    """Delete mesh faces whose centroid lies inside the outline (plan view, local meters)."""
    removed = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        mw = obj.matrix_world
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        doomed = []
        for face in bm.faces:
            c = mw @ face.calc_center_median()
            if bg.point_in_polygon((c.x, c.y), outline_xy, margin=margin):
                doomed.append(face)
        if doomed:
            bmesh.ops.delete(bm, geom=doomed, context="FACES")
            bm.to_mesh(obj.data)
            removed += len(doomed)
        bm.free()
    return removed


def glass_curtain_material(name: str = "GlassCurtain", mullion_m: float = 1.1, mullion_glow: float = 0.0,
                           floor_m: float = 4.6, warm_ranges: list | None = None,
                           warm_boost: float = 4.0) -> bpy.types.Material:
    """Dark reflective glass with light vertical mullions every `mullion_m` meters (UV u = meters)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.02, 0.025, 0.035, 1)
    bsdf.inputs["Metallic"].default_value = 0.3
    bsdf.inputs["Roughness"].default_value = 0.08
    uv = nodes.new("ShaderNodeUVMap")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(uv.outputs["UV"], sep.inputs[0])
    scaled = nodes.new("ShaderNodeMath")
    scaled.operation = "DIVIDE"
    scaled.inputs[1].default_value = mullion_m
    links.new(sep.outputs["X"], scaled.inputs[0])
    frac = nodes.new("ShaderNodeMath")
    frac.operation = "FRACT"
    links.new(scaled.outputs[0], frac.inputs[0])
    fin = nodes.new("ShaderNodeMath")
    fin.operation = "LESS_THAN"
    fin.inputs[1].default_value = 0.09
    links.new(frac.outputs[0], fin.inputs[0])
    # Floor lines every `floor_m` meters of height (UV v = meters).
    floor_scaled = nodes.new("ShaderNodeMath")
    floor_scaled.operation = "DIVIDE"
    floor_scaled.inputs[1].default_value = floor_m
    links.new(sep.outputs["Y"], floor_scaled.inputs[0])
    floor_frac = nodes.new("ShaderNodeMath")
    floor_frac.operation = "FRACT"
    links.new(floor_scaled.outputs[0], floor_frac.inputs[0])
    floor_line = nodes.new("ShaderNodeMath")
    floor_line.operation = "LESS_THAN"
    floor_line.inputs[1].default_value = 0.03
    links.new(floor_frac.outputs[0], floor_line.inputs[0])
    mullion = nodes.new("ShaderNodeMath")
    mullion.operation = "MAXIMUM"
    links.new(fin.outputs[0], mullion.inputs[0])
    links.new(floor_line.outputs[0], mullion.inputs[1])
    color = nodes.new("ShaderNodeMix")
    color.data_type = "RGBA"
    color.inputs["A"].default_value = (0.02, 0.025, 0.035, 1)
    color.inputs["B"].default_value = (0.55, 0.57, 0.6, 1)
    links.new(mullion.outputs[0], color.inputs["Factor"])
    links.new(color.outputs["Result"], bsdf.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.08
    rough.inputs["To Max"].default_value = 0.45
    links.new(mullion.outputs[0], rough.inputs["Value"])
    links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    if mullion_glow > 0:
        # Lit grid at night: cool cyan by default, warm gold on floodlit arc ranges.
        warm = None
        for s0, s1 in warm_ranges or []:
            above = nodes.new("ShaderNodeMath")
            above.operation = "GREATER_THAN"
            above.inputs[1].default_value = s0
            links.new(sep.outputs["X"], above.inputs[0])
            below = nodes.new("ShaderNodeMath")
            below.operation = "LESS_THAN"
            below.inputs[1].default_value = s1
            links.new(sep.outputs["X"], below.inputs[0])
            inside = nodes.new("ShaderNodeMath")
            inside.operation = "MULTIPLY"
            links.new(above.outputs[0], inside.inputs[0])
            links.new(below.outputs[0], inside.inputs[1])
            if warm is None:
                warm = inside
            else:
                union = nodes.new("ShaderNodeMath")
                union.operation = "MAXIMUM"
                links.new(warm.outputs[0], union.inputs[0])
                links.new(inside.outputs[0], union.inputs[1])
                warm = union
        tint = nodes.new("ShaderNodeMix")
        tint.data_type = "RGBA"
        tint.inputs["A"].default_value = (0.45, 0.8, 1.0, 1)
        tint.inputs["B"].default_value = (1.0, 0.72, 0.35, 1)
        strength = nodes.new("ShaderNodeMapRange")  # warm fins glow `warm_boost` times brighter
        strength.inputs["To Min"].default_value = mullion_glow
        strength.inputs["To Max"].default_value = mullion_glow * warm_boost
        if warm is not None:
            links.new(warm.outputs[0], tint.inputs["Factor"])
            links.new(warm.outputs[0], strength.inputs["Value"])
        else:
            tint.inputs["Factor"].default_value = 0.0
            strength.inputs["Value"].default_value = 0.0
        glow = nodes.new("ShaderNodeMath")
        glow.operation = "MULTIPLY"
        links.new(mullion.outputs[0], glow.inputs[0])
        links.new(strength.outputs["Result"], glow.inputs[1])
        links.new(tint.outputs["Result"], bsdf.inputs["Emission Color"])
        links.new(glow.outputs[0], bsdf.inputs["Emission Strength"])
    return mat


def extrude_outline(name: str, outline_xy: list, height: float, material) -> bpy.types.Object:
    """Walls and a flat roof from a closed outline; wall UVs are (arc length m, height m)."""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    bottoms = [bm.verts.new((x, y, 0.0)) for x, y in outline_xy]
    tops = [bm.verts.new((x, y, height)) for x, y in outline_xy]
    n = len(outline_xy)
    arc = 0.0
    for i in range(n):
        j = (i + 1) % n
        length = math.dist(outline_xy[i], outline_xy[j])
        face = bm.faces.new((bottoms[i], bottoms[j], tops[j], tops[i]))
        for loop, uv in zip(face.loops, ((arc, 0), (arc + length, 0), (arc + length, height), (arc, height))):
            loop[uv_layer].uv = uv
        arc += length
    roof = bm.faces.new(tops)
    for loop in roof.loops:
        loop[uv_layer].uv = (loop.vert.co.x, loop.vert.co.y)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _arc_range(landmark: dict, smooth_outline: list, spec: dict) -> tuple[float, float]:
    """Arc lengths for {"between": [i, j], "from": f0, "to": f1} on the smoothed outline."""
    arcs = bg.outline_vertex_arcs(smooth_outline)
    samples = landmark.get("samplesPerEdge", 8)
    a, b = (arcs[k * samples] for k in spec["between"])
    return a + (b - a) * spec["from"], a + (b - a) * spec["to"]


def add_band(name: str, outline_xy: list, s0: float, s1: float, z0: float, z1: float, image_path: str | None,
             strength: float, offset: float = 0.12, color=(1.0, 1.0, 1.0)) -> bpy.types.Object:
    """An emitting strip that follows the outline between arc lengths s0..s1 and heights z0..z1.

    It shows `image_path` when given, else a flat `color` (a lit screen with no usable footage).
    """
    points = bg.outline_band(outline_xy, s0, s1, offset=offset)
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    bottoms = [bm.verts.new((x, y, z0)) for (x, y), _u in points]
    tops = [bm.verts.new((x, y, z1)) for (x, y), _u in points]
    for i in range(len(points) - 1):
        u0, u1 = points[i][1], points[i + 1][1]
        face = bm.faces.new((bottoms[i], bottoms[i + 1], tops[i + 1], tops[i]))
        for loop, uv in zip(face.loops, ((u0, 0), (u1, 0), (u1, 1), (u0, 1))):
            loop[uv_layer].uv = uv
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = strength
    if image_path:
        image = nodes.new("ShaderNodeTexImage")
        image.image = bpy.data.images.load(image_path)
        image.interpolation = "Cubic"
        links.new(image.outputs["Color"], emission.inputs["Color"])
    else:
        emission.inputs["Color"].default_value = (*color, 1)
    links.new(emission.outputs[0], out.inputs["Surface"])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def add_landmark_bands(landmark: dict, smooth_outline: list, project_dir) -> int:
    """Bands placed by fractions of the arc between two outline vertices (e.g. QFRONT's front)."""
    for band in landmark.get("bands", []):
        s0, s1 = _arc_range(landmark, smooth_outline, band)
        add_band(f"{landmark['name']}_{band['name']}", smooth_outline, s0, s1, band["z"][0], band["z"][1],
                 str(project_dir / band["src"]) if band.get("src") else None, band.get("strength", 4.0),
                 color=tuple(band.get("color", (1.0, 1.0, 1.0))))
    return len(landmark.get("bands", []))


def add_landmark_lights(landmark: dict, smooth_outline: list) -> int:
    """Floodlight rows and small glowing marks (logo, neon) placed along the outline.

    Each entry: {between, from, to, z: [z0, z1], count, color, power, radius, glow}. Lights spread
    from (from, z0) to (to, z1), so a row can run along the wall or climb a corner.
    """
    placed = 0
    for index, row in enumerate(landmark.get("lights", [])):
        s0, s1 = _arc_range(landmark, smooth_outline, row)
        count = row.get("count", 1)
        color = tuple(row.get("color", (1.0, 0.95, 0.85)))
        glow = bpy.data.materials.new(f"{landmark['name']}Light{index:02d}")
        glow.use_nodes = True
        glow.node_tree.nodes.clear()
        emission = glow.node_tree.nodes.new("ShaderNodeEmission")
        emission.inputs["Color"].default_value = (*color, 1)
        emission.inputs["Strength"].default_value = row.get("glow", 60.0)
        output = glow.node_tree.nodes.new("ShaderNodeOutputMaterial")
        glow.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
        for k in range(count):
            t = k / (count - 1) if count > 1 else 0.5
            s = s0 + (s1 - s0) * t
            z = row["z"][0] + (row["z"][1] - row["z"][0]) * t
            (x, y), _u = bg.outline_band(smooth_outline, s, s + 0.01, offset=row.get("offset", 0.6))[0]
            bpy.ops.mesh.primitive_uv_sphere_add(radius=row.get("radius", 0.22), location=(x, y, z))
            bpy.context.active_object.data.materials.append(glow)
            if row.get("power", 0) > 0:
                light = bpy.data.lights.new(f"{landmark['name']}Lamp{index:02d}_{k:02d}", "POINT")
                light.energy = row["power"]
                light.color = color
                light.shadow_soft_size = 0.3
                lamp = bpy.data.objects.new(light.name, light)
                lamp.location = (x, y, z)
                bpy.context.scene.collection.objects.link(lamp)
            placed += 1
    return placed


def replace_with_landmark(plateau_objects: list, landmark: dict, origin: list, mullion_glow: float = 0.0) -> dict:
    """landmark: {name, outline: [[lng, lat], ...], sharp: [indices], height, samplesPerEdge}."""
    outline = [bg.local_meters(p, origin) for p in landmark["outline"]]
    if math.dist(outline[0], outline[-1]) < 0.01:
        outline = outline[:-1]
    removed = delete_inside(plateau_objects, outline, margin=landmark.get("deleteMargin", 1.5))
    smooth = bg.smooth_closed_outline(outline, landmark.get("samplesPerEdge", 8), set(landmark.get("sharp", [])))
    warm = [_arc_range(landmark, smooth, w) for w in landmark.get("warm", [])]
    material = glass_curtain_material(f"{landmark['name']}Glass", mullion_glow=mullion_glow,
                                      floor_m=landmark.get("floorM", 4.6), warm_ranges=warm)
    obj = extrude_outline(landmark["name"], smooth, landmark["height"], material)
    return {"object": obj, "removedFaces": removed, "outline": smooth}
