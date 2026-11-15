"""Re-measure a style's palette from ALL its images: the original wallpapers and every collection (ART, inbox...).

Usage: .venv/Scripts/python -I scripts/build/remeasure.py <style> [<style> ...] [--write]
Without --write it prints old vs new palette and the image count per source, and changes nothing.
With --write (after Marc's OK) it updates "palette" in taste/styles/<style>.json; then run scripts/build_taste.py.
Sources: taste/data/style_members.json + thumbs64.npy (wallpapers, 13 Nov), and taste/data/collections/<c>/tags.json
(keys "<style>" or "_extra:<style>") + that collection's thumbs64.npy.
"""
import glob, json, os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from features import palette  # noqa: E402

DATA = os.path.join(ROOT, 'taste', 'data')
write = '--write' in sys.argv
names = [a for a in sys.argv[1:] if not a.startswith('--')]
sources = []
if os.path.exists(os.path.join(DATA, 'style_members.json')):
    sources.append(('wallpapers', json.load(open(os.path.join(DATA, 'style_members.json'))), os.path.join(DATA, 'thumbs64.npy')))
for f in sorted(glob.glob(os.path.join(DATA, 'collections', '*', 'tags.json'))):
    c = os.path.dirname(f)
    tags = {k.split(':')[-1]: v for k, v in json.load(open(f)).items() if not k.startswith('_') or k.startswith('_extra:')}
    sources.append((os.path.basename(c), tags, os.path.join(c, 'thumbs64.npy')))

for name in names:
    path = os.path.join(ROOT, 'taste', 'styles', f'{name}.json')
    style = json.load(open(path, encoding='utf-8'))
    thumbs, counts = [], []
    for src, members, npy in sources:
        idx = members.get(name, [])
        if idx:
            T = np.load(npy)
            thumbs += [T[i] for i in idx]
            counts.append(f'{src} {len(idx)}')
    if not thumbs:
        print(f'{name}: no images found'); continue
    new = palette(thumbs)
    print(f'{name} ({", ".join(counts)})\n  old {" ".join(style["palette"])}\n  new {" ".join(new)}')
    if write:
        style['palette'] = new
        json.dump(style, open(path, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        print('  written')
