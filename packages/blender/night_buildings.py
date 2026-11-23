"""Night look for photo-textured PLATEAU buildings in Blender.

The daytime aerial photo texture is dimmed, then two kinds of light are emitted *through* the
same texture so the real facade pattern stays visible:
- lit windows: world-space floor x bay cells on walls, a random share switched on
  (the same idea as the Three.js city shader's `uCityWindows`);
- storefronts: the ground-floor band of every wall, warm and always on.
"""
from __future__ import annotations

import bpy


def sign_mask_group(boxes: list[dict]) -> bpy.types.NodeTree:
    """Shader node group: 1 inside any sign box (see blender_geo.sign_box), else 0."""
    group = bpy.data.node_groups.new("SignMask", "ShaderNodeTree")
    group.interface.new_socket("Position", in_out="INPUT", socket_type="NodeSocketVector")
    group.interface.new_socket("Mask", in_out="OUTPUT", socket_type="NodeSocketFloat")
    nodes, links = group.nodes, group.links
    inp = nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    total = None
    for box in boxes:
        offset = nodes.new("ShaderNodeVectorMath")
        offset.operation = "SUBTRACT"
        offset.inputs[1].default_value = box["center"]
        links.new(inp.outputs["Position"], offset.inputs[0])
        inside = None
        for axis, half in ((box["axisU"], box["halfWidth"]), ((0.0, 0.0, 1.0), box["halfHeight"]),
                           (box["normal"], box["halfDepth"])):
            dot = nodes.new("ShaderNodeVectorMath")
            dot.operation = "DOT_PRODUCT"
            dot.inputs[1].default_value = axis
            links.new(offset.outputs[0], dot.inputs[0])
            absolute = nodes.new("ShaderNodeMath")
            absolute.operation = "ABSOLUTE"
            links.new(dot.outputs["Value"], absolute.inputs[0])
            less = nodes.new("ShaderNodeMath")
            less.operation = "LESS_THAN"
            less.inputs[1].default_value = half
            links.new(absolute.outputs[0], less.inputs[0])
            if inside is None:
                inside = less
            else:
                both = nodes.new("ShaderNodeMath")
                both.operation = "MULTIPLY"
                links.new(inside.outputs[0], both.inputs[0])
                links.new(less.outputs[0], both.inputs[1])
                inside = both
        if total is None:
            total = inside
        else:
            union = nodes.new("ShaderNodeMath")
            union.operation = "MAXIMUM"
            links.new(total.outputs[0], union.inputs[0])
            links.new(inside.outputs[0], union.inputs[1])
            total = union
    if total is not None:
        links.new(total.outputs[0], out.inputs["Mask"])
    return group


def _find_base_texture(tree: bpy.types.NodeTree):
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None or not bsdf.inputs["Base Color"].is_linked:
        return bsdf, None
    return bsdf, bsdf.inputs["Base Color"].links[0].from_socket


