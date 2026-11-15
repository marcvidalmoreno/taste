"""Re-measure a style's palette from ALL its images: the original wallpapers and every collection (ART, inbox...).

Usage: .venv/Scripts/python -I scripts/build/remeasure.py <style> [<style> ...] [--groups N] [--write]
Without --write it prints old vs new palette and the image count per source, and changes nothing.
With --write (after Marc's OK) it updates "palette" in taste/styles/<style>.json; then run scripts/build_taste.py.
--groups N splits the images into N colour families and measures one palette per family; with --write it
stores them as "palettes" (options a batch rotates through), leaving "palette" as it was.
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
groups = int(sys.argv[sys.argv.index('--groups') + 1]) if '--groups' in sys.argv else 1
names = [a for a in sys.argv[1:] if not a.startswith('--') and not (sys.argv.index(a) > 0 and sys.argv[sys.argv.index(a) - 1] == '--groups')]
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
    if groups > 1:
        # Split the style's images into colour families (k-means on each image's mean colour and spread),
        # one palette per family, biggest family first. Gives the "palettes" options of a style.
        from sklearn.cluster import KMeans
        f = np.array([np.concatenate([t.reshape(-1, 3).mean(0), t.reshape(-1, 3).std(0)]) for t in thumbs])
        lab = KMeans(groups, n_init=8, random_state=0).fit_predict(f)
        fams = sorted(range(groups), key=lambda g: -(lab == g).sum())
        new_list = [palette([t for t, l in zip(thumbs, lab) if l == g]) for g in fams]
        print(f'{name} ({", ".join(counts)})  {groups} colour families')
        for g, p in zip(fams, new_list):
            print(f'  {(lab == g).sum():3d} images  {" ".join(p)}')
        if write:
            style['palettes'] = new_list
            json.dump(style, open(path, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
            print('  written')
        continue
    new = palette(thumbs)
    print(f'{name} ({", ".join(counts)})\n  old {" ".join(style["palette"])}\n  new {" ".join(new)}')
    if write:
        style['palette'] = new
        json.dump(style, open(path, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        print('  written')
