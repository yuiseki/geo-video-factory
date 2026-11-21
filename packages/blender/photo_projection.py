"""Camera projection of a real photo onto the scene geometry (the VFX "projection mapping" trick).

A projector (an empty at the photo's recovered camera pose) throws the photo onto building surfaces
as emission. Seen from near the projector the result is the photo itself, with real parallax for
small camera moves. Parts of the photo that hold transient things (people, cars, a raised phone)
are masked out by world height and by image rectangles; there the previous material shows through.
"""
from __future__ import annotations

import math

import bpy


def add_projector(location, tilt: float, bearing: float) -> bpy.types.Object:
    empty = bpy.data.objects.new("PhotoProjector", None)
    empty.location = location
    empty.rotation_euler = (math.radians(tilt), 0.0, -math.radians(bearing))
    bpy.context.scene.collection.objects.link(empty)
    return empty


def _math(nodes, links, op, a, b=None, value=None):
    node = nodes.new("ShaderNodeMath")
    node.operation = op
    links.new(a, node.inputs[0])
    if b is not None:
        links.new(b, node.inputs[1])
    elif value is not None:
        node.inputs[1].default_value = value
    return node.outputs[0]


def project_onto(materials: list, image_path: str, projector: bpy.types.Object, fov: float, width: int,
                 height: int, min_z: float = 2.6, masks: list | None = None, strength: float = 1.0) -> int:
    """Add the projected photo on top of each material; returns how many were changed.

    `fov` is the photo's vertical field of view in degrees; `masks` are [u0, v0, u1, v1] pixel rectangles
    of the photo (origin top-left) that must not be projected.
    """
    image = bpy.data.images.load(image_path, check_existing=True)
    half_tan = math.tan(math.radians(fov) / 2)
    changed = 0
    for mat in materials:
        if mat is None or not mat.use_nodes:
            continue
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        output = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
        if output is None or not output.inputs["Surface"].is_linked:
            continue
        original = output.inputs["Surface"].links[0].from_socket
        # Projector-space position of the surface point, with height clamped to `min_z`: below that
        # line (where the photo holds people) the facade colour just above is stretched downward.
        geometry = nodes.new("ShaderNodeNewGeometry")
        world = nodes.new("ShaderNodeSeparateXYZ")
        links.new(geometry.outputs["Position"], world.inputs[0])
        clamped_z = _math(nodes, links, "MAXIMUM", world.outputs["Z"], value=min_z)
        clamped = nodes.new("ShaderNodeCombineXYZ")
        links.new(world.outputs["X"], clamped.inputs["X"])
        links.new(world.outputs["Y"], clamped.inputs["Y"])
        links.new(clamped_z, clamped.inputs["Z"])
        relative = nodes.new("ShaderNodeVectorMath")
        relative.operation = "SUBTRACT"
        relative.inputs[1].default_value = tuple(projector.location)
        links.new(clamped.outputs[0], relative.inputs[0])
        local = nodes.new("ShaderNodeVectorRotate")
        local.rotation_type = "EULER_XYZ"
        local.invert = True
        local.inputs["Rotation"].default_value = tuple(projector.rotation_euler)
        links.new(relative.outputs[0], local.inputs["Vector"])
        sep = nodes.new("ShaderNodeSeparateXYZ")
        links.new(local.outputs["Vector"], sep.inputs[0])
        depth = _math(nodes, links, "MULTIPLY", sep.outputs["Z"], value=-1.0)  # projector looks down -Z
        sx = _math(nodes, links, "DIVIDE", sep.outputs["X"], depth)
        sy = _math(nodes, links, "DIVIDE", sep.outputs["Y"], depth)
        u = _math(nodes, links, "MULTIPLY_ADD", sx, None)
        u.node.inputs[1].default_value = height / (2 * half_tan * width)
        u.node.inputs[2].default_value = 0.5
        v = _math(nodes, links, "MULTIPLY_ADD", sy, None)
        v.node.inputs[1].default_value = 1 / (2 * half_tan)
        v.node.inputs[2].default_value = 0.5
        uv = nodes.new("ShaderNodeCombineXYZ")
        links.new(u, uv.inputs["X"])
        links.new(v, uv.inputs["Y"])
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "CLIP"
        tex.interpolation = "Cubic"
        links.new(uv.outputs[0], tex.inputs["Vector"])
        # Valid where in front of the projector, inside the frame, above people height, outside masks.
        valid = _math(nodes, links, "GREATER_THAN", depth, value=0.5)
        for comp, lo, hi in ((u, 0.0, 1.0), (v, 0.0, 1.0)):
            valid = _math(nodes, links, "MULTIPLY", valid, _math(nodes, links, "GREATER_THAN", comp, value=lo))
            valid = _math(nodes, links, "MULTIPLY", valid, _math(nodes, links, "LESS_THAN", comp, value=hi))
        for u0, v0, u1, v1 in masks or []:
            inside = _math(nodes, links, "GREATER_THAN", u, value=u0 / width)
            inside = _math(nodes, links, "MULTIPLY", inside, _math(nodes, links, "LESS_THAN", u, value=u1 / width))
            inside = _math(nodes, links, "MULTIPLY", inside, _math(nodes, links, "GREATER_THAN", v, value=1 - v1 / height))
            inside = _math(nodes, links, "MULTIPLY", inside, _math(nodes, links, "LESS_THAN", v, value=1 - v0 / height))
            outside = nodes.new("ShaderNodeMath")
            outside.operation = "SUBTRACT"
            outside.inputs[0].default_value = 1.0
            links.new(inside, outside.inputs[1])
            valid = _math(nodes, links, "MULTIPLY", valid, outside.outputs[0])
        # Stretched rows below `min_z` are dimmed, fading to 45 % at the ground.
        below = nodes.new("ShaderNodeMapRange")
        below.inputs["From Min"].default_value = 0.0
        below.inputs["From Max"].default_value = min_z
        below.inputs["To Min"].default_value = 0.45 * strength
        below.inputs["To Max"].default_value = strength
        links.new(world.outputs["Z"], below.inputs["Value"])
        emission = nodes.new("ShaderNodeEmission")
        links.new(below.outputs["Result"], emission.inputs["Strength"])
        links.new(tex.outputs["Color"], emission.inputs["Color"])
        mix = nodes.new("ShaderNodeMixShader")
        links.new(valid, mix.inputs["Fac"])
        links.new(original, mix.inputs[1])
        links.new(emission.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs["Surface"])
        changed += 1
    return changed
