"""check_frames.py <frames dir> [min mean 0-255]   Exit 1 and list the frames that are darker than the limit."""
import sys, glob
from PIL import Image, ImageStat
lim = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
bad = [p[-8:-4] for p in sorted(glob.glob(sys.argv[1] + "/*.png"))
       if sum(ImageStat.Stat(Image.open(p).convert("RGB").resize((96, 72))).mean) / 3 < lim]
print(len(glob.glob(sys.argv[1] + "/*.png")), "frames,", len(bad), "dark", bad[:5], bad[-5:])
sys.exit(1 if bad else 0)
