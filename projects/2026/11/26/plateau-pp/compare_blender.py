"""Render a trial area (out/<name>, PLATEAU++ as plateau_pp bakes it) with Blender's own glTF import: no material is touched (blender -b -P).

    blender -b --factory-startup -P projects/2026/11/26/plateau-pp/compare_blender.py -- out/<name> <out.png>

Placement, ground and camera come from out/<name>/scene.json (scene_trial.py), as in compare_three.mjs.
Light: a sky of SKY radiance and a sun of SUN W/m2 from SUN_DIR, the same numbers the three.js side uses.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

SKY = (0.62, 0.74, 0.9)
SUN, SUN_DIR = 3.0, (-0.45, -0.55, 0.70)       # direction the light comes from (towards the sun)

argv = sys.argv[sys.argv.index("--") + 1:]
baked, out_png = Path(argv[0]), Path(argv[1])
scene = json.loads((baked / "scene.json").read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
for tile in scene["tiles"]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(baked / tile["glb"]))
    m = Matrix(tile["matrix"])
    for obj in set(bpy.data.objects) - before:
        if obj.parent is None:
            obj.matrix_world = m @ obj.matrix_world

sc.world = bpy.data.worlds.new("sky")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (*SKY, 1)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = SUN
sun.rotation_euler = Vector(SUN_DIR).to_track_quat("Z", "Y").to_euler()
sc.collection.objects.link(sun)

c = scene["camera"]
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.sensor_fit = "VERTICAL"
cam.data.angle_y = math.radians(c["fov"])
cam.data.clip_start, cam.data.clip_end = 1.0, 20000
cam.location = c["eye"]
cam.rotation_euler = (Vector(c["target"]) - Vector(c["eye"])).to_track_quat("-Z", "Y").to_euler()
sc.collection.objects.link(cam)
sc.camera = cam

sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = c["width"], c["height"]
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = str(out_png.resolve())
bpy.ops.render.render(write_still=True)
print("wrote", out_png)
