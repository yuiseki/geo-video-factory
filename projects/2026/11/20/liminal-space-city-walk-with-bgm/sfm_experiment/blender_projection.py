"""Blender test: project photos with SfM-fitted cameras onto PLATEAU and look from other viewpoints.

blender -b --factory-startup -P blender_projection.py -- <repo> <proj_dir> <out_dir> <render_key> <key> [<key> ...]
  proj_dir: mesh.npz + cams.json from export_projection.py
  render_key: whose camera the views start from; the photos are projected in the given order, the
              first one last (on top)
Writes view_<name>.png stills (camera shifted right / forward) and frames/ for a short side-step clip.

--day: daylight look for daytime photos. The night defaults are a near-black world, near-black walls where
       no photo lands and a road as dark as one lit by signs; with daytime photos the gaps between them
       then read as holes. --day gives a sky gradient (the photo's sky lands on nothing, so the world is
       the sky), light grey walls, a brighter road, and the Standard view transform (AgX, the default,
       greys out a daylight photo; the photos are already display-referred).
  --sky=r,g,b/r,g,b   horizon / zenith colour the camera sees (linear), default 0.72,0.80,0.90/0.20,0.38,0.75;
                      the road is always lit by the default sky. Without --day one colour: the night sky
                      (default 0.01,0.012,0.03). A photo whose sky is black needs a black world, or the gaps
                      between the buildings show as dark blue boxes
  --sun=az,el[,w]     a sun lamp from compass azimuth az at elevation el (deg), strength w (default 2):
                      building shadows on the road. Photos are emission and are not lit by it.
  --ground-photo=<key>[,<key>]   these photos also land on the ground (a paved plaza in front of the photographer).
                      Nothing tests what stands in between: where the photo shows a tree or a wall, its picture is
                      smeared along the ground behind it, so stay near where the photo was taken
  --backdrop=<key>[,<key>]   these photos also land on a far dome around their own viewpoint: the sky, clouds, cranes
                      and distant buildings that PLATEAU has no geometry for. Photo sky that lands on a wall then
                      continues into the same sky behind it instead of standing out against the world colour.
                      Outside the photo's frame the dome is transparent (the world shows)
  --size=WxH          frame size (default 960 wide, as tall as the photo's shape). The photo's width fills the frame's
                      width: a wider shape such as 1920x1080 cuts the photo's top and bottom, which leaves room to tilt
  --zoom=z            narrow the field of view z times: room to pan before the photo's edge comes into the frame
  --ground-gain= --ground-glow= --ground-wet=   road albedo multiplier (4; 1.5 with a sun), ambient emission
                      strength (1; 0.35 with a sun), wet mirror patches (0 = dry; the night default is 1)
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
repo, proj, out, render_key = Path(argv[0]), Path(argv[1]), Path(argv[2]), argv[3]
keys = [a for a in argv[4:] if not a.startswith("--")]
opts = dict(a[2:].split("=", 1) for a in argv[4:] if a.startswith("--") and "=" in a)
# --photo-<key>=<path> swaps in another version of a photo (e.g. with people removed);
# --stretch=<m> is the height below which the facade colour above is stretched down (2.6 = old default,
# 0 = project the photo all the way down, for people-removed photos)
STRETCH = float(opts.get("stretch", 2.6))
GROUND_PHOTOS = [k for k in opts.get("ground-photo", "").split(",") if k]
BACKDROP_PHOTOS = [k for k in opts.get("backdrop", "").split(",") if k]
BACKDROP_RADIUS = 1500.0   # far enough for no visible parallax over a few metres, inside the camera's clip range
DAY = "--day" in argv
SKY_DEFAULT = "0.72,0.80,0.90/0.20,0.38,0.75"   # horizon / zenith, linear
SUN = [float(v) for v in opts["sun"].split(",")] if "sun" in opts else None
GROUND_GAIN = float(opts.get("ground-gain", (1.5 if SUN else 4.0) if DAY else 1.0))
GROUND_GLOW = float(opts.get("ground-glow", (0.35 if SUN else 1.0) if DAY else 1.0))
GROUND_WET = float(opts.get("ground-wet", 0.0 if DAY else 1.0))
GROUND = (GROUND_GAIN, GROUND_GLOW, GROUND_WET)
sys.path.insert(0, str(repo / "packages/pipeline"))
sys.path.insert(0, str(repo / "packages/blender"))
import photo_projection  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ground_materials  # noqa: E402

out.mkdir(parents=True, exist_ok=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
z = np.load(proj / "mesh.npz")
tris, ground = z["tris"].astype(np.float64), float(z["ground"])
cams = json.load(open(proj / "cams.json"))

# PLATEAU mesh (each triangle its own 3 vertices; fine for a test)
verts = tris.reshape(-1, 3)
mesh = bpy.data.meshes.new("plateau")
mesh.vertices.add(len(verts))
mesh.vertices.foreach_set("co", verts.ravel())
n = len(tris)
mesh.loops.add(n * 3)
mesh.loops.foreach_set("vertex_index", np.arange(n * 3))
mesh.polygons.add(n)
mesh.polygons.foreach_set("loop_start", np.arange(0, n * 3, 3))
mesh.polygons.foreach_set("loop_total", np.full(n, 3))
mesh.update()
obj = bpy.data.objects.new("plateau", mesh)
bpy.context.scene.collection.objects.link(obj)


def flat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*rgb, 1)
    p.inputs["Roughness"].default_value = 0.9
    return m


wall = flat("wall", (0.42, 0.42, 0.44) if DAY else (0.05, 0.05, 0.06))
obj.data.materials.append(wall)
bpy.ops.mesh.primitive_plane_add(size=1400, location=(cams[render_key]["eye"][0], cams[render_key]["eye"][1], ground))


def asphalt():
    """Synthesised ground: dark asphalt grain as weak emission (the scene has no lamps)."""
    m = bpy.data.materials.new("asphalt")
    m.use_nodes = True
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(nd)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.9
    noise.inputs["Detail"].default_value = 12
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 40
    mixc = nt.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    mixc.inputs["Factor"].default_value = 0.5
    nt.links.new(noise.outputs["Fac"], mixc.inputs["A"])
    nt.links.new(fine.outputs["Fac"], mixc.inputs["B"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.010, 0.010, 0.012, 1)
    ramp.color_ramp.elements[1].color = (0.045, 0.043, 0.048, 1)
    nt.links.new(mixc.outputs["Result"], ramp.inputs["Fac"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


ground_mat = ground_materials.aged_asphalt(*GROUND) if "--aged" in argv else asphalt()
bpy.context.active_object.data.materials.append(ground_mat)


def add_crosswalks(path, lon0=139.70055, lat0=35.65950):
    """Zebra bars from crosswalks.json (OSM lines in lon/lat + width) as faint emissive quads on the ground."""
    from buildings import blender_geo as bg
    k = math.cos(math.radians(lat0)) * 6378137 * math.pi / 180
    kn = 6378137 * math.pi / 180
    m = bpy.data.materials.new("zebra")
    m.use_nodes = True
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(nd)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6
    ramp = nt.nodes.new("ShaderNodeValToRGB")   # worn paint
    ramp.color_ramp.elements[0].color = (0.06, 0.06, 0.065, 1)
    ramp.color_ramp.elements[1].color = (0.16, 0.16, 0.17, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    verts, faces = [], []
    for cw in json.load(open(path))["crosswalks"]:
        (a, b) = [((lon - lon0) * k, (lat - lat0) * kn) for lon, lat in cw["line"][:2]]
        for q in bg.crosswalk_stripes(a, b, cw["width"]):
            i = len(verts)
            verts += [(x, y, ground + 0.02) for x, y in q]
            faces.append((i, i + 1, i + 2, i + 3))
    me = bpy.data.meshes.new("zebra")
    me.from_pydata(verts, [], faces)
    o = bpy.data.objects.new("zebra", me)
    o.data.materials.append(ground_materials.worn_paint(*GROUND) if "--aged" in argv else m)
    bpy.context.scene.collection.objects.link(o)
    return len(faces)


if "crosswalks" in opts:
    print("zebra bars", add_crosswalks(opts["crosswalks"]))


def cam_matrix(c, shift=(0.0, 0.0, 0.0)):
    """Blender camera/projector matrix from COLMAP world->camera rotation: Blender looks down -Z, up +Y."""
    Rt = np.array(c["Rw"]).T
    cols = [Rt[:, 0], -Rt[:, 1], -Rt[:, 2]]
    right, fwd = Rt[:, 0], Rt[:, 2]
    fwd_h = np.array([fwd[0], fwd[1], 0.0]) / max(1e-9, math.hypot(fwd[0], fwd[1]))
    loc = np.array(c["eye"]) + shift[0] * right + shift[1] * fwd_h + np.array([0, 0, shift[2]])
    return Matrix([[cols[0][i], cols[1][i], cols[2][i], loc[i]] for i in range(3)] + [[0, 0, 0, 1]])


def add_backdrop(eye):
    """A dome around `eye` that shows nothing by itself (transparent): only what a photo projects onto it."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=BACKDROP_RADIUS, location=tuple(eye), segments=48, ring_count=24)
    dome = bpy.context.object
    dome.name = "backdrop"
    dome.visible_shadow = False
    mat = bpy.data.materials.new("backdrop")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    clear = nodes.new("ShaderNodeBsdfTransparent")
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(clear.outputs[0], output.inputs["Surface"])
    dome.data.materials.append(mat)
    return mat


