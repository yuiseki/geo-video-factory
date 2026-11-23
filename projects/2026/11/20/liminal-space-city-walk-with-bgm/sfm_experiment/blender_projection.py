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
sys.path.insert(0, str(repo / "packages/pipeline"))
sys.path.insert(0, str(repo / "packages/blender"))
import photo_projection  # noqa: E402

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
bpy.context.active_object.data.materials.append(flat("ground", (0.03, 0.03, 0.035)))


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
    photo_projection.project_onto([wall], c["photo"], proj_obj, c["fov_v"], c["width"], c["height"],
                                  min_z=ground + 2.6)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
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

if "--clip" in sys.argv:
    (out / "frames").mkdir(exist_ok=True)
    N = 120
    for i in range(N):
        s = 0.5 - 0.5 * math.cos(math.pi * i / (N - 1))   # ease in and out
        view.matrix_world = cam_matrix(c0, (12 * s, 6 * s, 0))
        sc.render.filepath = str(out / "frames" / f"{i:04d}.png")
        bpy.ops.render.render(write_still=True)
print("done")
