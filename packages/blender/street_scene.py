"""Street-level dressing for Blender shots: wet ground, emissive billboards, street props, lights.

Mirrors the `plateauBuildings.groundPlane / billboards / streetProps` fields of the shot JSON
(see packages/renderer/src/types.ts), but lets Blender light the scene physically instead of
the additive glow sprites used in Three.js.
"""
from __future__ import annotations

import math
from pathlib import Path

import bpy

import blender_geo as bg

BILLBOARD_STRENGTH = 3.0


def _hex(color: str) -> tuple[float, float, float]:
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(c ** 2.2 for c in rgb)  # type: ignore[return-value]


def _plane(name: str, width: float, height: float) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    w, h = width / 2, height / 2
    mesh.from_pydata([(-w, -h, 0), (w, -h, 0), (w, h, 0), (-w, h, 0)], [], [(0, 1, 2, 3)])
    mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(mesh.uv_layers[0].data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = uv
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _material(name: str) -> tuple[bpy.types.Material, bpy.types.NodeTree]:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    return mat, tree


def _emission_material(name: str, color: tuple[float, float, float], strength: float) -> bpy.types.Material:
    mat, tree = _material(name)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*color, 1)
    emission.inputs["Strength"].default_value = strength
    tree.links.new(emission.outputs[0], out.inputs["Surface"])
    return mat


def add_ground(cfg: dict, project_dir: Path, origin: list[float]) -> None:
    gp = cfg.get("groundPlane")
    # Dark wet asphalt everywhere, so the far ground is not the world color.
    base = _plane("AsphaltBase", 4000, 4000)
    base.location = (0, 0, -0.02)
    mat, tree = _material("AsphaltBase")
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.012, 0.012, 0.016, 1)
    bsdf.inputs["Roughness"].default_value = 0.3
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    base.data.materials.append(mat)
    if not gp:
        return
    w, s, e, n = gp["bbox"]
    x0, y0 = bg.local_meters([w, s], origin)
    x1, y1 = bg.local_meters([e, n], origin)
    plane = _plane("GroundPlane", abs(x1 - x0), abs(y1 - y0))
    plane.location = ((x0 + x1) / 2, (y0 + y1) / 2, gp.get("altitudeM", 0.05))
    mat, tree = _material("WetGround")
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    image = tree.nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(str(project_dir / gp["src"]))
    image.interpolation = "Cubic"
    tint = tree.nodes.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.inputs["Factor"].default_value = 1.0
    tint.inputs["B"].default_value = (*([gp.get("brightness", 1.0)] * 3), 1)
    tree.links.new(image.outputs["Color"], tint.inputs["A"])
    tree.links.new(tint.outputs["Result"], bsdf.inputs["Base Color"])
    # Wet: puddles (low roughness) broken up by noise, so neon reflects in patches.
    coords = tree.nodes.new("ShaderNodeTexCoord")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 6.0
    tree.links.new(coords.outputs["Object"], noise.inputs["Vector"])
    ramp = tree.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.42
    ramp.inputs["From Max"].default_value = 0.58
    ramp.inputs["To Min"].default_value = gp.get("_wetMinRoughness", 0.06)
    ramp.inputs["To Max"].default_value = gp.get("_wetMaxRoughness", 0.45)
    tree.links.new(noise.outputs["Fac"], ramp.inputs["Value"])
    tree.links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    plane.data.materials.append(mat)


def add_billboards(cfg: dict, project_dir: Path, origin: list[float]) -> int:
    for index, bb in enumerate(cfg.get("billboards", [])):
        obj = _plane(f"Billboard{index:02d}", bb["widthM"], bb["heightM"])
        lx, ly = bg.local_meters(bb["center"], origin)
        obj.location = (lx, ly, bb["altitudeM"])
        obj.rotation_euler = bg.facing_euler(bb["bearing"])
        mat, tree = _material(f"Billboard{index:02d}")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        image = tree.nodes.new("ShaderNodeTexImage")
        image.image = bpy.data.images.load(str(project_dir / bb["src"]))
        image.interpolation = "Cubic"
        emission = tree.nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = BILLBOARD_STRENGTH * bb.get("glow", 1.0)
        tree.links.new(image.outputs["Color"], emission.inputs["Color"])
        transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
        mix = tree.nodes.new("ShaderNodeMixShader")
        tree.links.new(image.outputs["Alpha"], mix.inputs["Fac"])
        tree.links.new(transparent.outputs[0], mix.inputs[1])
        tree.links.new(emission.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs[0], out.inputs["Surface"])
        obj.data.materials.append(mat)
        # Lift off the facade slightly toward the street to avoid z-fighting with PLATEAU walls.
        b = math.radians(bb["bearing"])
        obj.location.x += math.sin(b) * 0.3
        obj.location.y += math.cos(b) * 0.3
    return len(cfg.get("billboards", []))


