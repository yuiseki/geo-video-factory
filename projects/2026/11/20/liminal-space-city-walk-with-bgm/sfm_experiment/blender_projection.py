"""Blender test: project photos with SfM-fitted cameras onto PLATEAU and look from other viewpoints.

blender -b --factory-startup -P blender_projection.py -- <repo> <proj_dir> <out_dir> <render_key> <key> [<key> ...]
  proj_dir: mesh.npz + cams.json from export_projection.py
  render_key: whose camera the views start from; the photos are projected in the given order, the
              first one last (on top)
Writes view_<name>.png stills (camera shifted right / forward) and frames/ for a short side-step clip.
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


wall = flat("wall", (0.05, 0.05, 0.06))
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


bpy.context.active_object.data.materials.append(ground_materials.aged_asphalt() if "--aged" in argv else asphalt())


def add_crosswalks(path, lon0=139.70055, lat0=35.65950):
    """Zebra bars from crosswalks.json (OSM lines in lon/lat + width) as faint emissive quads on the ground."""
    import blender_geo as bg
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
    o.data.materials.append(ground_materials.worn_paint() if "--aged" in argv else m)
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


for key in reversed(keys):
    c = cams[key]
    proj_obj = photo_projection.add_projector((0, 0, 0), 90, 0)
    proj_obj.matrix_world = cam_matrix(c)
    bpy.context.view_layer.update()
    photo_projection.project_onto([wall], opts.get(f"photo-{key}", c["photo"]), proj_obj, c["fov_v"],
                                  c["width"], c["height"], min_z=ground + STRETCH)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
if "--aged" in argv:
    sc.eevee.use_raytracing = True   # wet patches reflect the photo facades
c0 = cams[render_key]
sc.render.resolution_x, sc.render.resolution_y = 960, round(960 * c0["height"] / c0["width"])
sc.world = bpy.data.worlds.new("night")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.01, 0.012, 0.03, 1)
cam_data = bpy.data.cameras.new("view")
cam_data.sensor_fit = "VERTICAL"
cam_data.angle_y = math.radians(c0["fov_v"])
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