def apply_night(
    objects: list,
    dim: float = 0.10,
    window_share: float = 0.0,
    window_strength: float = 1.6,
    storefront_height: float = 4.5,
    storefront_strength: float = 2.5,
    floor_height: float = 3.4,
    bay_width: float = 12.0,
    sign_strength: float = 6.0,
    sign_saturation: tuple[float, float] = (0.35, 0.65),
    sign_boxes: list[dict] | None = None,
) -> int:
    """Turn the imported PLATEAU materials into night materials; returns how many were changed."""
    done = set()
    sign_group = sign_mask_group(sign_boxes) if sign_boxes else None
    for obj in objects:
        if obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            if mat is None or mat.name in done or not mat.use_nodes:
                continue
            tree = mat.node_tree
            bsdf, color = _find_base_texture(tree)
            if bsdf is None or color is None:
                continue
            nodes, links = tree.nodes, tree.links

            # Dim the daylight photo.
            dimmer = nodes.new("ShaderNodeMix")
            dimmer.data_type = "RGBA"
            dimmer.blend_type = "MULTIPLY"
            dimmer.inputs["Factor"].default_value = 1.0
            dimmer.inputs["B"].default_value = (dim, dim, dim * 1.1, 1)
            links.new(color, dimmer.inputs["A"])
            links.new(dimmer.outputs["Result"], bsdf.inputs["Base Color"])

            geometry = nodes.new("ShaderNodeNewGeometry")
            # Walls only: |normal.z| small.
            normal = nodes.new("ShaderNodeSeparateXYZ")
            links.new(geometry.outputs["Normal"], normal.inputs[0])
            abs_nz = nodes.new("ShaderNodeMath")
            abs_nz.operation = "ABSOLUTE"
            links.new(normal.outputs["Z"], abs_nz.inputs[0])
            wall = nodes.new("ShaderNodeMath")
            wall.operation = "LESS_THAN"
            wall.inputs[1].default_value = 0.35
            links.new(abs_nz.outputs[0], wall.inputs[0])

            # Window cells: floor(position / (bay, bay, floor)) -> random value per cell.
            scale = nodes.new("ShaderNodeVectorMath")
            scale.operation = "DIVIDE"
            scale.inputs[1].default_value = (bay_width, bay_width, floor_height)
            links.new(geometry.outputs["Position"], scale.inputs[0])
            cell = nodes.new("ShaderNodeVectorMath")
            cell.operation = "FLOOR"
            links.new(scale.outputs[0], cell.inputs[0])
            noise = nodes.new("ShaderNodeTexWhiteNoise")
            noise.noise_dimensions = "3D"
            links.new(cell.outputs[0], noise.inputs["Vector"])
            lit = nodes.new("ShaderNodeMath")
            lit.operation = "LESS_THAN"
            lit.inputs[1].default_value = window_share
            links.new(noise.outputs["Value"], lit.inputs[0])

            # Above the storefront band only.
            position = nodes.new("ShaderNodeSeparateXYZ")
            links.new(geometry.outputs["Position"], position.inputs[0])
            upper = nodes.new("ShaderNodeMath")
            upper.operation = "GREATER_THAN"
            upper.inputs[1].default_value = storefront_height
            links.new(position.outputs["Z"], upper.inputs[0])
            ground = nodes.new("ShaderNodeMath")
            ground.operation = "LESS_THAN"
            ground.inputs[1].default_value = storefront_height
            links.new(position.outputs["Z"], ground.inputs[0])

            window_mask = nodes.new("ShaderNodeMath")
            window_mask.operation = "MULTIPLY"
            links.new(lit.outputs[0], window_mask.inputs[0])
            links.new(upper.outputs[0], window_mask.inputs[1])
            window_strength_node = nodes.new("ShaderNodeMath")
            window_strength_node.operation = "MULTIPLY"
            window_strength_node.inputs[1].default_value = window_strength
            links.new(window_mask.outputs[0], window_strength_node.inputs[0])

            store_strength = nodes.new("ShaderNodeMath")
            store_strength.operation = "MULTIPLY"
            store_strength.inputs[1].default_value = storefront_strength
            links.new(ground.outputs[0], store_strength.inputs[0])

            total = nodes.new("ShaderNodeMath")
            total.operation = "ADD"
            links.new(window_strength_node.outputs[0], total.inputs[0])
            links.new(store_strength.outputs[0], total.inputs[1])
            # Signs and screens already baked into the photo: saturated, not too dark -> glow.
            hsv = nodes.new("ShaderNodeSeparateColor")
            hsv.mode = "HSV"
            links.new(color, hsv.inputs["Color"])
            saturated = nodes.new("ShaderNodeMapRange")
            saturated.inputs["From Min"].default_value = sign_saturation[0]
            saturated.inputs["From Max"].default_value = sign_saturation[1]
            links.new(hsv.outputs["Green"], saturated.inputs["Value"])
            bright = nodes.new("ShaderNodeMapRange")
            bright.inputs["From Min"].default_value = 0.25
            bright.inputs["From Max"].default_value = 0.55
            links.new(hsv.outputs["Blue"], bright.inputs["Value"])
            sign = nodes.new("ShaderNodeMath")
            sign.operation = "MULTIPLY"
            links.new(saturated.outputs["Result"], sign.inputs[0])
            links.new(bright.outputs["Result"], sign.inputs[1])
            if sign_group is not None:
                # Picked sign boxes on real walls replace the saturation guess.
                sign = nodes.new("ShaderNodeGroup")
                sign.node_tree = sign_group
                links.new(geometry.outputs["Position"], sign.inputs["Position"])
            sign_power = nodes.new("ShaderNodeMath")
            sign_power.operation = "MULTIPLY"
            sign_power.inputs[1].default_value = sign_strength
            links.new(sign.outputs[0], sign_power.inputs[0])
            with_signs = nodes.new("ShaderNodeMath")
            with_signs.operation = "ADD"
            links.new(total.outputs[0], with_signs.inputs[0])
            links.new(sign_power.outputs[0], with_signs.inputs[1])
            total = with_signs

            on_wall = nodes.new("ShaderNodeMath")
            on_wall.operation = "MULTIPLY"
            links.new(total.outputs[0], on_wall.inputs[0])
            links.new(wall.outputs[0], on_wall.inputs[1])

            # Light passes through the photo: squaring it keeps bright glass glowing and frames dark,
            # and each lit floor gets its own warm-to-cool interior tint.
            squared = nodes.new("ShaderNodeMix")
            squared.data_type = "RGBA"
            squared.blend_type = "MULTIPLY"
            squared.inputs["Factor"].default_value = 1.0
            links.new(color, squared.inputs["A"])
            links.new(color, squared.inputs["B"])
            tint = nodes.new("ShaderNodeMix")
            tint.data_type = "RGBA"
            tint.inputs["A"].default_value = (1.0, 0.72, 0.45, 1)
            tint.inputs["B"].default_value = (0.85, 0.92, 1.0, 1)
            links.new(noise.outputs["Value"], tint.inputs["Factor"])
            warm = nodes.new("ShaderNodeMix")
            warm.data_type = "RGBA"
            warm.blend_type = "MULTIPLY"
            warm.inputs["Factor"].default_value = 1.0
            links.new(squared.outputs["Result"], warm.inputs["A"])
            links.new(tint.outputs["Result"], warm.inputs["B"])
            # Signs keep their own colour; lit floors get the interior tint.
            emission_color = nodes.new("ShaderNodeMix")
            emission_color.data_type = "RGBA"
            emission_color.clamp_factor = True
            links.new(sign.outputs[0], emission_color.inputs["Factor"])
            links.new(warm.outputs["Result"], emission_color.inputs["A"])
            links.new(color, emission_color.inputs["B"])
            links.new(emission_color.outputs["Result"], bsdf.inputs["Emission Color"])
            links.new(on_wall.outputs[0], bsdf.inputs["Emission Strength"])
            done.add(mat.name)
    return len(done)
