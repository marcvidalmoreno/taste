"""Export the pictures Marc picked in the app (Publish) to the public taste-gallery site.

  .venv/Scripts/python -I scripts/publish.py --dry-run          # list what would be written, write nothing
  .venv/Scripts/python -I scripts/publish.py --sync             # write images + JSON into the gallery repo's docs/
  .venv/Scripts/python -I scripts/publish.py --sync --picks f.json --out some/folder   # a sample, elsewhere

Only the picks are exported (generated/codex/publish.json, written by the app). Public text per picture: style name,
date and the subject line. Never style text (styles are private in taste-private), never prompts, ratings' "why",
paths or names. Besides the pictures it writes aggregate evolution data: per style the dates of style edits
(dates only, plus a fixed label for how: distilled, feedback in the app, with Claude), runs and ratings per day for each
style and for all styles together, and the public README changelog (first sentences).

Every run ends with a privacy check on everything it would write; if it finds a local path, 'refs/', 'taste/data',
a name or a piece of style text in a subject, it stops before writing anything (exit 2).

Output (OUT = ../taste-gallery/docs by default):
  OUT/data/images.json      one row per pick: id, style, date, subject, mode, w, h, group, rating
  OUT/data/styles.json      style key -> display name (names only)
  OUT/data/data.js          the three files above as one script (the site opens by double-click, where fetch() is blocked)
  OUT/data/evolution.json   per style: first date, edit dates and kinds, daily runs and ratings; totals; the changelog;
                            'examples': up to 3 thumbs-up pictures per style version (styles with a pick only)
  OUT/img/<id>.webp         about 1600 px on the long side;  OUT/img/t/<id>.webp  about 800 px
Ids are a short hash of batch/name: folder names never go public.
"""
import argparse, csv, hashlib, json, re, subprocess, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'generated' / 'codex'
STYLES = ROOT / 'taste' / 'styles'
DEFAULT_OUT = ROOT.parent / 'taste-gallery' / 'docs'
EXAMPLES = 3               # thumbs-up examples per style version on the Evolution page
LARGE, THUMB = 1600, 800   # thumbs fill a grid tile, often 600+ px wide on a high-DPI screen
NAME_BLOCKLIST = ['marc', 'mvidal', 'vidal', 'manara']   # lower-case words that must never appear in the output
STYLE_FIELDS = ('description', 'light', 'composition', 'camera_or_medium', 'mood', 'texture_detail', 'avoid', 'prefer')