for key in reversed(keys):
    c = cams[key]
    proj_obj = photo_projection.add_projector((0, 0, 0), 90, 0)
    proj_obj.matrix_world = cam_matrix(c)
    bpy.context.view_layer.update()
    photo_projection.project_onto([wall], opts.get(f"photo-{key}", c["photo"]), proj_obj, c["fov_v"],
                                  c["width"], c["height"], min_z=ground + STRETCH)
    if key in GROUND_PHOTOS:
        photo_projection.project_onto([ground_mat], opts.get(f"photo-{key}", c["photo"]), proj_obj, c["fov_v"],
                                      c["width"], c["height"], min_z=ground - 1.0)
    if key in BACKDROP_PHOTOS:
        photo_projection.project_onto([add_backdrop(c["eye"])], opts.get(f"photo-{key}", c["photo"]), proj_obj,
                                      c["fov_v"], c["width"], c["height"], min_z=ground - 1.0)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
if "--aged" in argv:
    sc.eevee.use_raytracing = True   # wet patches reflect the photo facades
c0 = cams[render_key]
if "size" in opts:
    RW, RH = (int(v) for v in opts["size"].split("x"))
else:
    RW, RH = 960, round(960 * c0["height"] / c0["width"])
sc.render.resolution_x, sc.render.resolution_y = RW, RH
sc.world = bpy.data.worlds.new("day" if DAY else "night")
sc.world.use_nodes = True
if DAY:
    # sky gradient by the view ray's elevation: pale at the horizon, blue overhead
    wn, wl = sc.world.node_tree.nodes, sc.world.node_tree.links
    coord = wn.new("ShaderNodeTexCoord")
    sep = wn.new("ShaderNodeSeparateXYZ")
    wl.new(coord.outputs["Generated"], sep.inputs[0])

    def sky_ramp(spec):
        horizon, zenith = [[float(v) for v in part.split(",")] for part in spec.split("/")]
        ramp = wn.new("ShaderNodeValToRGB")      # z = sin(elevation): 0 at the horizon, 0.7 at 45 deg
        ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, (*horizon, 1)
        ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.7, (*zenith, 1)
        wl.new(sep.outputs["Z"], ramp.inputs["Fac"])
        return ramp

    # --sky is what the camera sees (matched to the top photo's sky, so photo sky that lands on a building
    # does not stand out). The light on the road comes from the default sky whatever --sky says: a deep
    # blue sky tints the road blue, and two scenes with different skies would not share a road colour.
    seen, light = sky_ramp(opts.get("sky", SKY_DEFAULT)), sky_ramp(SKY_DEFAULT)
    path = wn.new("ShaderNodeLightPath")
    mix = wn.new("ShaderNodeMixRGB")
    wl.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    wl.new(light.outputs["Color"], mix.inputs["Color1"])
    wl.new(seen.outputs["Color"], mix.inputs["Color2"])
    wl.new(mix.outputs["Color"], wn["Background"].inputs["Color"])
    sc.view_settings.view_transform = "Standard"
    if SUN:
        az, el = math.radians(SUN[0]), math.radians(SUN[1])
        lamp = bpy.data.lights.new("sun", "SUN")
        lamp.energy = SUN[2] if len(SUN) > 2 else 2.0
        lamp.angle = math.radians(1.5)
        sun = bpy.data.objects.new("sun", lamp)
        to_sun = np.array([math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)])
        side = np.cross((0.0, 0.0, 1.0), to_sun)
        side /= np.linalg.norm(side)
        up = np.cross(to_sun, side)              # a lamp shines down its -Z, so +Z points at the sun
        sun.matrix_world = Matrix([[side[i], up[i], to_sun[i], 0.0] for i in range(3)] + [[0, 0, 0, 1]])
        sc.collection.objects.link(sun)
