"""Render one camera move of a shots module through a saved scene (Blender, run with -b <scene.blend> -P).

usage: blender -b <scene.blend> -P path_render.py -- <out_dir> <shots module or shots.py> <shot> [--size=1280x720]
           [--only=first,last] [--step=1] [--samples=16]

The scene is what orbit_render.py --save wrote. --step=6 draws every sixth frame (a preview; the frame
numbers stay those of the full move). --only draws frames first..last-1 and skips the ones on disk, so a
long move can run in pieces under a timeout.

Some views hang EEVEE for good (the process sleeps, every time, on the same frame). Before a frame is drawn a
marker f####.try is left; a later run that finds it draws that frame from a camera moved by a few centimetres,
and after two such tries leaves the frame out (f####.stuck) so the move goes on. fill_frames.py fills the gap."""
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # packages/pipeline
from world_model import world_camera as cp  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
out_dir, module, name = [a for a in argv if not a.startswith("--")]
out_dir = Path(out_dir)
out_dir.mkdir(parents=True, exist_ok=True)
shot = cp.load_shots(module)[name]
path = cp.sample(shot["keys"], shot["frames"], shot.get("ease", True))

sc = bpy.context.scene
cam = sc.camera
for con in list(cam.constraints):
    cam.constraints.remove(con)     # the saved scene tracks a target; here the matrix says where to look
cam.data.clip_start, cam.data.clip_end = 0.3, 3000
sc.render.resolution_x, sc.render.resolution_y = (int(v) for v in opts.get("size", "1280x720").split("x"))
sc.eevee.taa_render_samples = int(opts.get("samples", 16))
sc.render.image_settings.file_format = "JPEG"
first, last = (int(v) for v in opts.get("only", f"0,{len(path)}").split(","))
warm = True   # EEVEE draws the first frame of a process before the textures are ready
for i in range(first, min(last, len(path)), int(opts.get("step", 1))):
    target = out_dir / f"f{i:04d}.jpg"
    if target.exists() or target.with_suffix(".stuck").exists():
        continue
    tried = target.with_suffix(".try")
    n = int(tried.read_text() or 0) + 1 if tried.exists() else 0
    if n > 2:
        tried.rename(target.with_suffix(".stuck"))
        print("left out", target.name)
        continue
    tried.write_text(str(n))
    eye = path[i, :3] + 0.04 * n * np.array([1.0, -0.7, 0.5])
    cam.matrix_world = Matrix(cp.look_matrix(eye, path[i, 3:6], path[i, 7]).tolist())
    cam.data.lens = float(path[i, 6])
    sc.render.filepath = str(target)
    bpy.ops.render.render(write_still=True)
    if warm:
        bpy.ops.render.render(write_still=True)
        warm = False
    tried.unlink()
print("rendered", name, first, last)
