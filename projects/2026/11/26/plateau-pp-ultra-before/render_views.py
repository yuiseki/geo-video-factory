"""Three views of an area's scene (blender -b <scene.blend> -P render_views.py -- <scene.json> <out dir> <day|night>).

aerial: 300 m out and 250 m up, looking at the centre; roof: 90 m out and 45 m up; street: eye 1.6 m above the
ground, looking along street_bearing, from the point within 80 m of the centre (10 m grid) that sees farthest along
that bearing and back (a street, not the wall the centre may fall against). The scene's own render settings
(pp_scene.py) are kept.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
info = json.loads(Path(argv[0]).read_text())
out, tag = Path(argv[1]), argv[2]
g = info["ground_z"]
b = math.radians(info["area"].get("street_bearing", 0))
ahead = Vector((math.sin(b), math.cos(b), 0))
back = Vector((-math.sin(b + 0.6), -math.cos(b + 0.6), 0))
sc = bpy.context.scene
depsgraph = bpy.context.evaluated_depsgraph_get()


def free(origin, direction, limit=400.0):
    hit, loc, *_ = sc.ray_cast(depsgraph, origin, direction, distance=limit)
    return (loc - origin).length if hit else limit


best, street = -1.0, Vector((0, 0, g + 1.6))
for ix in range(-8, 9):
    for iy in range(-8, 9):
        p = Vector((ix * 10, iy * 10, g + 1.6))
        if p.xy.length > 80 or free(p, Vector((0, 0, 1)), 300) < 300:      # under a roof: inside a building
            continue
        score = min(free(p, ahead), 200) + 0.5 * min(free(p, -ahead), 100)
        if score > best:
            best, street = score, p
print("street eye", tuple(round(v, 1) for v in street), "sees", round(best, 1))
views = {
    "aerial": (back * 300 + Vector((0, 0, g + 250)), Vector((0, 0, g)), 45),
    "roof": (back * 90 + Vector((0, 0, g + 45)), Vector((0, 0, g + 10)), 55),
    "street": (street, street + ahead * 100 + Vector((0, 0, 6)), 70),
}
cam = sc.camera
cam.data.sensor_fit = "HORIZONTAL"
cam.data.clip_start, cam.data.clip_end = 0.3, 6000
for name, (eye, target, fov) in views.items():
    cam.location = eye
    cam.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    cam.data.angle = math.radians(fov)
    bpy.context.view_layer.update()          # without it a render can come out from the previous camera
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(out / f"{tag}_{name}.png")
    bpy.ops.render.render(write_still=True)
    print("wrote", sc.render.filepath)
