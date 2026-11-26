"""How many photos saw an atlas texel, as build_atlas stores it in seen.png and pp_scene reads it back.

seen.png holds min(count, 5) * 51 per texel. A texel seen by a single photo cannot be checked against another view:
when that photo looked through something the city model does not have (a tree, a crowd, a bus), the colours of
the occluder land on the wall, sharp enough to pass the quality fade (Shibuya's 109 at night, from a photo of the
crossing past a tree hung with lights). pp_scene --atlas-min-views=2 shows only texels at least two photos saw.
"""
import numpy as np

STEP = 51            # seen.png grey level per photo
CAP = 5              # counts above this are stored as this


def seen_png(count):
    """The seen.png grey levels (uint8) of per-texel photo counts."""
    return (np.clip(np.asarray(count), 0, CAP) * STEP).astype(np.uint8)


def views_threshold(min_views):
    """The value (0..1, as a Non-Color texture reads seen.png) above which a texel was seen by >= min_views photos."""
    return (min(max(int(min_views), 1), CAP) - 0.5) * STEP / 255.0
