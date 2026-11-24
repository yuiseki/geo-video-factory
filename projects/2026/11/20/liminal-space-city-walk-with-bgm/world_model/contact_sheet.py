"""contact_sheet.py <out.jpg> <columns> <frame>... -- tile frames into one image for a quick look."""
import sys
from PIL import Image

out, cols, frames = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
tiles = [Image.open(f).convert("RGB") for f in frames]
w = 480
h = round(w * tiles[0].height / tiles[0].width)
rows = -(-len(tiles) // cols)
sheet = Image.new("RGB", (cols * w, rows * h))
for i, t in enumerate(tiles):
    sheet.paste(t.resize((w, h)), ((i % cols) * w, (i // cols) * h))
sheet.save(out, quality=88)