else:
    night = [float(v) for v in opts.get("sky", "0.01,0.012,0.03").split(",")]
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (*night, 1)
cam_data = bpy.data.cameras.new("view")
cam_data.sensor_fit = "VERTICAL"
# the photo's field of view across the frame's width, whatever the frame's shape; --zoom narrows it
half_w = math.tan(math.radians(c0["fov_v"]) / 2) * c0["width"] / c0["height"] / float(opts.get("zoom", 1))
cam_data.angle_y = 2 * math.atan(half_w * RH / RW)
cam_data.clip_start, cam_data.clip_end = 0.3, 3000
view = bpy.data.objects.new("view", cam_data)
sc.collection.objects.link(view)
sc.camera = view

for name, shift in (("0_photo_pose", (0, 0, 0)), ("1_right5m", (5, 0, 0)), ("2_right15m", (15, 0, 0)),
                    ("3_forward20m", (0, 20, 0)), ("4_up8m", (0, 0, 8))):
    view.matrix_world = cam_matrix(c0, shift)
    sc.render.filepath = str(out / f"view_{name}.png")
    bpy.ops.render.render(write_still=True)

def look_matrix(pos, bearing, pitch):
    """Camera matrix at pos looking along compass bearing (deg, clockwise from north) and pitch (deg up)."""
    b, p = math.radians(bearing), math.radians(pitch)
    fwd = np.array([math.sin(b) * math.cos(p), math.cos(b) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(b), -math.sin(b), 0.0])
    up = np.cross(right, fwd)
    cols = [right, up, -fwd]
    return Matrix([[cols[0][i], cols[1][i], cols[2][i], pos[i]] for i in range(3)] + [[0, 0, 0, 1]])


