"""Render one frame of a geo-video-factory shot JSON with Blender (spike).

Run inside Blender:
  blender -b --factory-startup -P packages/blender/render_plateau_shot.py -- \
    --shot <shot.json> --project-dir <dir that shot paths are relative to> \
    --out <frame.png> [--engine EEVEE|CYCLES] [--t 0.0] [--samples 64]

Geometry and camera math live in packages/pipeline/buildings/blender_geo.py (unit tested without bpy).
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
from buildings import blender_geo as bg  # noqa: E402
import landmarks  # noqa: E402
import night_buildings  # noqa: E402
import photo_projection  # noqa: E402
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
    parser.add_argument("--night-buildings", action="store_true", help="dim photo textures, light windows and storefronts")
    parser.add_argument("--window-share", type=float, default=0.0, help="share of lit floors; 0 = no windows")
    parser.add_argument("--night-dim", type=float, default=0.10, help="multiplier on the daylight photo texture")
    parser.add_argument("--pick-signs", default=None, help="JSON of sign rectangles picked in this view's pixels")
    parser.add_argument("--pick-out", default=None, help="write sign boxes (wall-anchored) here and skip rendering")
    parser.add_argument("--sign-boxes", default=None, help="JSON of sign boxes to light on PLATEAU walls")
    parser.add_argument("--sign-strength", type=float, default=4.0)
    parser.add_argument("--signal-poles", default=None, help="JSON from pipeline/buildings/street_lights.py")
    parser.add_argument("--lamp-power", type=float, default=1500.0)
    parser.add_argument("--wall-billboards", default=None, help="JSON of real-photo signs on picked wall boxes")
    parser.add_argument("--landmarks", default=None, help="JSON of landmark masses replacing PLATEAU boxes")
    parser.add_argument("--plain-ground", action="store_true", help="drop the shot's ground image")
    proj = parser.add_argument_group("photo projection")
    proj.add_argument("--project-photo", default=None, help="real photo (project-relative) to project onto buildings")
    proj.add_argument("--projector", default=None, help="JSON with the photo's fitted camera (camera_fit report)")
    proj.add_argument("--project-size", type=int, nargs=2, metavar=("W", "H"), help="photo size in pixels")
    proj.add_argument("--project-min-z", type=float, default=2.6, help="do not project below this height (people)")
    proj.add_argument("--project-mask", type=float, nargs=4, action="append", metavar=("U0", "V0", "U1", "V1"))
    proj.add_argument("--project-ground", action="store_true", help="also project the photo onto the ground")
    proj.add_argument("--no-landmark-dressing", action="store_true", help="landmark mass only (no bands/lights)")
    proj.add_argument("--view-standard", action="store_true", help="Standard view transform (keeps photo colours)")
    anim = parser.add_argument_group("short camera move")
    anim.add_argument("--frames", type=int, default=1)
    anim.add_argument("--dolly-m", type=float, default=0.0, help="move forward this far over the frames")
    anim.add_argument("--pan-deg", type=float, default=0.0, help="look around in place: sweep bearing +/- this")
    anim.add_argument("--zoom-to-fov", type=float, default=None, help="ease the vertical fov to this by the end")
    parser.add_argument("--crosswalks", default=None, help="JSON of crosswalk walking lines and widths")
    parser.add_argument("--size", type=int, nargs=2, metavar=("W", "H"), help="override the shot's frame size")
    parser.add_argument("--washes", default=None, help="JSON of facade boxes washed by area lights")
    parser.add_argument("--spill-power", type=float, default=0.0, help="W per m2 of sign light thrown back on walls")
    parser.add_argument("--mullion-glow", type=float, default=0.0, help="emission strength of landmark mullions")
    parser.add_argument("--floodlight-face", default=None, help="picked wall box to line with floodlights")
    parser.add_argument("--floodlight-share", type=float, default=0.2, help="floodlight height as share from the top")
    parser.add_argument("--window-strength", type=float, default=1.6)
    parser.add_argument("--storefront-strength", type=float, default=2.5)
    parser.add_argument("--manifest", default=None, help="override plateauBuildings.manifest (project-relative)")
    parser.add_argument("--ground-src", default=None, help="diagnostic: replace the ground image (project-relative)")
    parser.add_argument("--ground-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    parser.add_argument("--wet-roughness", type=float, nargs=2, default=[0.06, 0.45])
    parser.add_argument("--ground-fill", type=float, default=0.0, help="overhead area light power in W")
    parser.add_argument("--exposure", type=float, default=0.0)
    parser.add_argument("--sky-strength", type=float, default=0.6)
    parser.add_argument("--sky-color", default=None, help="hex colour of the night sky, e.g. #0b1426")
    parser.add_argument("--bloom", type=float, default=0.6, help="compositor glare strength, 0 disables")
    eye = parser.add_argument_group("street-level camera (overrides the shot's MapLibre keys)")
    eye.add_argument("--eye", type=float, nargs=3, metavar=("LNG", "LAT", "HEIGHT_M"))
    eye.add_argument("--bearing", type=float, default=0.0)
    eye.add_argument("--tilt", type=float, default=90.0, help="0 looks down, 90 looks at the horizon")
    eye.add_argument("--fov", type=float, default=None, help="vertical field of view in degrees")
    eye.add_argument("--roll", type=float, default=0.0, help="camera roll about the view axis in degrees")
    eye.add_argument("--fisheye-mm", type=float, default=None,
                     help="equisolid fisheye focal length on a 36 mm wide sensor (Cycles only)")
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
    if args.fisheye_mm:
        # Ultra-wide look of phone/action cameras: equisolid fisheye (Cycles only), full-frame width.
        data.type = "PANO"
        data.panorama_type = "FISHEYE_EQUISOLID"
        data.fisheye_lens = args.fisheye_mm
        data.fisheye_fov = math.radians(180)
        data.sensor_fit = "HORIZONTAL"
        data.sensor_width = 36.0
    data.clip_start = 0.1
    data.clip_end = 5000
    obj = bpy.data.objects.new("ShotCamera", data)
    scene.collection.objects.link(obj)
    obj.location = cam["location"]
    obj.rotation_euler = cam["rotation_euler"]
    if args.eye and args.roll:
        obj.matrix_world = photo_projection.camera_matrix(cam["location"], args.tilt, args.bearing, args.roll)
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


def pick_signs(scene: bpy.types.Scene, spec: dict, args: argparse.Namespace, origin: list[float]) -> None:
    """Ray-cast picked sign rectangles onto PLATEAU walls and save upright sign boxes."""
    picks = json.loads(Path(args.pick_signs).read_text())
    width, height = spec["width"], spec["height"]
    fov = args.fov if args.fov is not None else 36.87
    camera = {"location": tuple(bg.eye_camera(args.eye, args.bearing, args.tilt, fov, origin)["location"]),
              "tilt": args.tilt, "bearing": args.bearing, "fov": fov, "shift_px": args.shift_px}
    bpy.context.view_layer.update()  # apply the tile matrices before ray casting
    depsgraph = bpy.context.evaluated_depsgraph_get()
    boxes = []
    scene.render.resolution_x, scene.render.resolution_y = width, height
    cam_obj = scene.camera
    top_right, bottom_right, bottom_left, top_left = cam_obj.data.view_frame(scene=scene)
    rotation = cam_obj.matrix_world.to_3x3()

    def blender_ray(u: float, v: float):
        fx, fy = (u + 0.5) / width, (v + 0.5) / height
        local = top_left.lerp(top_right, fx)
        local.y = top_left.y + (bottom_left.y - top_left.y) * fy
        direction = (rotation @ local).normalized()
        return cam_obj.matrix_world.translation, direction

    center_mine = bg.pixel_ray(camera, width / 2, height / 2, width, height)[1]
    center_blender = blender_ray(width / 2 - 0.5, height / 2 - 0.5)[1]
    print(f"[blender-shot] centre ray mine {tuple(round(c, 4) for c in center_mine)} "
          f"blender {tuple(round(c, 4) for c in center_blender)}", flush=True)
    profiles = []
    for profile in picks.get("profiles", []):
        v, u_start, u_end, step = profile["row"]
        hits = []
        u = u_start
        while u <= u_end:
            ray_origin, direction = blender_ray(u, v)
            ok, location, normal, _index, obj, _matrix = scene.ray_cast(depsgraph, ray_origin, direction)
            if ok:
                hits.append({"u": u, "point": list(location), "normal": list(normal), "object": obj.name})
            u += step
        profiles.append({"name": profile["name"], "hits": hits})
        print(f"[blender-shot] profile {profile['name']}: {len(hits)} hits", flush=True)
    for sign in picks["signs"]:
        u0, v0, u1, v1 = sign["rect"]
        samples = []
        for i in range(5):
            for j in range(5):
                u, v = u0 + (u1 - u0) * i / 4, v0 + (v1 - v0) * j / 4
                ray_origin, direction = blender_ray(u, v)
                ok, location, normal, _index, obj, _matrix = scene.ray_cast(depsgraph, ray_origin, direction)
                if ok and abs(normal.z) < 0.4:
                    samples.append((obj.name, tuple(round(c, 1) for c in normal), tuple(location)))
        if not samples:
            print(f"[blender-shot] pick {sign['name']}: no wall hit, skipped", flush=True)
            continue
        # Keep the wall most samples landed on (same object and facing), then fit its extent.
        keys = [(s[0], s[1]) for s in samples]
        wall = max(set(keys), key=keys.count)
        points = [s[2] for s in samples if (s[0], s[1]) == wall]
        hits = bg.wall_extent_corners(points, normal=wall[1])
        box = bg.sign_box(hits, camera["location"], depth=sign.get("depth", 1.5))
        box["samples"] = f"{len(points)}/25"
        box["name"] = sign["name"]
        boxes.append(box)
        print(f"[blender-shot] pick {sign['name']}: {2 * box['halfWidth']:.1f} x {2 * box['halfHeight']:.1f} m "
              f"at z {box['center'][2]:.1f} ({box['samples']} samples on one wall)", flush=True)
    Path(args.pick_out).write_text(json.dumps({"origin": origin, "boxes": boxes, "profiles": profiles}, indent=1))


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
    if args.size:
        spec["width"], spec["height"] = args.size
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
    if args.landmarks:
        for landmark in json.loads(Path(args.landmarks).read_text())["landmarks"]:
            result = landmarks.replace_with_landmark(plateau_objects, landmark, origin, args.mullion_glow)
            dressed = not (args.buildings_only or args.no_landmark_dressing)
            bands = landmarks.add_landmark_bands(landmark, result["outline"], project_dir) if dressed else 0
            if dressed:
                bands += landmarks.add_landmark_lights(landmark, result["outline"])
            plateau_objects.append(result["object"])
            print(f"[blender-shot] landmark {landmark['name']}: removed {result['removedFaces']} PLATEAU faces, "
                  f"{bands} bands", flush=True)
    if args.pick_signs:
        pick_signs(scene, spec, args, origin)
        return
    if not args.buildings_only:
        if args.ground_src:
            # Diagnostic: lay an untouched aerial photo (e.g. the raw GSI mosaic) as the ground.
            cfg["groundPlane"] = {"src": args.ground_src, "bbox": args.ground_bbox, "altitudeM": 0.04, "brightness": 1.0}
        if args.plain_ground:
            cfg.pop("groundPlane", None)  # dark asphalt only; markings come from --crosswalks
        if args.crosswalks:
            crosswalks = json.loads(Path(args.crosswalks).read_text())["crosswalks"]
            print(f"[blender-shot] {street_scene.add_crosswalks(crosswalks, origin)} crosswalk bars", flush=True)
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
        if args.signal_poles:
            poles = json.loads(Path(args.signal_poles).read_text())["poles"]
            print(f"[blender-shot] {street_scene.add_signal_poles(poles, origin, args.lamp_power)} signal poles", flush=True)
        if args.wall_billboards:
            entries = json.loads(Path(args.wall_billboards).read_text())["entries"]
            print(f"[blender-shot] {street_scene.add_wall_billboards(entries, project_dir)} wall billboards", flush=True)
        if args.spill_power > 0:
            entries = json.loads(Path(args.wall_billboards).read_text())["entries"] if args.wall_billboards else []
            boxes = json.loads(Path(args.sign_boxes).read_text())["boxes"] if args.sign_boxes else []
            spill = street_scene.sign_spill_boxes(entries, boxes, project_dir)
            print(f"[blender-shot] {street_scene.add_wall_spill(spill, args.spill_power)} sign spill lights", flush=True)
        if args.washes:
            washes = json.loads(Path(args.washes).read_text())["boxes"]
            print(f"[blender-shot] {street_scene.add_wall_spill(washes, reach=6.0)} facade washes", flush=True)
        if args.floodlight_face:
            face = json.loads(Path(args.floodlight_face).read_text())["boxes"][0]
            top = face["center"][2] + face["halfHeight"]
            street_scene.add_facade_floodlights(face, z=top * (1 - args.floodlight_share))
        signs = 0 if args.no_dressing else street_scene.add_billboards(cfg, project_dir, origin)
        props = 0 if args.no_dressing else street_scene.add_street_props(cfg, origin)
        print(f"[blender-shot] added {signs} billboards and {props} street props", flush=True)
    if args.sky_color:
        spec.setdefault("sky", {})["horizon-color"] = args.sky_color
    setup_world(scene, spec, args.sky_strength)
    if args.clay:
        apply_clay(scene, plateau_objects)
    elif args.daylight:
        apply_daylight(scene)
    elif args.night_buildings:
        changed = night_buildings.apply_night(
            plateau_objects, dim=args.night_dim, window_share=args.window_share, window_strength=args.window_strength,
            storefront_strength=args.storefront_strength, sign_strength=args.sign_strength,
            sign_boxes=json.loads(Path(args.sign_boxes).read_text())["boxes"] if args.sign_boxes else None,
        )
        print(f"[blender-shot] night materials on {changed} PLATEAU materials", flush=True)
    if args.project_photo:
        fit = json.loads(Path(args.projector).read_text())["fit"]
        px, py = bg.local_meters(fit["eye"], origin)
        projector = photo_projection.add_projector((px, py, fit["eye"][2]), fit["tilt"], fit["bearing"], fit.get("roll", 0.0))
        targets = list(plateau_objects)
        if args.project_ground:
            # The cleaned photo carries the road too: project it onto the ground as well.
            targets += [obj for obj in scene.objects if obj.name in ("AsphaltBase", "GroundPlane")]
        materials = {m for obj in targets if obj.type == "MESH" for m in obj.data.materials if m}
        changed = photo_projection.project_onto(
            list(materials), str(project_dir / args.project_photo), projector, fit["fov"],
            args.project_size[0], args.project_size[1], min_z=args.project_min_z, masks=args.project_mask or [])
        print(f"[blender-shot] projected the photo onto {changed} materials", flush=True)
    setup_render(scene, spec, args.engine, args.samples, args.out)
    if args.view_standard:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
    scene.view_settings.exposure = args.exposure
    setup_bloom(scene, args.bloom)
    if args.frames > 1 and (args.pan_deg or args.zoom_to_fov):
        # Look around in place: no parallax, so a projected photo stays intact. Eased sweep
        # bearing - pan .. bearing + pan, field of view easing to `zoom_to_fov`.
        camera.rotation_mode = "QUATERNION"
        fov0 = math.degrees(camera.data.angle_y)
        location = tuple(camera.location)
        for frame in range(1, args.frames + 1):
            t = (frame - 1) / max(1, args.frames - 1)
            ease = 0.5 - 0.5 * math.cos(math.pi * t)
            bearing = args.bearing + args.pan_deg * (2 * ease - 1)
            camera.matrix_world = photo_projection.camera_matrix(location, args.tilt, bearing, args.roll)
            camera.keyframe_insert("rotation_quaternion", frame=frame)
            camera.data.angle_y = math.radians(fov0 + ((args.zoom_to_fov or fov0) - fov0) * ease)
            camera.data.keyframe_insert("lens", frame=frame)
    elif args.frames > 1:
        # Dolly forward along the view's horizontal heading.
        heading = -camera.rotation_euler.z
        start = camera.location.copy()
        camera.keyframe_insert("location", frame=1)
        camera.location.x = start.x + math.sin(heading) * args.dolly_m
        camera.location.y = start.y + math.cos(heading) * args.dolly_m
        camera.keyframe_insert("location", frame=args.frames)  # default Bezier easing
    if args.frames > 1:
        scene.frame_start, scene.frame_end = 1, args.frames
        scene.render.fps = spec.get("fps", 24)
        scene.render.filepath = args.out.rsplit(".", 1)[0] + "_"
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
    started = time.time()
    if args.frames > 1:
        bpy.ops.render.render(animation=True)
    else:
        bpy.ops.render.render(write_still=True)
    print(f"[blender-shot] rendered {args.engine} {args.frames} frame(s) in {time.time() - started:.1f}s -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
