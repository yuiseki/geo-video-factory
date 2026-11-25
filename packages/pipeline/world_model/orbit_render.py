"""Render an orbit around textured building models (Blender, run with -b -P).

usage: blender -b --factory-startup -P orbit_render.py -- <out_dir> <scene tris.npz>
           [--frames=48] [--size=960x540] [--radius=110] [--height=45] [--centre=x,y,z]
           [--arc=0,360] [--lens=28] [--context-radius=] [--ground=z]
           [--drop=<buildings.npz>:name,name] [--look=out] [--aim=h]
           [--save=scene.blend] [--sky=r,g,b] [--sun=3.0] [--only=first,last] <model.obj>...

--drop removes the context triangles the textured models replace (they would
z-fight). --look=out stands at the centre at --height and turns, aiming at
--aim metres above the ground on the ring of --radius: the view from the
crossing rather than of a building. --sky and --sun set the backdrop and the light on the
untextured context (a night layer wants both low). --only renders frames first..last-1 of the
same move and skips the ones already on disk: a long render in one process can hang on a busy
GPU, so run it in pieces under a timeout and run the piece again when it stops.

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
if "drop" in opts:   # --drop=<buildings.npz>:name,name -- the textured models replace these triangles
    path, names = opts["drop"].rsplit(":", 1)
    held = np.load(path)
    key = lambda t: {tuple(r) for r in np.round(t.mean(axis=1) * 20).astype(np.int64).tolist()}
    gone = set().union(*(key(held[n].astype(np.float64)) for n in names.split(",")))
    keep = np.array([tuple(r) not in gone for r in np.round(tris.mean(axis=1) * 20).astype(np.int64).tolist()])
    print("dropped", int((~keep).sum()), "context triangles")
    tris = tris[keep]
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
sun.data.energy = float(opts.get("sun", 3.0))
sun.data.use_shadow = False   # a city of this extent overflows the EEVEE shadow buffer
sun.rotation_euler = (math.radians(50), 0, math.radians(200))
sc.collection.objects.link(sun)
sc.world = bpy.data.worlds.new("sky")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (*(float(v) for v in opts.get("sky", "0.62,0.74,0.9").split(",")), 1)
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = RW, RH
sc.render.image_settings.file_format = "JPEG"
ground = float(opts.get("ground", lo[2]))
# PLATEAU buildings carry no ground: without a plane the sky shows under them
bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, ground))
road = bpy.data.materials.new("road")
road.use_nodes = True
road.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.16, 0.16, 0.17, 1)
road.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0   # no sun glint on the asphalt
bpy.context.object.data.materials.append(road)
look_out = opts.get("look") == "out"   # stand at the centre and turn, instead of circling it

if "save" in opts:
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / opts["save"]))
first, last = (int(v) for v in opts.get("only", f"0,{frames}").split(","))
warm = True   # EEVEE draws the first frame of a process before the textures are ready: it comes out blank
for i in range(first, min(last, frames)):
    if (out_dir / f"f{i:04d}.jpg").exists():
        continue
    a = math.radians(a0 + (a1 - a0) * i / frames)   # compass bearing of the camera from the centre
    ring = (centre[0] + radius * math.sin(a), centre[1] + radius * math.cos(a))
    if look_out:
        cam.location = (centre[0], centre[1], ground + height)
        target.location = (ring[0], ring[1], ground + float(opts.get("aim", height)))
    else:
        cam.location = (ring[0], ring[1], ground + height)
    sc.render.filepath = str(out_dir / f"f{i:04d}.jpg")
    bpy.ops.render.render(write_still=True)
    if warm:
        bpy.ops.render.render(write_still=True)
        warm = False
print("rendered", frames, "frames; centre", centre.round(1).tolist(), "ground", round(ground, 1))
