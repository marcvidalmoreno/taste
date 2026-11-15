"""Step 4 of "Add a collection": from tags to measured palettes, exemplars and members, per style.

Usage: .venv/Scripts/python -I scripts/build/collection_styles.py <collection> [--src <folder>] [--only s1,s2]
Reads (local, git-ignored): taste/data/collections/<c>/tags.json, {style: [idx, ...]} set by eye on the sheets.
Keys starting with "_" are notes (extras to propose, images to join existing styles, skipped) and are left out;
pass "_extra:name" in --only to build one anyway (it's written under its plain name).
Writes: taste/data/collections/<c>/members.json and palettes.json, taste/data/exemplars/<style>/ (8 originals,
local only, used by pack.py), taste/data/contact-sheets/exemplars-<style>.jpg. Prints palette per style:
5 base colours (k-means on the thumbnails, dark to light) + 2 accents (saturated, bright pixels), as restyle.py.
The source folder comes from --src or the collection's meta.json (written by ingest.py).
"""
import argparse, json, os, shutil, sys
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from features import features  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('collection')
ap.add_argument('--src')
ap.add_argument('--only', default='')
a = ap.parse_args()
C = os.path.join(ROOT, 'taste', 'data', 'collections', a.collection)
D = os.path.join(ROOT, 'taste', 'data')
src = a.src or json.load(open(os.path.join(C, 'meta.json')))['src']
rows = {r['idx']: r for r in json.load(open(os.path.join(C, 'inventory.json'))) if 'idx' in r}
T = np.load(os.path.join(C, 'thumbs64.npy'))
tags = json.load(open(os.path.join(C, 'tags.json')))
only = [s for s in a.only.split(',') if s]
todo = {k.split(':')[-1]: v for k, v in tags.items() if (k in only if only else not k.startswith('_'))}

hexs = lambda cs: ['#%02x%02x%02x' % tuple(int(v) for v in c) for c in cs]
lum = lambda c: c @ [0.299, 0.587, 0.114]
members, palettes = {}, {}
for p in ('members.json', 'palettes.json'):
    f = os.path.join(C, p)
    (members if p == 'members.json' else palettes).update(json.load(open(f)) if os.path.exists(f) else {})
os.makedirs(os.path.join(D, 'contact-sheets'), exist_ok=True)
for name, m in todo.items():
    members[name] = sorted(m)
    px = np.concatenate([T[i][::4, ::4].reshape(-1, 3) for i in m]).astype(float)
    base = sorted(KMeans(5, n_init=4, random_state=0).fit(px).cluster_centers_, key=lum)
    sat = (px.max(1) - px.min(1)) / (px.max(1) + 1e-6)
    vivid = px[(sat > 0.55) & (px.max(1) > 110)]
    acc = KMeans(2, n_init=4, random_state=0).fit(vivid).cluster_centers_ if len(vivid) > 50 else []
    palettes[name] = hexs(base) + hexs(acc)
    F = np.array([features(T[i], rows[i]['w'], rows[i]['h']) for i in m])
    order = [m[k] for k in np.argsort(np.linalg.norm(F - F.mean(0), axis=1))]
    big = [i for i in order if max(rows[i]['w'], rows[i]['h']) >= 1000 and rows[i]['w'] * rows[i]['h'] < 40e6]
    pick = (big + [i for i in order if i not in big])[:8]
    out = os.path.join(D, 'exemplars', name)
    shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    for i in pick:
        s = os.path.abspath(os.path.join(src, rows[i]['path']))
        if os.name == 'nt' and len(s) > 240:
            s = '\\\\?\\' + s  # Windows long-path prefix
        shutil.copy2(s, os.path.join(out, f'{a.collection}-{i:04d}' + rows[i]['ext']))
    S = Image.new('RGB', (4 * 220, 2 * 140), (20, 20, 20))
    for k, i in enumerate(pick):
        t = Image.open(os.path.join(C, 'thumbs', f'{i}.jpg')); t.thumbnail((216, 136)); S.paste(t, ((k % 4) * 220, (k // 4) * 140))
    S.save(os.path.join(D, 'contact-sheets', f'exemplars-{name}.jpg'), quality=80)
    print(f'{name:22} {len(m):4}  ' + ' '.join(palettes[name]))
json.dump(members, open(os.path.join(C, 'members.json'), 'w'))
json.dump(palettes, open(os.path.join(C, 'palettes.json'), 'w'), indent=1)
