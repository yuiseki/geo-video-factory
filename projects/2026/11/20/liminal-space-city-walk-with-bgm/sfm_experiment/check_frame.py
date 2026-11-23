"""check_frame.py <plateau_tris.npz> <osm_buildings.json> <osm_crossings.json> <camera_018.json> <out.png>
Top view 400 m around the origin: PLATEAU triangles grey, OSM building outlines cyan, OSM crossings yellow,
the 018 eye red with its bearing."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

z = np.load(sys.argv[1])
tris, (lon0, lat0) = z["tris"], z["origin"]
k = np.cos(np.radians(lat0)) * 6378137 * np.pi / 180
kn = 6378137 * np.pi / 180
V = 800
g = lambda x, y: (x * 2 + V / 2, V / 2 - y * 2)
img = Image.new("RGB", (V, V), (16, 16, 20))
d = ImageDraw.Draw(img)
for tr in tris:
    if abs(tr[0, 0]) < 220 and abs(tr[0, 1]) < 220:
        d.polygon([g(x, y) for x, y, _ in tr], fill=(70, 70, 76))
for fn, col in ((sys.argv[2], (0, 200, 255)), (sys.argv[3], (255, 220, 0))):
    for el in json.load(open(fn))["elements"]:
        if "geometry" in el:
            d.line([g((p["lon"] - lon0) * k, (p["lat"] - lat0) * kn) for p in el["geometry"]], fill=col, width=1)
fit = json.load(open(sys.argv[4]))["fit"]
e, n = (fit["eye"][0] - lon0) * k, (fit["eye"][1] - lat0) * kn
b = np.radians(fit["bearing"])
x, y = g(e, n)
d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 60, 60))
d.line((x, y, *g(e + 60 * np.sin(b), n + 60 * np.cos(b))), fill=(255, 60, 60), width=2)
d.text((8, 8), "1 px = 0.5 m. PLATEAU grey, OSM buildings cyan, OSM crossings yellow, 018 eye + bearing red", fill=(255, 255, 0))
img.save(sys.argv[5])