if "frames" in opts:
    # --frames=<json>: [{"x", "y", "z", "bearing", "pitch", "out"}, ...] rendered as given (paths made outside)
    for fr in json.load(open(opts["frames"])):
        view.matrix_world = look_matrix((fr["x"], fr["y"], fr["z"]), fr["bearing"], fr["pitch"])
        sc.render.filepath = fr["out"]
        bpy.ops.render.render(write_still=True)

if "path" in opts:
    # --path=x,y,bearing;x,y,bearing;... waypoints at eye height; the first one may be "photo" (render_key's pose)
    fwd0 = np.array(c0["Rw"]).T[:, 2]
    b0 = math.degrees(math.atan2(fwd0[0], fwd0[1]))
    pitch = math.degrees(math.asin(fwd0[2]))
    eye_h = c0["eye"][2]
    wps = []
    for w in opts["path"].split(";"):
        if w == "photo":
            wps.append((c0["eye"][0], c0["eye"][1], b0))
        else:
            wps.append(tuple(float(v) for v in w.split(",")))
    seg = [math.dist(wps[i][:2], wps[i + 1][:2]) for i in range(len(wps) - 1)]
    total = sum(seg)
    N = int(float(opts.get("seconds", 10)) * 24)
    (out / "frames").mkdir(exist_ok=True)
    for i in range(N):
        d = total * (0.5 - 0.5 * math.cos(math.pi * i / (N - 1)))
        k = 0
        while k < len(seg) - 1 and d > seg[k]:
            d -= seg[k]
            k += 1
        f = min(1.0, d / seg[k]) if seg[k] else 1.0
        a, b = wps[k], wps[k + 1]
        db = (b[2] - a[2] + 180) % 360 - 180
        pos = (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), eye_h)
        view.matrix_world = look_matrix(pos, a[2] + f * db, pitch * (1 - (k + f) / len(seg)) + 3 * (k + f) / len(seg))
        sc.render.filepath = str(out / "frames" / f"{i:04d}.png")
        bpy.ops.render.render(write_still=True)

if "--clip" in sys.argv:
    (out / "frames").mkdir(exist_ok=True)
    N = 120
    for i in range(N):
        s = 0.5 - 0.5 * math.cos(math.pi * i / (N - 1))   # ease in and out
        view.matrix_world = cam_matrix(c0, (12 * s, 6 * s, 0))
        sc.render.filepath = str(out / "frames" / f"{i:04d}.png")
        bpy.ops.render.render(write_still=True)
print("done")
