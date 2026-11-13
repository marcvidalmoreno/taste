"""Contact sheet for one batch: numbered thumbnails, seed first. Claude reviews this one image per batch.

Usage: .venv/Scripts/python -I scripts/sheet.py <batch folder>
Writes <batch>/sheet.jpg. Numbers match the rating step (1 = first generated image, seed is "S").
"""
import sys, os, glob
from PIL import Image, ImageDraw

batch = sys.argv[1]
seeds = sorted(glob.glob(os.path.join(batch, 'seed.*')))
pngs = sorted(p for p in glob.glob(os.path.join(batch, '*.png')) if not os.path.basename(p).startswith('seed.'))
items = [('S', p) for p in seeds[:1]] + [(str(i + 1), p) for i, p in enumerate(pngs)]
if not items:
    sys.exit('no images in ' + batch)
W, H, cols = 420, 236, min(4, len(items))
sheet = Image.new('RGB', (cols * W, ((len(items) + cols - 1) // cols) * H), (24, 24, 24))
draw = ImageDraw.Draw(sheet)
for i, (label, p) in enumerate(items):
    im = Image.open(p).convert('RGB')
    im.thumbnail((W - 8, H - 8))
    x, y = (i % cols) * W + 4, (i // cols) * H + 4
    sheet.paste(im, (x, y))
    draw.rectangle([x, y, x + 34, y + 26], fill=(0, 0, 0))
    draw.text((x + 8, y + 6), label, fill=(255, 255, 255))
out = os.path.join(batch, 'sheet.jpg')
sheet.save(out, quality=82)
for label, p in items:
    print(label, os.path.basename(p))
print('sheet:', out)