def _point_light(name: str, location, color, power: float, radius: float = 0.25) -> None:
    data = bpy.data.lights.new(name, "POINT")
    data.color = color
    data.energy = power
    data.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)


def _box(name: str, size, location, material, rotation_z: float = 0.0) -> None:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    obj.rotation_euler = (0, 0, rotation_z)
    obj.data.materials.append(material)


def add_crosswalks(crosswalks: list[dict], origin: list[float], z: float = 0.06) -> int:
    """White zebra paint from walking lines: [{name, line: [[lng, lat], ...], width}] (first -> last point)."""
    import bmesh

    paint, tree = _material("CrosswalkPaint")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.72, 0.72, 0.7, 1)
    bsdf.inputs["Roughness"].default_value = 0.5
    tree.links.new(bsdf.outputs[0], tree.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    bm = bmesh.new()
    bars = 0
    for crosswalk in crosswalks:
        a = bg.local_meters(crosswalk["line"][0], origin)
        b = bg.local_meters(crosswalk["line"][-1], origin)
        for quad in bg.crosswalk_stripes(a, b, crosswalk["width"], trim=crosswalk.get("trim", 0.8)):
            bm.faces.new([bm.verts.new((x, y, z)) for x, y in quad])
            bars += 1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for face in bm.faces:
        if face.normal.z < 0:
            face.normal_flip()
    mesh = bpy.data.meshes.new("Crosswalks")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(paint)
    obj = bpy.data.objects.new("Crosswalks", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return bars


def _box_matrix(box: dict, lift: float):
    """World matrix for a plane spanning a sign box: X along the wall, Y up, Z out of the wall."""
    from mathutils import Matrix, Vector

    u = Vector(box["axisU"])
    up = Vector((0.0, 0.0, 1.0))
    n = Vector(box["normal"])
    center = Vector(box["center"]) + n * lift
    return Matrix((
        (u.x, up.x, n.x, center.x),
        (u.y, up.y, n.y, center.y),
        (u.z, up.z, n.z, center.z),
        (0.0, 0.0, 0.0, 1.0),
    ))


def add_wall_billboards(entries: list[dict], project_dir: Path) -> int:
    """Real-photo sign images on wall-anchored boxes (see blender_geo.sign_box), emitting light."""
    for index, entry in enumerate(entries):
        box = entry["box"]
        obj = _plane(f"WallSign{index:02d}_{entry['name']}", 2 * box["halfWidth"], 2 * box["halfHeight"])
        obj.matrix_world = _box_matrix(box, lift=0.08)
        mat, tree = _material(f"WallSign{index:02d}")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        image = tree.nodes.new("ShaderNodeTexImage")
        image.image = bpy.data.images.load(str(project_dir / entry["src"]))
        image.interpolation = "Cubic"
        emission = tree.nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = entry.get("strength", 4.0)
        tree.links.new(image.outputs["Color"], emission.inputs["Color"])
        tree.links.new(emission.outputs[0], out.inputs["Surface"])
        obj.data.materials.append(mat)
    return len(entries)


def _mean_color(image_path: Path) -> tuple[float, float, float]:
    image = bpy.data.images.load(str(image_path), check_existing=True)
    probe = image.copy()
    probe.scale(8, 8)
    px = list(probe.pixels)
    bpy.data.images.remove(probe)
    n = len(px) // 4
    rgb = [sum(px[i * 4 + c] for i in range(n)) / n for c in range(3)]
    peak = max(rgb) or 1.0
    return tuple(c / peak for c in rgb)  # keep hue, normalise brightness


def add_wall_spill(boxes: list[dict], power_per_m2: float = 40.0, reach: float = 1.4) -> int:
    """Light that signs throw back onto the facade around them (and the street below).

    One area light per sign box, `reach` meters in front of it, slightly larger than the sign and
    aimed at the wall, tinted with the sign's mean colour (`color` in the box, default warm white).
    """
    from mathutils import Vector

    for index, box in enumerate(boxes):
        n = Vector(box["normal"])
        width, height = 2 * box["halfWidth"] * 1.6, 2 * box["halfHeight"] * 1.6
        data = bpy.data.lights.new(f"Spill{index:02d}", "AREA")
        data.shape = "RECTANGLE"
        data.size, data.size_y = width, height
        data.energy = box.get("powerPerM2", power_per_m2) * width * height
        data.color = box.get("color", (1.0, 0.9, 0.8))
        light = bpy.data.objects.new(f"Spill{index:02d}", data)
        light.location = Vector(box["center"]) + n * reach
        # Area lights shine along local -Z: aim at the wall, keep the rectangle upright.
        light.rotation_euler = (-n).to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.collection.objects.link(light)
    return len(boxes)


def sign_spill_boxes(entries: list[dict], sign_boxes: list[dict], project_dir: Path) -> list[dict]:
    """Boxes for wall spill: photo signs tinted by their image, other picked signs warm white."""
    out = []
    named = {e["name"] for e in entries}
    for entry in entries:
        box = dict(entry["box"])
        box["color"] = _mean_color(project_dir / entry["src"])
        out.append(box)
    out.extend(b for b in sign_boxes if b.get("name") not in named)
    return out


def add_facade_floodlights(box: dict, z: float, count: int = 9, power: float = 400.0) -> None:
    """A row of facade floodlights along a wall (as on QFRONT's shoulders), aimed down the wall."""
    from mathutils import Vector

    glow = _emission_material("Floodlight", (1.0, 0.95, 0.85), 80.0)
    u, n = Vector(box["axisU"]), Vector(box["normal"])
    for i in range(count):
        offset = (i / (count - 1) - 0.5) * 2 * box["halfWidth"] * 0.95
        p = Vector((box["center"][0], box["center"][1], z)) + u * offset + n * 0.6
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=p)
        bpy.context.active_object.data.materials.append(glow)
        data = bpy.data.lights.new(f"Flood{i:02d}", "SPOT")
        data.energy = power
        data.color = (1.0, 0.93, 0.82)
        data.spot_size = math.radians(70)
        data.spot_blend = 0.5
        light = bpy.data.objects.new(f"Flood{i:02d}", data)
        light.location = p + n * 0.3
        # Point mostly down, slightly into the wall.
        direction = (-n * 0.35 + Vector((0, 0, -1))).normalized()
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.collection.objects.link(light)


def add_signal_poles(poles: list[dict], origin: list[float], lamp_power: float = 1500.0) -> int:
    """Signal poles on the sidewalk with a red signal head and a pole-mounted street lamp.

    The lamp on every signal pole is an assumption to be checked against photos.
    """
    metal, tree = _material("SignalPoleMetal")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.03, 0.032, 0.035, 1)
    bsdf.inputs["Metallic"].default_value = 0.7
    bsdf.inputs["Roughness"].default_value = 0.35
    tree.links.new(bsdf.outputs[0], tree.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    red = _emission_material("SignalRed", (1.0, 0.05, 0.03), 40.0)
    lamp_glow = _emission_material("LampGlow", (1.0, 0.88, 0.72), 30.0)
    for index, pole in enumerate(poles):
        x, y = bg.local_meters(pole["lngLat"], origin)
        _box(f"SignalPole{index:02d}", (0.2, 0.2, 7.5), (x, y, 3.75), metal)
        _box(f"SignalHead{index:02d}", (1.2, 0.35, 0.4), (x, y, 5.4), metal)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.14, location=(x, y, 5.4))
        bpy.context.active_object.data.materials.append(red)
        _point_light(f"SignalGlow{index:02d}", (x, y, 5.2), (1.0, 0.1, 0.05), 25.0, 0.1)
        _box(f"LampHead{index:02d}", (0.8, 0.35, 0.12), (x, y, 7.6), lamp_glow)
        data = bpy.data.lights.new(f"PoleLamp{index:02d}", "SPOT")
        data.energy = lamp_power
        data.color = (1.0, 0.9, 0.78)
        data.spot_size = math.radians(140)
        data.spot_blend = 0.6
        data.shadow_soft_size = 0.3
        lamp = bpy.data.objects.new(f"PoleLamp{index:02d}", data)
        lamp.location = (x, y, 7.5)  # spot lights point down (-Z) by default
        bpy.context.scene.collection.objects.link(lamp)
    return len(poles)


