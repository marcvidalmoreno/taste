"""Rebuild step 2 (13 Nov 2026): from hand tags to style members, measured palettes and exemplars.

Usage: .venv/Scripts/python -I scripts/build/restyle.py <wallpaper-root> <project-root>
Reads (local, git-ignored): taste/data/review/tags.json (one tag per image, set by eye on contact sheets)
and taste/data/review/proposal.json (style -> tags, approved by Marc).
Writes: taste/data/style_members.json (style -> image idx; used by scripts/nearest.py),
taste/data/exemplars/<style>/ (8 copies per style, local only), taste/data/contact-sheets/exemplars-<style>.jpg,
and prints a measured palette per style: 5 base colours (k-means on the thumbnails' pixels, dark to light)
plus 2 accents (k-means on the saturated, bright pixels only).
"""
import json, os, sys, shutil, collections
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

src, root = sys.argv[1], sys.argv[2]
D = os.path.join(root, 'taste', 'data')
sys.path.insert(0, os.path.join(root, 'scripts'))
from features import features  # noqa: E402

tags = {int(k): v for k, v in json.load(open(os.path.join(D, 'review', 'tags.json'))).items()}
styles = json.load(open(os.path.join(D, 'review', 'proposal.json')))['styles']
rows = {r['idx']: r for r in json.load(open(os.path.join(D, 'clusters_k5.json')))}
T = np.load(os.path.join(D, 'thumbs64.npy'))
members, palettes = {}, {}
for name, tg in styles.items():
    m = sorted(i for i, t in tags.items() if t in tg)
    members[name] = m
    px = np.concatenate([T[i][::4, ::4].reshape(-1, 3) for i in m]).astype(float)
    lum = lambda c: c @ [0.299, 0.587, 0.114]
    base = sorted(KMeans(5, n_init=4, random_state=0).fit(px).cluster_centers_, key=lum)
    sat = (px.max(1) - px.min(1)) / (px.max(1) + 1e-6)
    vivid = px[(sat > 0.55) & (px.max(1) > 110)]
    acc = KMeans(2, n_init=4, random_state=0).fit(vivid).cluster_centers_ if len(vivid) > 50 else []
    hexs = lambda cs: ['#%02x%02x%02x' % tuple(int(v) for v in c) for c in cs]
    palettes[name] = hexs(base) + hexs(acc)
    F = np.array([features(T[i], rows[i]['w'], rows[i]['h']) for i in m])
    d = np.linalg.norm(F - F.mean(0), axis=1)
    order = [m[k] for k in np.argsort(d)]
    big = [i for i in order if max(rows[i]['w'], rows[i]['h']) >= 1200 and rows[i]['w'] * rows[i]['h'] < 40e6]
    pick = (big + [i for i in order if i not in big])[:8]
    out = os.path.join(D, 'exemplars', name)
    os.makedirs(out, exist_ok=True)
    for i in pick:
        shutil.copy2(os.path.join(src, rows[i]['path']), os.path.join(out, f'{i:04d}_' + os.path.basename(rows[i]['path'])))
    S = Image.new('RGB', (4 * 220, 2 * 140), (20, 20, 20))
    for k, i in enumerate(pick):
        t = Image.open(os.path.join(D, 'thumbs', f'{i}.jpg')); t.thumbnail((216, 136)); S.paste(t, ((k % 4) * 220, (k // 4) * 140))
    S.save(os.path.join(D, 'contact-sheets', f'exemplars-{name}.jpg'), quality=80)
json.dump(members, open(os.path.join(D, 'style_members.json'), 'w'))
json.dump(palettes, open(os.path.join(D, 'review', 'palettes.json'), 'w'), indent=1)
for k, v in palettes.items():
    print(k, len(members[k]), ' '.join(v))
