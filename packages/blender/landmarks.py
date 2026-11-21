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


def glass_curtain_material(name: str = "GlassCurtain", mullion_m: float = 1.1, mullion_glow: float = 0.0) -> bpy.types.Material:
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
    mullion = nodes.new("ShaderNodeMath")
    mullion.operation = "LESS_THAN"
    mullion.inputs[1].default_value = 0.09
    links.new(frac.outputs[0], mullion.inputs[0])
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
        # Lit fins, as QFRONT's vertical mullions glow at night.
        glow = nodes.new("ShaderNodeMath")
        glow.operation = "MULTIPLY"
        glow.inputs[1].default_value = mullion_glow
        links.new(mullion.outputs[0], glow.inputs[0])
        bsdf.inputs["Emission Color"].default_value = (0.9, 0.92, 1.0, 1)
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


def add_band(name: str, outline_xy: list, s0: float, s1: float, z0: float, z1: float, image_path: str,
             strength: float, offset: float = 0.12) -> bpy.types.Object:
    """An emitting image strip that follows the outline between arc lengths s0..s1 and heights z0..z1."""
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
    image = nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(image_path)
    image.interpolation = "Cubic"
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = strength
    links.new(image.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs[0], out.inputs["Surface"])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def add_landmark_bands(landmark: dict, smooth_outline: list, project_dir) -> int:
    """Bands placed by fractions of the arc between two outline vertices (e.g. QFRONT's front)."""
    samples = landmark.get("samplesPerEdge", 8)
    arcs = bg.outline_vertex_arcs(smooth_outline)
    for band in landmark.get("bands", []):
        a, b = (arcs[k * samples] for k in band["between"])
        s0, s1 = a + (b - a) * band["from"], a + (b - a) * band["to"]
        add_band(f"{landmark['name']}_{band['name']}", smooth_outline, s0, s1, band["z"][0], band["z"][1],
                 str(project_dir / band["src"]), band.get("strength", 4.0))
    return len(landmark.get("bands", []))


def replace_with_landmark(plateau_objects: list, landmark: dict, origin: list, mullion_glow: float = 0.0) -> dict:
    """landmark: {name, outline: [[lng, lat], ...], sharp: [indices], height, samplesPerEdge}."""
    outline = [bg.local_meters(p, origin) for p in landmark["outline"]]
    if math.dist(outline[0], outline[-1]) < 0.01:
        outline = outline[:-1]
    removed = delete_inside(plateau_objects, outline, margin=landmark.get("deleteMargin", 1.5))
    smooth = bg.smooth_closed_outline(outline, landmark.get("samplesPerEdge", 8), set(landmark.get("sharp", [])))
    obj = extrude_outline(landmark["name"], smooth, landmark["height"], glass_curtain_material(f"{landmark['name']}Glass", mullion_glow=mullion_glow))
    return {"object": obj, "removedFaces": removed, "outline": smooth}
