"""Render an orbit around textured building models (Blender, run with -b -P).

usage: blender -b --factory-startup -P orbit_render.py -- <out_dir> <scene tris.npz>
           [--frames=48] [--size=960x540] [--radius=110] [--height=45] [--centre=x,y,z]
           [--arc=0,360] [--save=scene.blend] <model.obj>...

The models are drawn unlit (emission): the photos already carry the light of
their day, so shading them again would light them twice. The rest of the
scene (the PLATEAU triangles) is plain grey, so it is obvious which surfaces
are observed and which are only the geometry prior. Coordinates are the local
east/north/up metres of the atlas builder.
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
pos = [a for a in argv if not a.startswith("--")]
out_dir, scene_npz, models = Path(pos[0]), pos[1], pos[2:]
out_dir.mkdir(parents=True, exist_ok=True)
frames = int(opts.get("frames", 48))
RW, RH = (int(v) for v in opts.get("size", "960x540").split("x"))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# grey context: every PLATEAU triangle
tris = np.load(scene_npz)["tris"].astype(np.float64)
if "context-radius" in opts:
    cx0, cy0 = (float(v) for v in opts.get("centre", "0,0,0").split(",")[:2])
    cen = tris.mean(axis=1)
    tris = tris[np.hypot(cen[:, 0] - cx0, cen[:, 1] - cy0) < float(opts["context-radius"])]
mesh = bpy.data.meshes.new("context")
mesh.from_pydata(tris.reshape(-1, 3).tolist(), [], np.arange(len(tris) * 3).reshape(-1, 3).tolist())
ctx = bpy.data.objects.new("context", mesh)
sc.collection.objects.link(ctx)
grey = bpy.data.materials.new("grey")
grey.use_nodes = True
grey.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.45, 0.45, 0.47, 1)
grey.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
mesh.materials.append(grey)

lo, hi = [], []
for path in models:
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    for obj in set(bpy.data.objects) - before:
        obj.name = Path(path).parent.name
        obj.location.z += 0.0
        co = np.array([v.co[:] for v in obj.data.vertices])
        lo.append(co.min(axis=0)); hi.append(co.max(axis=0))
        for mat in obj.data.materials:
            nt = mat.node_tree
            tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
            out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
            em = nt.nodes.new("ShaderNodeEmission")
            nt.links.new(tex.outputs["Color"], em.inputs["Color"])
            nt.links.new(em.outputs[0], out.inputs["Surface"])
            mat.use_backface_culling = False
lo, hi = np.min(lo, axis=0), np.max(hi, axis=0)
# the textured copy sits on the same faces as the grey context: push the
# context's copy of those faces out of the way by drawing the models slightly
# in front is not possible for closed solids, so drop the context triangles
# that lie inside the models' bounding boxes instead (done by the caller via
# --drop, a .npy of triangle indices) -- see build_atlas.py report.
if "centre" in opts:
    centre = np.array([float(v) for v in opts["centre"].split(",")])
else:
    centre = (lo + hi) / 2
radius = float(opts.get("radius", 110))
height = float(opts.get("height", 45))
a0, a1 = (float(v) for v in opts.get("arc", "0,360").split(","))

target = bpy.data.objects.new("target", None)
target.location = centre.tolist()
sc.collection.objects.link(target)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = float(opts.get("lens", 28))
cam.data.clip_end = 3000
sc.collection.objects.link(cam)
sc.camera = cam
con = cam.constraints.new("TRACK_TO")
con.target = target
con.track_axis, con.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(200))
sc.collection.objects.link(sun)
sc.world = bpy.data.worlds.new("sky")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.74, 0.9, 1)
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = RW, RH
sc.render.image_settings.file_format = "JPEG"
ground = float(opts.get("ground", lo[2]))

if "save" in opts:
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / opts["save"]))
for i in range(frames):
    a = math.radians(a0 + (a1 - a0) * i / frames)   # compass bearing of the camera from the centre
    cam.location = (centre[0] + radius * math.sin(a), centre[1] + radius * math.cos(a), ground + height)
    sc.render.filepath = str(out_dir / f"f{i:04d}.jpg")
    bpy.ops.render.render(write_still=True)
print("rendered", frames, "frames; centre", centre.round(1).tolist(), "ground", round(ground, 1))
