"""Views of an area's scene (blender -b <scene.blend> -P render_views.py -- <scene.json> <out dir> <day|night> [view]).

Without a view, all three are drawn in this one Blender; before.py runs one Blender per view, because EEVEE in the
background sometimes drew a view from the previous camera (and re-rendering in the same session did not always help).

aerial: 300 m out and 250 m up, looking at the centre; roof: 90 m out and 45 m up; street: eye 1.6 m above the
ground, looking along street_bearing, from the point within 80 m of the centre (10 m grid) that sees farthest along
that bearing and back (a street, not the wall the centre may fall against); street lamps within 6 m of that eye are
left out of the street view. The scene's own render settings
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
only = argv[3] if len(argv) > 3 else None
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
previous = []
cam.data.sensor_fit = "HORIZONTAL"
cam.data.clip_start, cam.data.clip_end = 0.3, 6000
for name, (eye, target, fov) in views.items():
    if only and name != only:
        continue
    for obj in sc.objects:          # a street lamp (pp_scene --lamps) right at the eye would fill the street view
        if obj.name.startswith("lamp") and obj.parent is None:
            obj.hide_render = name == "street" and (obj.location.xy - eye.xy).length < 6.0
            for child in obj.children:
                child.hide_render = obj.hide_render
    cam.location = eye
    cam.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    cam.data.angle = math.radians(fov)
    sc.frame_set(sc.frame_current)           # EEVEE in the background can otherwise draw from the previous camera
    bpy.context.view_layer.update()
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(out / f"{tag}_{name}.png")
    for attempt in range(2):
        bpy.ops.render.render(write_still=True)
        small = Path(sc.render.filepath)
        img = bpy.data.images.load(str(small), check_existing=False)
        now = list(img.pixels[::4096])         # a sparse sample is enough to tell two views apart
        bpy.data.images.remove(img)
        if not previous or sum(abs(a - b) for a, b in zip(now, previous)) / len(now) > 0.002:
            break
        print("same image as the previous view, drawing again:", name)
    else:
        raise SystemExit(f"{name}: EEVEE drew the previous view twice")
    previous = now
    print("wrote", sc.render.filepath)
