"""Add a folder of images you like (a "collection") to the taste: steps 1-2 of the procedure in the README.

Usage (from the project root):
  .venv/Scripts/python -I scripts/ingest.py <folder> --name <collection> [--far 1.0]

Step 1, inventory and dedupe: reads every image under <folder> (sub-folder names are kept as a "group" hint,
e.g. an artist), makes thumbnails, and marks duplicates inside the collection and against everything already
ingested (the original wallpapers in taste/data/inventory.json and other collections).
Step 2, triage: if styles exist (taste/data/style_members.json), each image gets the top-3 closest styles by
colour and composition (scripts/nearest.py, a hint only: right ~1/3 of the time as first choice). Images close to
a style go to "fits" sheets per style; images far from every style go to "new" sheets, the candidates for new
styles. With no styles yet (a fresh fork), everything goes to "new".

Writes, all local and git-ignored (the images belong to their creators):
  taste/data/collections/<name>/inventory.json   one row per file (path, group, size, phash, status, triage)
  taste/data/collections/<name>/thumbs/<idx>.jpg + thumbs64.npy
  taste/data/collections/<name>/sheets/*.jpg     numbered contact sheets of 48 (number = idx)
  taste/data/collections/<name>/REVIEW.md        counts and the next steps (3-5: tag by eye, propose, test)
Only standard Python + numpy, scipy, scikit-learn, Pillow (no extra packages). Rerunning rebuilds the folder.
"""
import argparse, collections, datetime, json, os, shutil, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy.fftpack import dct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from features import features  # noqa: E402

Image.MAX_IMAGE_PIXELS = 300_000_000
try:
    import pillow_avif  # noqa: F401  (older Pillow without AVIF)
except Exception:
    pass
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.tif', '.tiff', '.bmp'}
DUP = 6  # phash bits apart that still count as the same image (same as scripts/build/dupes.py)


def phash(t):
    """64-bit perceptual hash, same recipe as imagehash.phash, so hashes compare with the 8 Nov inventory."""
    a = np.asarray(t.convert('L').resize((32, 32), Image.LANCZOS), dtype=float)
    low = dct(dct(a, axis=0), axis=1)[:8, :8]
    bits = ''.join('1' if b else '0' for b in (low > np.median(low)).ravel())
    return f'{int(bits, 2):016x}'


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count('1')


def inventory(src, out):
    rows, thumbs = [], []
    for dp, dn, fn in os.walk(src):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, src)
            parts = rel.split(os.sep)
            r = {'path': rel, 'group': parts[-2] if len(parts) > 1 else '-',
                 'ext': os.path.splitext(f)[1].lower(), 'bytes': os.path.getsize(p)}
            if r['ext'] not in EXTS:
                r['status'] = 'non-image'; rows.append(r); continue
            try:
                im = Image.open(p)
                r['w'], r['h'] = im.size
                im.draft('RGB', (256, 256))
                im = im.convert('RGB')
                t = im.copy(); t.thumbnail((128, 128))
                r['phash'] = phash(t)
                r['idx'] = len(thumbs)
                thumbs.append(np.asarray(t.resize((64, 64))))
                t.save(os.path.join(out, 'thumbs', f'{r["idx"]}.jpg'), quality=85)
                r['status'] = 'ok'
            except Exception as ex:
                r['status'] = 'broken: ' + str(ex)[:80]
            rows.append(r)
            if len(rows) % 100 == 0:
                print(f'  {len(rows)} files read', flush=True)
    if thumbs:
        np.save(os.path.join(out, 'thumbs64.npy'), np.stack(thumbs))
    return rows


def dedupe(rows, name):
    """Mark duplicates: first against earlier collections, then inside this one (keep the biggest copy)."""
    seen = []
    inv = os.path.join(ROOT, 'taste', 'data', 'inventory.json')
    if os.path.exists(inv):
        seen += [('wallpapers', r['phash']) for r in json.load(open(inv)) if r.get('phash')]
    cdir = os.path.join(ROOT, 'taste', 'data', 'collections')
    for c in sorted(os.listdir(cdir)):
        f = os.path.join(cdir, c, 'inventory.json')
        if c != name and os.path.exists(f):
            seen += [(c, r['phash']) for r in json.load(open(f)) if r.get('phash') and 'dup_of' not in r]
    ok = sorted((r for r in rows if r['status'] == 'ok'), key=lambda r: -r['w'] * r['h'])
    kept = []
    for r in ok:
        hit = next((s for s, h in seen if hamming(r['phash'], h) <= DUP), None)
        if hit:
            r['dup_of'] = hit; continue
        twin = next((k for k in kept if hamming(r['phash'], k['phash']) <= DUP), None)
        if twin:
            r['dup_of'] = f'{name}:{twin["idx"]}'; continue
        kept.append(r)
    return kept


