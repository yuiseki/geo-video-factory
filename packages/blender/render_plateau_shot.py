"""Render one frame of a geo-video-factory shot JSON with Blender (spike).

Run inside Blender:
  blender -b --factory-startup -P packages/blender/render_plateau_shot.py -- \
    --shot <shot.json> --project-dir <dir that shot paths are relative to> \
    --out <frame.png> [--engine EEVEE|CYCLES] [--t 0.0] [--samples 64]

Geometry and camera math live in packages/pipeline/blender_geo.py (unit tested without bpy).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_geo as bg  # noqa: E402
import street_scene  # noqa: E402

GLB_CACHE = Path(tempfile.mkdtemp(prefix="blender-shot-glb-"))


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--shot", required=True)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--engine", default="EEVEE", choices=["EEVEE", "CYCLES"])
    parser.add_argument("--t", type=float, default=0.0, help="normalized time within the first shot")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--radius", type=float, default=450.0, help="tile radius around the camera in meters")
    parser.add_argument("--save-blend", default=None)
    parser.add_argument("--buildings-only", action="store_true")
    parser.add_argument("--clay", action="store_true", help="diagnostic: grey buildings in daylight")
    parser.add_argument("--no-dressing", action="store_true", help="skip billboards and street props")
    parser.add_argument("--daylight", action="store_true", help="diagnostic: textured buildings in daylight")
    parser.add_argument("--manifest", default=None, help="override plateauBuildings.manifest (project-relative)")
    parser.add_argument("--ground-src", default=None, help="diagnostic: replace the ground image (project-relative)")
    parser.add_argument("--ground-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    parser.add_argument("--wet-roughness", type=float, nargs=2, default=[0.06, 0.45])
    parser.add_argument("--ground-fill", type=float, default=0.0, help="overhead area light power in W")
    parser.add_argument("--exposure", type=float, default=0.0)
    parser.add_argument("--sky-strength", type=float, default=0.6)
    parser.add_argument("--bloom", type=float, default=0.6, help="compositor glare strength, 0 disables")
    eye = parser.add_argument_group("street-level camera (overrides the shot's MapLibre keys)")
    eye.add_argument("--eye", type=float, nargs=3, metavar=("LNG", "LAT", "HEIGHT_M"))
    eye.add_argument("--bearing", type=float, default=0.0)
    eye.add_argument("--tilt", type=float, default=90.0, help="0 looks down, 90 looks at the horizon")
    eye.add_argument("--fov", type=float, default=None, help="vertical field of view in degrees")
    eye.add_argument("--shift-px", type=float, default=0.0, help="vertical lens shift; positive lowers the horizon")
    return parser.parse_args(argv)


def reset_scene() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def import_plateau(spec: dict, project_dir: Path, origin: list[float], camera_xy: tuple[float, float], radius: float) -> int:
    cfg = spec["plateauBuildings"]
    manifest_path = project_dir / cfg["manifest"]
    manifest = json.loads(manifest_path.read_text())
    height_offset = float(cfg.get("heightOffset", 0))
    count = 0
    for tile in manifest["tiles"]:
        matrix = bg.plateau_tile_matrix(tile["rtc"], origin, height_offset)
        tx, ty = matrix[0][3], matrix[1][3]
        if math.hypot(tx - camera_xy[0], ty - camera_xy[1]) > radius:
            continue
        source = manifest_path.parent / tile["glb"]
        strict = GLB_CACHE / source.name
        strict.write_bytes(bg.strict_glb(source.read_bytes()))
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(strict))
        new_objects = [obj for obj in bpy.data.objects if obj not in before]
        tile_matrix = Matrix(matrix)
        for obj in new_objects:
            if obj.parent is None:
                obj.matrix_world = tile_matrix @ obj.matrix_world
        count += 1
    return count


def setup_camera(scene: bpy.types.Scene, spec: dict, origin: list[float], args: argparse.Namespace) -> bpy.types.Object:
    fov = args.fov if args.fov is not None else spec.get("fov", 36.87)
    if args.eye:
        cam = bg.eye_camera(args.eye, bearing=args.bearing, tilt=args.tilt, fov=fov, origin=origin)
    else:
        key = bg.interpolate_keys(spec["shots"][0]["keys"], args.t)
        cam = bg.maplibre_camera(
            center=key["center"], zoom=key["zoom"], pitch=key["pitch"], bearing=key["bearing"],
            fov=fov, height_px=spec["height"], origin=origin,
        )
    data = bpy.data.cameras.new("ShotCamera")
    data.sensor_fit = "VERTICAL"
    data.angle_y = cam["fov_vertical"]
    # Blender's shift is a fraction of the larger frame side; positive moves the frame up.
    data.shift_y = args.shift_px / max(spec["width"], spec["height"])
    data.clip_start = 0.1
    data.clip_end = 5000
    obj = bpy.data.objects.new("ShotCamera", data)
    scene.collection.objects.link(obj)
    obj.location = cam["location"]
    obj.rotation_euler = cam["rotation_euler"]
    scene.camera = obj
    return obj


def setup_world(scene: bpy.types.Scene, spec: dict, strength: float) -> None:
    world = bpy.data.worlds.new("Night")
    world.use_nodes = True
    sky = spec.get("sky", {}).get("horizon-color", "#181329")
    rgb = [int(sky[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (*[c ** 2.2 for c in rgb], 1)
    background.inputs["Strength"].default_value = strength
    scene.world = world


def setup_render(scene: bpy.types.Scene, spec: dict, engine: str, samples: int, out: str) -> None:
    scene.render.resolution_x = spec["width"]
    scene.render.resolution_y = spec["height"]
    scene.render.resolution_percentage = 100
    scene.render.filepath = out
    scene.render.image_settings.file_format = "PNG"
    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = True
        scene.cycles.device = "GPU"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.seed = 0
    else:
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = samples
        scene.eevee.use_raytracing = True
        scene.eevee.use_shadows = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"


def setup_bloom(scene: bpy.types.Scene, strength: float) -> None:
    """Neon bloom with the compositor Glare node (Blender 5 compositing node groups)."""
    if strength <= 0:
        return
    tree = bpy.data.node_groups.new("ShotCompositor", "CompositorNodeTree")
    scene.compositing_node_group = tree
    layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    output = tree.nodes.new("NodeGroupOutput")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Threshold"].default_value = 0.8
    glare.inputs["Strength"].default_value = strength
    glare.inputs["Size"].default_value = 0.6
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], output.inputs[0])


def apply_clay(scene: bpy.types.Scene, plateau_objects: list) -> None:
    """Diagnostic look: grey PLATEAU buildings under a daylight sun, to judge geometry alone."""
    clay = bpy.data.materials.new("Clay")
    clay.use_nodes = True
    bsdf = clay.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.55, 0.55, 0.55, 1)
    bsdf.inputs["Roughness"].default_value = 0.9
    for obj in plateau_objects:
        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(clay)
    apply_daylight(scene)


def apply_daylight(scene: bpy.types.Scene) -> None:
    """Diagnostic light: a daylight sun and a bright sky, to inspect geometry and textures."""
    sun = bpy.data.lights.new("DiagnosticSun", "SUN")
    sun.energy = 3.0
    sun.angle = math.radians(3)
    sun_obj = bpy.data.objects.new("DiagnosticSun", sun)
    sun_obj.rotation_euler = (math.radians(40), 0, math.radians(-35))
    scene.collection.objects.link(sun_obj)
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.45, 0.5, 0.6, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0


def main() -> None:
    args = parse_args()
    spec = json.loads(Path(args.shot).read_text())
    project_dir = Path(args.project_dir)
    scene = reset_scene()
    if args.manifest:
        spec["plateauBuildings"]["manifest"] = args.manifest
    origin = list(json.loads((project_dir / spec["plateauBuildings"]["manifest"]).read_text())["center"])
    camera = setup_camera(scene, spec, origin, args)
    started = time.time()
    before = set(bpy.data.objects)
    tiles = import_plateau(spec, project_dir, origin, (camera.location.x, camera.location.y), args.radius)
    plateau_objects = [obj for obj in bpy.data.objects if obj not in before]
    print(f"[blender-shot] imported {tiles} tiles in {time.time() - started:.1f}s", flush=True)
    cfg = spec["plateauBuildings"]
    if not args.buildings_only:
        if args.ground_src:
            # Diagnostic: lay an untouched aerial photo (e.g. the raw GSI mosaic) as the ground.
            cfg["groundPlane"] = {"src": args.ground_src, "bbox": args.ground_bbox, "altitudeM": 0.04, "brightness": 1.0}
        if cfg.get("groundPlane"):
            cfg["groundPlane"]["_wetMinRoughness"] = args.wet_roughness[0]
            cfg["groundPlane"]["_wetMaxRoughness"] = args.wet_roughness[1]
        street_scene.add_ground(cfg, project_dir, origin)
        if args.ground_fill > 0:
            # Soft overhead "street light" fill so the crosswalk paint reads, like a long exposure.
            heading = -camera.rotation_euler.z  # bearing in radians
            tx = camera.location.x + math.sin(heading) * 20
            ty = camera.location.y + math.cos(heading) * 20
            data = bpy.data.lights.new("GroundFill", "AREA")
            data.size = 60
            data.energy = args.ground_fill
            data.color = (0.85, 0.88, 1.0)
            fill = bpy.data.objects.new("GroundFill", data)
            fill.location = (tx, ty, 30)
            scene.collection.objects.link(fill)
        signs = 0 if args.no_dressing else street_scene.add_billboards(cfg, project_dir, origin)
        props = 0 if args.no_dressing else street_scene.add_street_props(cfg, origin)
        print(f"[blender-shot] added {signs} billboards and {props} street props", flush=True)
    setup_world(scene, spec, args.sky_strength)
    if args.clay:
        apply_clay(scene, plateau_objects)
    elif args.daylight:
        apply_daylight(scene)
    setup_render(scene, spec, args.engine, args.samples, args.out)
    scene.view_settings.exposure = args.exposure
    setup_bloom(scene, args.bloom)
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
    started = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[blender-shot] rendered {args.engine} in {time.time() - started:.1f}s -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