def read_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def flat(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from flat(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from flat(x)


# ------------------------------------------------------------------ styles

def load_styles():
    """{key: style dict} for styles on and off (archived)."""
    out = {}
    for folder in (STYLES / 'archived', STYLES):
        for p in sorted(folder.glob('*.json')) if folder.exists() else []:
            d = read_json(p, None)
            if isinstance(d, dict):
                out[p.stem] = d
    return out


def style_fragments(styles):
    """Pieces of style text (12+ characters) that must never show up in a public file. The 'subjects' list is
    left out: those are example subjects, and a picture's subject line may be one of them."""
    frags = set()
    for d in styles.values():
        for f in STYLE_FIELDS:
            for t in flat(d.get(f, '')):
                for piece in re.split(r'[.;]\s', t):
                    piece = piece.strip().strip('.').lower()
                    if len(piece) >= 12:
                        frags.add(piece)
    return frags


# ------------------------------------------------------------------ subjects

def subject_of(prompt, style):
    """The subject line of a prompt, or '' when none is found: 'Subject: X. <style text>' or
    'change only the subject to: X. Style notes'. Cut where the style's own text begins."""
    m = re.search(r'change only the subject to:\s*(.+?)\.\s+Style notes', prompt, re.S)
    if m:
        return clean_subject(m.group(1))
    m = re.search(r'Subject:\s*(.+)', prompt, re.S)
    if not m:
        return ''
    rest = m.group(1)
    desc = (style or {}).get('description', '').strip()
    cut = rest.find(desc[:25]) if len(desc) >= 25 else -1
    if cut > 0:
        rest = rest[:cut]
    else:
        rest = re.split(r'\.\s+(?=[A-Z])', rest, maxsplit=1)[0]
    return clean_subject(rest)


def clean_subject(t):
    t = re.sub(r'\s+', ' ', t).strip().rstrip('.').strip()
    if len(t) > 160:
        t = t[:160].rsplit(' ', 1)[0] + '…'
    return t


# ------------------------------------------------------------------ data

def latest_ratings():
    out = {}
    p = BASE / 'ratings.csv'
    if p.exists():
        for r in csv.DictReader(open(p, encoding='utf-8')):
            out[(r['batch'], r['name'])] = r['rating']
    # 'cleared' means Marc took a rating back: the picture counts as unrated
    return {k: v for k, v in out.items() if v in ('keep', 'almost', 'no')}


def read_runs():
    runs = {}
    p = BASE / 'runs.csv'
    for r in csv.DictReader(open(p, encoding='utf-8')):
        runs[(r['batch'], r['name'])] = r   # the last row per image wins
    return runs


def image_id(batch, name):
    return hashlib.sha1(f'{batch}/{name}'.encode('utf-8')).hexdigest()[:10]


def week_of(d):
    y, m, dd = (int(x) for x in d.split('-'))
    x = date(y, m, dd)
    return (x - timedelta(days=x.weekday())).isoformat()


def git_style_dates():
    """{style key: {dates}}: days on which a style file changed, from the public history before the styles moved to
    the private repo plus the private repo itself. Dates only."""
    out = defaultdict(set)

    def scan(repo, pathspec, prefix, skip):
        try:
            txt = subprocess.run(['git', '-C', str(repo), 'log', '--name-only', '--format=@@%ad|%s', '--date=short', '--', pathspec],
                                 capture_output=True, text=True, encoding='utf-8', check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            return
        day, skipped = '', False
        for line in txt.splitlines():
            if line.startswith('@@'):
                day, _, subj = line[2:].partition('|')
                skipped = any(s in subj for s in skip)
            elif line.startswith(prefix) and line.endswith('.json') and not skipped:
                key = line[len(prefix):-5]
                if '/' not in key:
                    out[key].add(day)
    scan(ROOT, 'taste/styles', 'taste/styles/', ('Move styles to a private repo', 'Untrack generated'))
    scan(ROOT / 'taste', 'styles', 'styles/', ('moved from the public taste repo',))
    return out


EDIT_KIND = {'distil': 'distilled from ratings', 'codex': 'feedback in the app', 'words': 'feedback in the app'}


def edit_dates():
    """{style: {date: kind}} for edits made from the web app. Kind is a fixed public label, never the edit's text."""
    out = defaultdict(dict)
    for e in read_json(BASE / 'style-edits.json', []):
        if isinstance(e, dict) and not e.get('undone') and e.get('style') and e.get('at'):
            out[e['style']][e['at'][:10]] = EDIT_KIND.get(e.get('how'), 'feedback in the app')
    return out


def changelog():
    """Public README changelog: date and the first sentence of each entry."""
    txt = (ROOT / 'README.md').read_text(encoding='utf-8')
    body = txt.split('## Changelog', 1)[-1]
    out = []
    for m in re.finditer(r'^- \*\*(\d{1,2} \w{3} \d{4})\*\* – (.+?)(?=^- \*\*|\Z)', body, re.S | re.M):
        text = re.sub(r'\s+', ' ', m.group(2)).strip()
        text = re.sub(r'`([^`]*)`', r'\1', text)
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)   # links: keep the words, drop the paths
        first = re.split(r'(?<=[.!?])\s', text, maxsplit=1)[0]
        if len(first) > 200:
            first = first[:200].rsplit(' ', 1)[0] + '…'
        out.append({'date': m.group(1), 'text': first})
    return out


def build(picks, styles, runs, ratings):
    keys = {k: d.get('name', k) for k, d in styles.items()}
    images, skipped = [], []

    def image_row(key, run, src):
        st = run.get('style', '')
        return {
            'id': image_id(*key), 'style': st, 'date': run.get('date') or key[0][:10],
            'subject': subject_of(run.get('prompt', ''), styles.get(st)),
            'mode': {'test': 'from the style', 'text': 'from text'}.get(run.get('mode'), run.get('mode', '')),
            'w': int(run.get('width') or 1672), 'h': int(run.get('height') or 941),
            'group': image_id(key[0], ''), 'rating': {'keep': 'up', 'no': 'down'}.get(ratings.get(key), ''),
            '_src': src,
        }

    for p in picks:
        key = (p['batch'], p['name'])
        run = runs.get(key)
        src = BASE / p['batch'] / f"{p['name']}.png"
        if not run or not src.is_file():
            skipped.append(f"{p['batch']}/{p['name']} (missing)")
            continue
        images.append(image_row(key, run, src))
    images.sort(key=lambda i: (i['date'], i['id']))

    # evolution: every style that has a pick, or any run at all? Only styles with a pick, to keep the site small.
    used = sorted({i['style'] for i in images if i['style']})
    gdates, edates = git_style_dates(), edit_dates()
    daily = defaultdict(lambda: defaultdict(lambda: {'runs': 0, 'up': 0, 'almost': 0, 'down': 0}))
    every = defaultdict(lambda: {'runs': 0, 'up': 0, 'almost': 0, 'down': 0, 'styles': set()})
    for (batch, name), r in runs.items():
        st, d = r.get('style', ''), r.get('date', '')
        if not d or r.get('ok', 'yes') != 'yes':
            continue
        rt = {'keep': 'up', 'almost': 'almost', 'no': 'down'}.get(ratings.get((batch, name)))
        rows = [every[d]] + ([daily[st][d]] if st in used else [])
        for row in rows:
            row['runs'] += 1
            if rt:
                row[rt] += 1
        if st:
            every[d]['styles'].add(st)
    evo = {}
    for st in used:
        made = sorted(gdates.get(st, set()) | set(edates.get(st, {})))
        evo[st] = {'name': keys.get(st, st), 'first': made[0] if made else '', 'edits': made[1:],
                   'kinds': {d: edates.get(st, {}).get(d, 'edited with Claude') for d in made[1:]},
                   'days': [{'day': d, **v} for d, v in sorted(daily[st].items())]}
    days = [{'day': d, **{k: v for k, v in r.items() if k != 'styles'}, 'styles': len(r['styles'])} for d, r in sorted(every.items())]
    n_edits = sum(len(dates) - 1 for st in set(gdates) | set(edates)
                  for dates in [gdates.get(st, set()) | set(edates.get(st, {}))] if dates)
    totals = {'runs': sum(r['runs'] for r in days), 'up': sum(r['up'] for r in days), 'almost': sum(r['almost'] for r in days),
              'down': sum(r['down'] for r in days), 'styles': len({s for r in every.values() for s in r['styles']}),
              'edits': n_edits, 'days': days}

    # Evolution examples (Marc, 24 Nov 2026): besides the picks, up to EXAMPLES thumbs-up pictures per style version,
    # spread over the version's days, so each column shows what that version made. Only for styles that have a pick
    # (a style Marc never published stays off the site), never a picture already picked. Evolution page only.
    picked = {i['id'] for i in images}
    pool = defaultdict(list)
    for key, r in runs.items():
        st = r.get('style', '')
        if st in evo and r.get('ok', 'yes') == 'yes' and ratings.get(key) == 'keep' and image_id(*key) not in picked and r.get('date'):
            src = BASE / key[0] / f'{key[1]}.png'
            if src.is_file():
                pool[st].append((r['date'], r.get('time', ''), key, r, src))
    examples = []
    for st, e in evo.items():
        cuts = [''] + e['edits'] + ['9999']
        cands = sorted(pool[st], key=lambda c: (c[0], c[1], c[2]))
        for lo, hi in zip(cuts, cuts[1:]):
            g = [c for c in cands if lo <= c[0] < hi]
            n = min(EXAMPLES, len(g))
            for j in range(n):
                c = g[round(j * (len(g) - 1) / max(1, n - 1))] if n > 1 else g[len(g) // 2]
                examples.append({**image_row(c[2], c[3], c[4]), 'example': True})
    examples.sort(key=lambda i: (i['date'], i['id']))
    return images, examples, {k: keys[k] for k in used if k in keys}, {'styles': evo, 'all': totals, 'changelog': changelog()}, skipped


# ------------------------------------------------------------------ privacy check

def privacy_check(texts, styles):
    """texts: {label: string} of everything that would be written as text. Returns a list of problems."""
    frags = style_fragments(styles)
    bad = []
    for label, t in texts.items():
        low = t.lower()
        for token in ('c:\\', 'c:/', '\\\\', 'refs/', 'taste/data', 'taste-private', '.venv'):
            if token in low:
                bad.append(f'{label}: contains "{token}"')
        for n in NAME_BLOCKLIST + ['users']:
            if re.search(r'\b' + n + r'\b', low):
                bad.append(f'{label}: contains the name "{n}"')
        if label != 'changelog.text':
            for f in frags:
                if f in low:
                    bad.append(f'{label}: contains style text "{f[:30]}…"')
                    break
    return bad


def check_all(images, names, evo, styles):
    texts = {}
    for i in images:
        for k in ('subject', 'style', 'mode', 'date'):
            texts[f"image {i['id']}.{k}"] = str(i[k])
    for k, n in names.items():
        texts[f'style name {k}'] = n
    # The changelog is the public README: it may name a style, but never quote one. Entries that trip the check are
    # dropped (reported), the rest is kept.
    keep, dropped = [], []
    names = {k.lower() for k in styles} | {(d.get('name') or '').lower() for d in styles.values() if d.get('name')}
    for c in evo['changelog']:
        low = c['text'].lower()
        # entries about a style's content (it names a style, or says avoid / prefer) never go public: they paraphrase style text
        if any(n and n in low for n in names) or re.search(r'(avoid|prefer)', low):
            dropped.append(c)
        elif privacy_check({'changelog.text': c['text']}, {}):
            dropped.append(c)
        elif privacy_check({f'changelog {c["date"]}': c['text']}, styles):
            dropped.append(c)
        else:
            keep.append(c)
    evo['changelog'] = keep
    return privacy_check(texts, styles), dropped


# ------------------------------------------------------------------ writing

def export(images, out):
    from PIL import Image
    n = 0
    for i in images:
        large, thumb = out / 'img' / f"{i['id']}.webp", out / 'img' / 't' / f"{i['id']}.webp"
        src = i['_src']
        if (large.exists() and thumb.exists() and large.stat().st_mtime >= src.stat().st_mtime
                and max(Image.open(thumb).size) >= min(THUMB, max(Image.open(src).size))):
            continue
        large.parent.mkdir(parents=True, exist_ok=True)
        thumb.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(src).convert('RGB')
        big = im.copy()
        big.thumbnail((LARGE, LARGE))
        big.save(large, 'WEBP', quality=82, method=6)
        im.thumbnail((THUMB, THUMB))
        im.save(thumb, 'WEBP', quality=78, method=6)
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run', action='store_true', help='list what would be written; write nothing')
    g.add_argument('--sync', action='store_true', help='write images and JSON')
    ap.add_argument('--picks', default=str(BASE / 'publish.json'), help='picks file (default: the app\'s publish.json)')
    ap.add_argument('--out', default=str(DEFAULT_OUT), help='output folder (default: ../taste-gallery/docs)')
    a = ap.parse_args()
    out = Path(a.out)

    picks = [k for k in read_json(a.picks, []) if isinstance(k, dict) and k.get('batch') and k.get('name')]
    styles, runs, ratings = load_styles(), read_runs(), latest_ratings()
    images, examples, names, evo, skipped = build(picks, styles, runs, ratings)
    problems, dropped = check_all(images + examples, names, evo, styles)

    print(f'{len(picks)} picks, {len(images)} exportable, {len(examples)} evolution examples, {len(names)} styles, {len(evo["changelog"])} changelog entries')
    for s in skipped:
        print('  skipped:', s)
    for c in dropped:
        print(f'  changelog entry left out (privacy check): {c["date"]}')
    if problems:
        print('PRIVACY CHECK FAILED, nothing written:')
        for p in problems:
            print('  -', p)
        return 2
    print('privacy check passed')

    if a.dry_run:
        tot = 0
        for i in images:
            sz = i['_src'].stat().st_size
            tot += sz
            print(f"  img/{i['id']}.webp (+t/)  {i['style']:<26} {i['date']}  {i['subject'][:60]!r}")
        print(f'  data/images.json, data/styles.json, data/evolution.json into {out}')
        print(f'  source PNGs {tot / 1e6:.1f} MB (WebP will be roughly 10 percent of that)')
        return 0

    (out / 'data').mkdir(parents=True, exist_ok=True)
    made = export(images + examples, out)
    # remove pictures that are no longer picked
    keep_ids = {i['id'] for i in images + examples}
    for p in list((out / 'img').glob('*.webp')) + list((out / 'img' / 't').glob('*.webp')):
        if p.stem not in keep_ids:
            p.unlink()
    rows = [{k: v for k, v in i.items() if k != '_src'} for i in images]
    evo['examples'] = [{k: v for k, v in i.items() if k not in ('_src', 'example')} for i in examples]
    for fn, data in (('images.json', rows), ('styles.json', names), ('evolution.json', evo)):
        (out / 'data' / fn).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')
    # The site opens by double-click (file://), where fetch() of a JSON file is blocked: the same data as one script.
    (out / 'data' / 'data.js').write_text('window.TASTE = ' + json.dumps({'images': rows, 'styles': names, 'evolution': evo}, ensure_ascii=False) + ';',
                                          encoding='utf-8')
    print(f'wrote {len(rows)} pictures ({made} new images converted) and the data files to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
