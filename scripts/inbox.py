"""Sort new images from inbox/ into a style: the code guesses the top 3, Claude confirms on the contact sheet.

Usage: .venv/Scripts/python -I scripts/inbox.py <project-root>
- Moves each inbox image to taste/data/added/<best guess>/ (kept out of git: not Marc's images).
- Writes a numbered contact sheet taste/data/contact-sheets/inbox-<date>.jpg and appends to taste/data/added.json
  with the top-3 guesses. The guess is right about a third of the time (see nearest.py), so Claude looks at the
  sheet, moves wrongly filed images, and proposes edits to taste/styles/<style>.json for Marc's OK.
"""
import sys, os, json, shutil, datetime
from PIL import Image, ImageDraw

root = sys.argv[1]
sys.path.insert(0, os.path.join(root, 'scripts'))
from nearest import model  # noqa: E402

data = os.path.join(root, 'taste', 'data')
EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}
inbox = os.path.join(root, 'inbox')
files = [f for f in sorted(os.listdir(inbox)) if os.path.splitext(f)[1].lower() in EXTS]
if not files:
    print('inbox is empty'); sys.exit(0)

guess = model(root)
log_path = os.path.join(data, 'added.json')
log = json.load(open(log_path)) if os.path.exists(log_path) else []
today = datetime.date.today().isoformat()
sheet = Image.new('RGB', (4 * 220, ((len(files) + 3) // 4) * 160), (20, 20, 20))
draw = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    p = os.path.join(inbox, f)
    try:
        top, far, t = guess(p)
    except Exception as ex:
        print(f'SKIP {f}: {ex}'); continue
    style = top[0][0]
    dest = os.path.join(data, 'added', style)
    os.makedirs(dest, exist_ok=True)
    shutil.move(p, os.path.join(dest, f))
    log.append({'file': f, 'style': style, 'top3': [s for s, _ in top], 'far': far, 'date': today})
    t.thumbnail((216, 136)); x, y = (i % 4) * 220, (i // 4) * 160
    sheet.paste(t, (x, y)); draw.rectangle([x, y, x + 24, y + 16], fill=(0, 0, 0)); draw.text((x + 4, y + 2), str(i + 1), fill=(255, 255, 0))
    print(f'{i + 1} {f} -> {", ".join(s for s, _ in top)}{"   (far from all: new style?)" if far else ""}')
json.dump(log, open(log_path, 'w'), indent=1)
os.makedirs(os.path.join(data, 'contact-sheets'), exist_ok=True)
out = os.path.join(data, 'contact-sheets', f'inbox-{today}.jpg')
sheet.save(out, quality=80)
print('sheet:', out)