def add_street_props(cfg: dict, origin: list[float]) -> int:
    pole_bsdf, tree = _material("PoleMetal")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.02, 0.022, 0.03, 1)
    bsdf.inputs["Metallic"].default_value = 0.6
    bsdf.inputs["Roughness"].default_value = 0.4
    tree.links.new(bsdf.outputs[0], tree.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    pole = pole_bsdf
    ground_z = cfg.get("facadeTextures", {}).get("groundZ", 0)
    for index, sp in enumerate(cfg.get("streetProps", [])):
        lx, ly = bg.local_meters(sp["center"], origin)
        z0 = sp.get("altitudeM", ground_z)
        h = sp.get("heightM", 6.2)
        color = _hex(sp.get("color", "#cfe6ff"))
        rot = math.radians(180 - sp.get("bearing", 0))
        kind = sp["kind"]
        if kind in ("lamp", "signal"):
            _box(f"Pole{index:02d}", (0.22, 0.22, h), (lx, ly, z0 + h / 2), pole)
        if kind == "lamp":
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.28, location=(lx, ly, z0 + h))
            bpy.context.active_object.data.materials.append(_emission_material(f"Bulb{index:02d}", color, 25.0))
            _point_light(f"Lamp{index:02d}", (lx, ly, z0 + h - 0.4), color, 900.0)
        elif kind == "signal":
            arm = sp.get("widthM", 2.8)
            dx, dy = math.cos(rot) * arm * 0.65, math.sin(rot) * arm * 0.65
            _box(f"SignalBox{index:02d}", (1.15, 0.42, 0.35), (lx + dx, ly + dy, z0 + h - 0.6), pole, rot)
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.16, location=(lx + dx, ly + dy, z0 + h - 0.6))
            bpy.context.active_object.data.materials.append(_emission_material(f"Signal{index:02d}", color, 60.0))
            _point_light(f"SignalLight{index:02d}", (lx + dx, ly + dy, z0 + h - 0.9), color, 60.0, 0.1)
        elif kind == "arch":
            span = sp.get("widthM", 8.5)
            for side in (-1, 1):
                _box(f"Pillar{index:02d}{side}", (0.45, 0.45, h),
                     (lx + math.cos(rot) * span / 2 * side, ly + math.sin(rot) * span / 2 * side, z0 + h / 2), pole, rot)
            _box(f"Arch{index:02d}", (span + 0.6, 0.55, 1.1), (lx, ly, z0 + h), _emission_material(f"ArchGlow{index:02d}", color, 6.0), rot)
        elif kind == "wash":
            # Light washing a facade: an area light just in front of it, aimed at the wall.
            w = sp.get("widthM", 14)
            b = math.radians(sp.get("bearing", 0))
            data = bpy.data.lights.new(f"Wash{index:02d}", "AREA")
            data.shape = "RECTANGLE"
            data.size = w
            data.size_y = 1.0
            data.color = color
            data.energy = 4000.0
            obj = bpy.data.objects.new(f"Wash{index:02d}", data)
            obj.location = (lx + math.sin(b) * 2.0, ly + math.cos(b) * 2.0, z0)
            # Area lights emit along local -Z: tilt down and toward the facade.
            obj.rotation_euler = (math.radians(-55), 0, math.radians(180) - b)
            bpy.context.scene.collection.objects.link(obj)
        elif kind == "kiosk":
            kw, kh = sp.get("widthM", 5.4), sp.get("heightM", 2.8)
            _box(f"Kiosk{index:02d}", (kw, 2.8, kh), (lx, ly, z0 + kh / 2), _emission_material(f"KioskGlow{index:02d}", (1.0, 0.75, 0.45), 1.5), rot)
            _box(f"KioskRoof{index:02d}", (kw + 0.6, 3.4, 0.28), (lx, ly, z0 + kh + 0.14), pole, rot)
            _point_light(f"KioskLight{index:02d}", (lx, ly, z0 + kh * 0.6), (1.0, 0.8, 0.6), 400.0, 1.0)
    return len(cfg.get("streetProps", []))
