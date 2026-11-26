"""Build the world-model scene on PLATEAU++ and save it as a .blend (Blender, run with -b -P).

usage: blender -b --factory-startup -P pp_scene.py -- <out.blend> <PLATEAU++ manifest.json>
           [--radius=700] [--centre=10,-20] [--proxy-lift=33.5] [--dim=1.0] [--sky=r,g,b] [--sun=3.0]
           [--atlas=<model.obj>,...] [--ground=<model.obj>,...]
           [--water=<metres above the crossing>] [--water-colour=r,g,b] [--water-roughness=0.03] [--ripple=0.04]
           [--origin=lon,lat] [--ground-z=52.8]

--origin moves the local frame away from the Shibuya crossing (the default) and --ground-z gives that place's
ground on the ellipsoid, which the road plane under everything and --water start from.

--water floods the streets with a still, mirroring lake that many metres above the crossing's ground
(1.5 hides the smeared bottom of the walls left where people and cars were removed).

The buildings are PLATEAU++ (packages/pipeline: PLATEAU models with their own photo textures, filled-in
buildings where PLATEAU has none), every tile whose extent (its region) comes within --radius metres of --centre.
The photo atlases of this directory (build_atlas.py) lie on top of them, 0.15 m out along each face,
showing only the texels a photo saw (seen.png > 0): where no photo looked, PLATEAU++ shows through
instead of the atlas's grey fill. Photo textures (PLATEAU's and the atlases') are drawn unlit, as
orbit_render.py does: the photos carry their own light. --dim scales the PLATEAU++ photos (taken by
day) for a night layer; the atlases and grounds are already of their own time layer and are not dimmed.

Coordinates: local east/north/up metres around (139.7005, 35.6595), heights on the ellipsoid as
the PLATEAU 3D Tiles give them (ground about 52.8 at the crossing). Filled-in tiles (frame "enu") are
built on the GSI DEM around the manifest centre; --proxy-lift puts them on the same ground.
"""
import math
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # packages/pipeline
from buildings import blender_geo as bg  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
ORIGIN = tuple(float(v) for v in opts.get("origin", "139.7005,35.6595").split(","))
GROUND_Z = float(opts.get("ground-z", 52.8))   # the ground on the ellipsoid, as the PLATEAU tiles give it (Shibuya crossing: 52.8)
out_blend, manifest_path = [Path(a) for a in argv if not a.startswith("--")][:2]
radius = float(opts.get("radius", 700))
cx, cy = (float(v) for v in opts.get("centre", "10,-20").split(","))
lift = float(opts.get("proxy-lift", 33.5))
dim = float(opts.get("dim", 1.0))
cache = Path(tempfile.mkdtemp(prefix="pp-scene-glb-"))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def unlit(mat, strength):
    """Photo-textured material -> emission of its texture (no second lighting of a photo)."""
    nt = mat.node_tree
    tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
    if tex is None:
        return False
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return True


import json  # noqa: E402

manifest = json.loads(manifest_path.read_text())
mcx, mcy = bg.local_meters(manifest["center"], ORIGIN)
plain = bpy.data.materials.new("pp-untextured")
plain.use_nodes = True
plain.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.5, 0.5, 0.52, 1)
plain.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
tiles = 0
for tile in manifest["tiles"]:
    if tile.get("kind") == "city-shadow":
        continue
    enu = tile.get("frame") == "enu"
    if enu:
        matrix = Matrix.Translation((mcx, mcy, lift))
    else:
        m = bg.plateau_tile_matrix(tile["rtc"], ORIGIN, 0.0)
        reg = tile.get("region")
        if isinstance(reg, list) and len(reg) >= 4:
            # by the tile's own extent: some tiles carry RTC [0, 0, 0] and keep their place in node transforms
            # (Taito ward), so their RTC says nothing about where they are
            tx, ty = bg.local_meters((math.degrees((reg[0] + reg[2]) / 2), math.degrees((reg[1] + reg[3]) / 2)), ORIGIN)
            half = math.hypot(*(a - b for a, b in zip(bg.local_meters((math.degrees(reg[2]), math.degrees(reg[3])), ORIGIN),
                                                    bg.local_meters((math.degrees(reg[0]), math.degrees(reg[1])), ORIGIN)))) / 2
            if math.hypot(tx - cx, ty - cy) - half > radius:
                continue
        elif math.hypot(m[0][3] - cx, m[1][3] - cy) > radius:
            continue
        matrix = Matrix(m)
    source = manifest_path.parent / tile["glb"]
    strict = cache / source.name
    strict.write_bytes(bg.strict_glb(source.read_bytes()))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(strict))
    for obj in set(bpy.data.objects) - before:
        if obj.parent is None:
            obj.matrix_world = matrix @ obj.matrix_world
        if obj.type != "MESH":
            continue
        obj["pp_kind"] = tile.get("kind", "plateau")
        for i, mat in enumerate(obj.data.materials):
            if mat is None or not mat.use_nodes or not unlit(mat, dim):
                if not enu:
                    obj.data.materials[i] = plain
    tiles += 1
