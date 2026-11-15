"""Feed the taste with a few new images: drop them in the inbox, in the folder of the style they belong to.

Usage (from the project root):
  .venv/Scripts/python -I scripts/inbox.py            # process the inbox
  .venv/Scripts/python -I scripts/inbox.py --setup    # only (re)create one folder per style, process nothing

The inbox is `inbox/` in the project, or the folder set in taste/data/local.json as {"inbox": "<path>"} (e.g. a
synced cloud folder, so images can be saved from a phone or browser). Inside it:
  inbox/<style>/       one folder per style in taste/styles (created and kept up to date by this script):
                       the image joins that style as is, no guessing.
  inbox/<other name>/  a folder that's not a style: a candidate new style, tagged by eye with the loose files.
  inbox/<loose files>  not sure: Claude looks at the numbered sheet and tags them.

Each image is checked against everything ingested before (duplicates go to taste/data/added/_duplicates/), then
MOVED (never deleted) to taste/data/added/<style>/ and recorded in the "inbox" collection
(taste/data/collections/inbox/: inventory.json, thumbs, tags.json), so scripts/build/remeasure.py and
scripts/build/collection_styles.py see it like any other collection. All of taste/data is git-ignored.
Prints what joined which style, the sheet of images to tag, and the styles worth re-measuring.
"""
import argparse, collections, datetime, glob, json, os, shutil, sys
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from ingest import EXTS, DUP, phash, hamming, known_hashes  # noqa: E402

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
DATA = os.path.join(ROOT, 'taste', 'data')
COLL = os.path.join(DATA, 'collections', 'inbox')
ADDED = os.path.join(DATA, 'added')
NOTE = ('Drop images you like into the folder of their style. Not sure? Leave them here, loose.\n'
        'A new folder with another name = a candidate new style. Then tell Claude: "process my inbox".\n')


def inbox_dir():
    f = os.path.join(DATA, 'local.json')
    cfg = json.load(open(f, encoding='utf-8')) if os.path.exists(f) else {}
    return os.path.expanduser(cfg.get('inbox') or os.path.join(ROOT, 'inbox'))


def setup(box, styles):
    os.makedirs(box, exist_ok=True)
    made = [s for s in styles if not os.path.isdir(os.path.join(box, s))]
    for s in made:
        os.makedirs(os.path.join(box, s))
    with open(os.path.join(box, 'HOW-TO.txt'), 'w', encoding='utf-8') as f:
        f.write(NOTE)
    return made


def unique(path):
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f'{base}-{n}{ext}'; n += 1
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('root', nargs='?', help='ignored (old usage passed the project root)')
    ap.add_argument('--setup', action='store_true')
    a = ap.parse_args()
    styles = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(ROOT, 'taste', 'styles', '*.json')))
    box = inbox_dir()
    made = setup(box, styles)
    if made:
        print(f'new style folders in {box}: {", ".join(made)}')
    if a.setup:
        print(f'inbox ready: {box} ({len(styles)} style folders)'); return

    files = []
    for dp, dn, fn in os.walk(box):
        rel = os.path.relpath(dp, box)
        if rel.count(os.sep) > 0:
            continue  # one level of folders only
        for f in sorted(fn):
            if os.path.splitext(f)[1].lower() in EXTS:
                files.append((os.path.join(dp, f), '' if rel == '.' else rel))
    if not files:
        print(f'inbox is empty: {box}'); return

    os.makedirs(os.path.join(COLL, 'thumbs'), exist_ok=True)
    os.makedirs(os.path.join(COLL, 'sheets'), exist_ok=True)
    inv_f, tags_f, npy_f = (os.path.join(COLL, n) for n in ('inventory.json', 'tags.json', 'thumbs64.npy'))
    rows = json.load(open(inv_f)) if os.path.exists(inv_f) else []
    tags = json.load(open(tags_f)) if os.path.exists(tags_f) else {}
    T = list(np.load(npy_f)) if os.path.exists(npy_f) else []
    json.dump({'src': ADDED, 'note': 'images moved here by scripts/inbox.py'}, open(os.path.join(COLL, 'meta.json'), 'w'))
    seen = known_hashes(exclude='inbox') + [('inbox', r['phash']) for r in rows if r.get('phash') and 'dup_of' not in r]
    today = datetime.date.today().isoformat()
    joined, unsorted, dups, broken = collections.Counter(), [], [], []

    for path, folder in files:
        style = folder if folder in styles else None
        try:
            im = Image.open(path); w, h = im.size
            im.draft('RGB', (256, 256)); im = im.convert('RGB')
            t = im.copy(); t.thumbnail((128, 128))
            ph = phash(t)
        except Exception as ex:
            broken.append(f'{os.path.basename(path)} ({str(ex)[:60]})'); continue
        hit = next((s for s, x in seen if hamming(ph, x) <= DUP), None)
        if hit:
            d = os.path.join(ADDED, '_duplicates'); os.makedirs(d, exist_ok=True)
            shutil.move(path, unique(os.path.join(d, os.path.basename(path))))
            dups.append(f'{os.path.basename(path)} (already in {hit})'); continue
        sub = style or os.path.join('_unsorted', folder or '_loose')
        dest = unique(os.path.join(ADDED, sub, os.path.basename(path)))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(path, dest)
        idx = len(T)
        T.append(np.asarray(t.resize((64, 64))))
        t.save(os.path.join(COLL, 'thumbs', f'{idx}.jpg'), quality=85)
        r = {'path': os.path.relpath(dest, ADDED), 'group': folder or '-', 'ext': os.path.splitext(dest)[1].lower(),
             'w': w, 'h': h, 'phash': ph, 'idx': idx, 'status': 'ok', 'added': today}
        rows.append(r); seen.append(('inbox', ph))
        if style:
            tags.setdefault(style, []).append(idx); joined[style] += 1
        else:
            tags.setdefault('_unsorted', []).append(idx); unsorted.append(r)

    np.save(npy_f, np.stack(T)) if T else None
    json.dump(rows, open(inv_f, 'w'), indent=1)
    json.dump(tags, open(tags_f, 'w'), indent=0)

    for s, n in joined.most_common():
        print(f'+{n:3} {s}')
    if unsorted:
        cols, cell = 6, 200
        S = Image.new('RGB', (cols * cell, ((len(unsorted) + cols - 1) // cols) * cell), (20, 20, 20))
        d = ImageDraw.Draw(S)
        for i, r in enumerate(unsorted):
            t = Image.open(os.path.join(COLL, 'thumbs', f'{r["idx"]}.jpg')); t.thumbnail((cell - 6, cell - 24))
            x, y = (i % cols) * cell, (i // cols) * cell
            S.paste(t, (x + 3, y + 3)); d.text((x + 4, y + cell - 18), f'{r["idx"]} {r["group"][:20]}', fill=(255, 220, 120))
        sheet = os.path.join(COLL, 'sheets', f'unsorted-{today}.jpg')
        S.save(sheet, quality=82)
        print(f'{len(unsorted)} to tag by eye: {os.path.relpath(sheet, ROOT)}  (set tags in {os.path.relpath(tags_f, ROOT)})')
    for x in dups:
        print('duplicate, moved to taste/data/added/_duplicates/:', x)
    for x in broken:
        print('could not read, left in the inbox:', x)
    if joined:
        print('re-measure palettes (prints old vs new, changes nothing):',
              f'.venv/Scripts/python -I scripts/build/remeasure.py {" ".join(joined)}')


if __name__ == '__main__':
    main()