def triage(kept, out, far):
    members = os.path.join(ROOT, 'taste', 'data', 'style_members.json')
    if not os.path.exists(members):
        for r in kept:
            r['triage'] = 'new'
        return
    from nearest import model
    score = model(ROOT).score
    T = np.load(os.path.join(out, 'thumbs64.npy'))
    for r in kept:
        top, ratio = score(T[r['idx']], r['w'], r['h'])
        r['top3'] = [s for s, _ in top]
        r['fit'] = round(ratio, 2)  # distance / the style's own 90th percentile: <= 1 sits inside the style
        r['triage'] = 'fits' if ratio <= far else 'new'


def sheets(rows, out, label):
    cols, cell, per = 8, 160, 48
    files = []
    for k in range(0, len(rows), per):
        chunk = rows[k:k + per]
        S = Image.new('RGB', (cols * cell, ((len(chunk) + cols - 1) // cols) * cell), (20, 20, 20))
        d = ImageDraw.Draw(S)
        for i, r in enumerate(chunk):
            t = Image.open(os.path.join(out, 'thumbs', f'{r["idx"]}.jpg')); t.thumbnail((cell - 6, cell - 22))
            x, y = (i % cols) * cell, (i // cols) * cell
            S.paste(t, (x + 3 + (cell - 6 - t.width) // 2, y + 3))
            d.text((x + 4, y + cell - 17), str(r['idx']), fill=(255, 220, 120))
        f = f'{label}-{k // per + 1:02d}.jpg'
        S.save(os.path.join(out, 'sheets', f), quality=80)
        files.append(f)
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('folder')
    ap.add_argument('--name', required=True, help='short collection name, e.g. art')
    ap.add_argument('--far', type=float, default=1.0,
                    help='how far from a style still "fits" (1.0 = inside 90%% of its members)')
    a = ap.parse_args()
    src = os.path.abspath(os.path.expanduser(a.folder))
    out = os.path.join(ROOT, 'taste', 'data', 'collections', a.name)
    if os.path.exists(out):
        shutil.rmtree(out)
    for sub in ('thumbs', 'sheets'):
        os.makedirs(os.path.join(out, sub))

    print(f'1/3 inventory of {src}')
    rows = inventory(src, out)
    print('2/3 duplicates')
    kept = dedupe(rows, a.name)
    print('3/3 triage against the styles')
    triage(kept, out, a.far)

    by_style = collections.defaultdict(list)
    for r in kept:
        by_style[r['top3'][0] if r['triage'] == 'fits' else '_new'].append(r)
    sheet_files = {}
    for s, rs in sorted(by_style.items()):
        rs.sort(key=lambda r: (r['group'], r['idx']))
        sheet_files[s] = sheets(rs, out, 'new' if s == '_new' else f'fits-{s}')
    json.dump(rows, open(os.path.join(out, 'inventory.json'), 'w'), indent=1)

    status = collections.Counter(r['status'].split(':')[0] for r in rows)
    skipped = collections.Counter(r['ext'] for r in rows if r['status'] == 'non-image')
    dups = collections.Counter(r['dup_of'].split(':')[0] for r in rows if 'dup_of' in r)
    groups = collections.Counter(r['group'] for r in kept)
    lines = [f'# Collection "{a.name}" – ingested {datetime.date.today().isoformat()}', '',
             f'Source: `{src}` (local, never published).', '',
             f'- Files: {len(rows)} – images {status["ok"]}, broken {status["broken"]}, '
             f'skipped {sum(skipped.values())} ({", ".join(f"{n} {e}" for e, n in skipped.most_common())})',
             f'- Duplicates dropped: {sum(dups.values())} ({", ".join(f"{n} of {c}" for c, n in dups.most_common()) or "none"})',
             f'- Unique images: {len(kept)} in {len(groups)} groups', '',
             '## Triage (a hint: colour and composition only)', '',
             '| Bucket | Images | Sheets |', '|---|---|---|']
    for s, rs in sorted(by_style.items(), key=lambda t: -len(t[1])):
        lines.append(f'| {"new (far from every style)" if s == "_new" else "fits " + s} | {len(rs)} | '
                     + ', '.join(f'[{f}](sheets/{f})' for f in sheet_files[s]) + ' |')
    lines += ['', 'The guess sees colour and composition, not subject or medium: a collection unlike the styles '
              '(e.g. art vs wallpapers) lands in "fits" buckets by colour alone. Check one sheet by eye before '
              'trusting the buckets; the groups below are often the better hint.', '',
              '## Groups (sub-folders)', '', '| Group | Images |', '|---|---|']
    lines += [f'| {g} | {n} |' for g, n in groups.most_common()]
    lines += ['', '## Next (README, "Add a collection")', '',
              '3. Claude tags each image by eye on the sheets (subject, medium, mood, light), "new" sheets first.',
              '4. Claude proposes new styles and edits to existing ones; Marc approves each; restyle, build_taste.py.',
              '5. 2-3 Codex images per new style, rated in the app; distil after ~20 ratings.']
    open(os.path.join(out, 'REVIEW.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[4:]))
    print(f'\nreview: {os.path.relpath(os.path.join(out, "REVIEW.md"), ROOT)}')


if __name__ == '__main__':
    main()