print("PLATEAU++ tiles", tiles)

for path in [p for p in opts.get("atlas", "").split(",") if p]:
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    seen_path = Path(path).parent / "seen.png"
    for obj in set(bpy.data.objects) - before:
        obj.name = "atlas-" + Path(path).parent.name
        for poly in obj.data.polygons:          # faces are unwelded: each moves out along its own normal
            for vi in poly.vertices:
                obj.data.vertices[vi].co += poly.normal * 0.15
        for mat in obj.data.materials:
            nt = mat.node_tree
            tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
            out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
            em = nt.nodes.new("ShaderNodeEmission")      # the atlas is of its own time layer: never dimmed
            nt.links.new(tex.outputs["Color"], em.inputs["Color"])
            seen = nt.nodes.new("ShaderNodeTexImage")
            seen.image = bpy.data.images.load(str(seen_path))
            seen.image.colorspace_settings.name = "Non-Color"
            seen.interpolation = "Closest"
            nt.links.new(tex.inputs["Vector"].links[0].from_socket if tex.inputs["Vector"].links else
                         nt.nodes.new("ShaderNodeTexCoord").outputs["UV"], seen.inputs["Vector"])
            gt = nt.nodes.new("ShaderNodeMath")
            gt.operation = "GREATER_THAN"
            gt.inputs[1].default_value = 0.05
            nt.links.new(seen.outputs["Color"], gt.inputs[0])
            mix = nt.nodes.new("ShaderNodeMixShader")
            nt.links.new(gt.outputs[0], mix.inputs["Fac"])
            nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
            nt.links.new(em.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], out.inputs["Surface"])
            mat.use_backface_culling = False

for path in [p for p in opts.get("ground", "").split(",") if p]:
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    for obj in set(bpy.data.objects) - before:
        obj.name = "ground-" + Path(path).parent.name
        for mat in obj.data.materials:
            unlit(mat, 1.0)

# a road-coloured plane under everything, so no sky shows below the ground models
bpy.ops.mesh.primitive_plane_add(size=6000, location=(cx, cy, GROUND_Z - 0.25))
road = bpy.data.materials.new("road")
road.use_nodes = True
road.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.16, 0.16, 0.17, 1)
road.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
bpy.context.object.data.materials.append(road)

if "water" in opts:
    # a still lake over the streets: hides the bottom metres of the walls, where removed people and cars
    # leave smears, and mirrors the city above (EEVEE raytraced reflections)
    level = GROUND_Z + float(opts["water"])
    bpy.ops.mesh.primitive_plane_add(size=2 * radius + 400, location=(cx, cy, level))
    water = bpy.data.materials.new("water")
    water.use_nodes = True
    nt = water.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*(float(v) for v in opts.get("water-colour", "0.02,0.035,0.04").split(",")), 1)
    bsdf.inputs["Roughness"].default_value = float(opts.get("water-roughness", 0.03))
    bsdf.inputs["IOR"].default_value = 1.33
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.6
    noise.inputs["Detail"].default_value = 4.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = float(opts.get("ripple", 0.04))
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.context.object.data.materials.append(water)
    bpy.context.object.name = "water"
    sc.eevee.use_raytracing = True
    sc.eevee.ray_tracing_options.resolution_scale = "1"
    print("water at", level)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = float(opts.get("sun", 3.0))
sun.data.use_shadow = False
sun.rotation_euler = (math.radians(50), 0, math.radians(200))
sc.collection.objects.link(sun)
sc.world = bpy.data.worlds.new("sky")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (*(float(v) for v in opts.get("sky", "0.62,0.74,0.9").split(",")), 1)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.clip_start, cam.data.clip_end = 0.3, 4000
sc.collection.objects.link(cam)
sc.camera = cam
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.render.image_settings.file_format = "JPEG"
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend.resolve()))
print("saved", out_blend)
