"""Local web app to view, mark and save ratings for the images made through Codex.

Usage (from the project root):
  .venv/Scripts/python -I scripts/app.py              # starts on http://127.0.0.1:8777 and opens the browser
  .venv/Scripts/python -I scripts/app.py --no-browser --port 8780
  .venv/Scripts/python -I scripts/app.py --dry-run    # try the variations button without spending allowance

How the pieces fit
  app/ (HTML, CSS, JS in the browser)  <-- JSON over HTTP -->  this file  <-- files -->  generated/codex/
  - The browser never touches files: it asks this server, which reads and writes generated/codex/
    (git-ignored, so no image, rating or draft can reach the public repo).
  - Standard library only, plus Pillow for thumbnails. No framework, no build step.
  - Listens on 127.0.0.1 only: nothing on the network can reach it.
  - Restarts itself (23 Nov 2026): the started process only supervises; the server runs as its child and starts
    again, same port, when scripts/*.py changed and nothing is running (see supervise, restart_when_idle).

Files this server reads or writes (all in generated/codex/)
  <batch>/*.png        images (read), seed.* is the seed of a variations batch
  runs.csv             one row per generated image (read): style, change, seed, prompt
  ratings.csv          saved ratings (read; appended through rate.append_ratings)
  app-drafts.json      marks not saved yet, so they survive closing the tab (written)
  app-ignored.json     images hidden from the grid and left out of ratings (written)
  .look-index.json     colour and framing numbers per image for "More like this" (written, safe to delete)
  kept.json            images kept as examples of their style: [{batch, name, style, at}] (written; new batch and
                       single-image runs of that style send up to 2 of them along as references, 21 Nov 2026)
  .thumbs/             small JPEG copies for the grid (written, safe to delete)
  distil-state.json    where the last distil stopped (read only: --mark stays a command-line step)
  <batch>/run.json     what a run started here was, where it came from and how it was set (written)
  app-queue.json       runs waiting (written; app-queue.dry.json with --dry-run, so a test never runs for real)
  claude-notes.json    notes for Claude Code (written here, answered with scripts/notes.py)
  distil-run.json      the current distil round: Codex's proposal per style and what Marc decided (written)
  style-edits.json     style edits made here: before / after of each, for Undo (written; the style file itself is
                       taste/styles/<style>.json, rewritten in the repo's format, then build_taste.py)
  references/<style>/  reference images a style was started from in the page (written; other people's work,
                       so it stays here, git-ignored). references/.drafts/ holds them until "Create style"
  removed-styles/      a new style whose creation was undone (its file and references move here, never deleted)
  .progress.json       live progress of the running run (read; written by the run scripts)
  taste/styles/archived/  styles switched off on the Styles page (their file moves here; every script then skips them, 23 Nov 2026)
  .app-restart-<port>.json  the last runs and the port, handed from a server to the one that restarts it (deleted
                       on start)

Runs (21 Nov 2026): one queue, one image run at a time. New runs (batch.py), single images, remixes and retries
(run_list.py) and variations (variations.py) are queued from the page; a run started from chat holds the queue
until it ends. Codex also writes subjects and rewrites prompts (codex_text.py, read-only text jobs).

Marks are saved at once (21 Nov 2026): each Up / Down / take-back appends a row to ratings.csv, the latest row per
image wins (rate.latest). app-drafts.json is only read once, to save marks left from before.
"""
import argparse, csv, io, json, os, re, sys, threading, webbrowser, zipfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import rate  # noqa: E402  (shared paths and the one writer of ratings.csv)
import cf_run  # noqa: E402  (the Cloudflare route: FLUX on the free daily allowance, docs/cloudflare-route.md)

BASE = rate.BASE
APP_DIR = ROOT / 'app'
THUMBS = BASE / '.thumbs'
THUMB_SIZE = (640, 640)
DRAFTS = BASE / 'app-drafts.json'      # {batch: {name: {"rating": "keep", "why": "..."}}}
IGNORED = BASE / 'app-ignored.json'    # {batch: [name, ...]}
# Windows can map .js to text/plain in its registry; browsers then refuse ES modules. Be explicit.
TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.js': 'text/javascript; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml',
         '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
         '.md': 'text/plain; charset=utf-8'}
LOCK_SIMILAR = threading.Lock()  # one measuring pass at a time (scripts/similar.py)
LOCK = threading.Lock()  # one writer at a time for the small JSON files and thumbnails


# ---------------------------------------------------------------- small file helpers

def read_json(path, default):
    try:
        return json.load(open(path, encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    """Write to a temporary file, then swap it in: a crash never leaves half a file."""
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def saved_ratings():
    """ratings.csv as {(batch, name): row}: the latest mark per image, cleared marks left out."""
    if not rate.RATINGS.exists():
        return {}
    return {(r['batch'], r['name']): r for _, r in rate.latest(list(csv.DictReader(open(rate.RATINGS, encoding='utf-8'))))}


# ---------------------------------------------------------------- kept examples (21 Nov 2026)

KEPT = BASE / 'kept.json'     # [{batch, name, style, at}]: images Marc keeps as examples of their style
REFS_PER_IMAGE = 2            # how many kept examples go along with one new image


def kept_list():
    return [k for k in read_json(KEPT, []) if isinstance(k, dict) and k.get('batch') and k.get('name')]


def kept_set():
    return {(k['batch'], k['name']) for k in kept_list()}


def kept_paths(style):
    """Files of the images kept for a style, oldest first; ones that no longer exist are left out."""
    out = []
    for k in kept_list():
        p = BASE / k['batch'] / f"{k['name']}.png"
        if k.get('style') == style and p.is_file() and ',' not in str(p):
            out.append(str(p))
    return out


# ---------------------------------------------------------------- published picks (23 Nov 2026)

PUBLISH = BASE / 'publish.json'   # [{batch, name, style, at}]: images Marc picks for the public taste-gallery site


def publish_list():
    return [k for k in read_json(PUBLISH, []) if isinstance(k, dict) and k.get('batch') and k.get('name')]


def publish_set():
    return {(k['batch'], k['name']) for k in publish_list()}


GALLERY_SYNC_DELAY = 300   # seconds after the last Publish toggle before the site is synced (scripts/gallery_sync.py)
_gallery_timer = [None]


def schedule_gallery_sync(delay=GALLERY_SYNC_DELAY):
    """Debounced: every Publish toggle restarts the clock; when it runs out and no run is going, sync the site."""
    def fire():
        import subprocess
        busy = CUR.get('running') or QUEUE or (chat_run() or {}).get('running')
        if busy:
            return schedule_gallery_sync(60)   # try again in a minute, once nothing runs
        subprocess.Popen([PY, '-I', str(ROOT / 'scripts' / 'gallery_sync.py'), 'after Publish in the app'], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if _gallery_timer[0]:
        _gallery_timer[0].cancel()
    t = threading.Timer(delay, fire)
    t.daemon = True
    _gallery_timer[0] = t
    t.start()


def pick_refs(paths, i):
    """The kept examples that go with image number i of a style: REFS_PER_IMAGE of them, turning through the list."""
    n = min(REFS_PER_IMAGE, len(paths))
    return [paths[(i * REFS_PER_IMAGE + k) % len(paths)] for k in range(n)]


# ---------------------------------------------------------------- batches and images

def is_batch(name):
    """A batch is a folder directly inside generated/codex/ (never '..', never a hidden folder)."""
    return bool(name) and not name.startswith('.') and '/' not in name and '\\' not in name \
        and (BASE / name).is_dir()


def seed_file(batch):
    seeds = sorted(p.name for p in (BASE / batch).glob('seed.*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'))
    return seeds[0] if seeds else None


def all_runs():
    """runs.csv as {batch: {name: row}} (the last row per image wins, like rate.batch_runs)."""
    out = {}
    if rate.RUNS.exists():
        for r in csv.DictReader(open(rate.RUNS, encoding='utf-8')):
            out.setdefault(r['batch'], {})[r['name']] = r
    return out


def batch_images(batch, shared=None):
    """Every image of a batch with what the app shows about it.
    status: 'rated' (saved, read-only) > 'ignored' > 'draft' (marked, not saved) > 'new'.
    shared: (runs by batch, saved ratings, ignored) read once by list_batches, so the home page does not
    parse runs.csv and ratings.csv once per batch (that took ~1.4 s with 120 batches; 21 Nov 2026)."""
    if shared:
        runs_by_batch, saved, ignored_all, kept, pub = shared
        runs = runs_by_batch.get(batch, {})
    else:
        runs, saved, ignored_all, kept, pub = rate.batch_runs(batch), saved_ratings(), read_json(IGNORED, {}), kept_set(), publish_set()
    ignored = set(ignored_all.get(batch, []))
    out = []
    for i, name in enumerate(rate.batch_images(batch), 1):
        run = runs.get(name, {})
        s = saved.get((batch, name))
        # One mark per image, saved at once (21 Nov 2026): "draft" is the mark the page shows and changes,
        # "saved" stays empty (nothing is read-only any more). Old drafts are saved on start (migrate_drafts).
        status = 'rated' if s else 'ignored' if name in ignored else 'new'
        out.append({
            'name': name, 'file': f'{name}.png', 'number': i, 'status': status,
            'mtime': int((BASE / batch / f'{name}.png').stat().st_mtime),
            'style': run.get('style', ''), 'mode': run.get('mode', ''), 'change': run.get('change', ''),
            'seed': run.get('seed', ''), 'prompt': run.get('prompt', ''), 'route': run.get('route') or 'codex',
            'width': run.get('width', ''), 'height': run.get('height', ''),
            'date': run.get('date', ''), 'time': run.get('time', ''), 'seconds': run.get('seconds', ''),
            'draft': {'rating': s['rating'], 'why': s['why'], 'date': s['date']} if s else None,
            'saved': None, 'kept': (batch, name) in kept, 'published': (batch, name) in pub,
        })
    return out


def summary(batch, images):
    rec = run_record(batch)
    count = lambda st: sum(1 for im in images if im['status'] == st)  # noqa: E731
    return {'batch': batch, 'date': batch[:10], 'images': len(images),
            'to_rate': count('new') + count('draft'), 'drafts': count('draft'),
            'rated': count('rated'), 'ignored': count('ignored'),
            'newest': max((im['mtime'] for im in images), default=int((BASE / batch).stat().st_mtime)),
            'preview': [im['file'] for im in images if im['status'] != 'ignored'][:4],
            'seed': seed_file(batch), 'kind': kind_of_batch(batch, images, rec), 'title': (rec or {}).get('title', ''),
            'styles': sorted({im['style'] for im in images if im['style']})}


def list_batches():
    """All batches, newest image first."""
    names = [p.name for p in BASE.iterdir() if is_batch(p.name)] if BASE.exists() else []
    shared = (all_runs(), saved_ratings(), read_json(IGNORED, {}), kept_set(), publish_set())
    out = [summary(b, batch_images(b, shared)) for b in names]
    return sorted(out, key=lambda s: s['newest'], reverse=True)


def thumbnail(batch, file):
    """Small JPEG for the grid, made once and kept in .thumbs/ until the image changes."""
    from PIL import Image
    src = BASE / batch / file
    dst = THUMBS / batch / (Path(file).stem + '.jpg')
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        with LOCK:
            dst.parent.mkdir(parents=True, exist_ok=True)
            im = Image.open(src).convert('RGB')
            im.thumbnail(THUMB_SIZE)
            im.save(dst, quality=86)
    return dst


# ---------------------------------------------------------------- runs: one queue, one image run at a time

PY = sys.executable
CHANGES = ['palette', 'subject', 'composition', 'mood']   # the order scripts/variations.py makes them in
RATIO_CHOICES = ('mixed', 'wide', 'portrait', 'square')
WEEK_RATE = 0.1           # weekly % per image when the log can't measure it yet (README "Allowance", 23 Nov 2026)
DRY_RUN = False           # --dry-run: every run and text job is a dry run (no Codex, no allowance)
QUEUE_FILE = BASE / 'app-queue.json'    # runs waiting: a restart of the app keeps them
NOTES = BASE / 'claude-notes.json'      # notes for Claude Code (scripts/notes.py reads and answers them)
SPECS = BASE / '.app'                   # files of dry runs (subjects, jobs), deleted when the run ends
QUEUE = []                # specs waiting, first = next
CUR = {}                  # the run the app started last (running or finished); read by GET /api/job
PROC = {}                 # its process: {'p': Popen}
RECENT = []               # the last finished app runs, newest last: the page reports each one once, even when
                          # the next queued run starts at once
HOLD = {}                 # the queue is on hold: {'reason', 'since', 'auto'} (23 Nov 2026), see broken_scripts()
_QLOCK = threading.Lock()
_WAKE = threading.Event()
RESTART = 3                   # exit code: "start me again", for the supervisor (scripts/ changed, 23 Nov 2026)
BORN = [0.0]               # code_stamp() when this server started (set in main): a newer page may call a route it lacks
RESTARTING = threading.Event()  # set once a restart is decided: no new run or distil round starts after it
ACTIVE = [0]                  # requests being answered right now (a restart waits for them)
_ALOCK = threading.Lock()
_guess = None            # nearest.model, loaded on first use (a few seconds: sklearn + 1,000 thumbnails)
_GUESS_LOCK = threading.Lock()  # its own lock: loading it must not hold up marking
_lineage = {'key': None, 'map': {}}


def allowance():
    """Codex usage now (scripts/codex_run.py read: from Codex's own session log, never typed) plus the images made
    in this Codex week (since its weekly reset, Codex route only: FLUX on Cloudflare is free) and what one image
    costs of the week, measured from runs.csv (23 Nov 2026; was a rolling 7 days against a fixed budget)."""
    import datetime, subprocess
    r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'read'],
                       capture_output=True, text=True, encoding='utf-8', timeout=60)
    now = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip().startswith('{') else None
    resets = now and now.get('weekly_resets')
    start = (datetime.datetime.fromisoformat(resets) - datetime.timedelta(days=7)) if resets else         datetime.datetime.now() - datetime.timedelta(days=7)
    prev = start - datetime.timedelta(days=7)
    week, last_week, last_pct = 0, 0, None
    if rate.RUNS.exists():
        for row in csv.DictReader(open(rate.RUNS, encoding='utf-8')):
            if row['ok'] != 'yes' or (row.get('route') or 'codex') == 'cloudflare':
                continue
            try:
                t = datetime.datetime.fromisoformat(f"{row['date']}T{row['time'] or '00:00'}")
            except ValueError:
                continue
            if t >= start:
                week += 1
            elif t >= prev:
                last_week += 1
                if row.get('weekly_last'):
                    last_pct = float(row['weekly_last'])
    # % of the week per image: everything Codex used counts against images, so it errs on the safe side.
    if now and week >= 20:
        per = now['weekly'] / week
    elif last_week >= 20 and last_pct:
        per = last_pct / last_week
    else:
        per = WEEK_RATE
    queued = sum(len(s['expected']) for s in QUEUE)
    return {'now': now, 'unknown_reason': None if now else (r.stderr or r.stdout).strip()[-300:],
            'week_images': week, 'week_start': start.isoformat(timespec='minutes') if resets else None,
            'week_per_image': round(per, 3), 'dry_run': DRY_RUN, 'queued_images': queued,
            'cloudflare': cf_run.today()}   # FLUX's free day: connected, images today and left (an estimate)


def source_image(batch, file):
    """The image to vary: any PNG in a batch, the seed included."""
    if not is_batch(batch) or file.startswith('.') or '/' in file or '\\' in file \
            or not (BASE / batch / file).is_file() or Path(file).suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        raise ApiError(404, f'no image "{file}" in batch "{batch}"')
    return BASE / batch / file


def guess_styles(path):
    """Top-3 style guess, the same function variations.py uses without --style."""
    global _guess
    with _GUESS_LOCK:
        if _guess is None:
            from nearest import model
            _guess = model(str(ROOT))
    top, far, _ = _guess(str(path))
    # nearest.py still knows the styles switched off: leave them out
    return {'top': [{'style': s, 'distance': d} for s, d in top if (ROOT / 'taste' / 'styles' / f'{s}.json').is_file()], 'far': far}


def slugify(text, fallback='run'):
    return '-'.join(''.join(c if c.isalnum() else ' ' for c in text.lower()).split())[:32].strip('-') or fallback


def flux_end(body):
    """New FLUX runs get folders ending in -flux, so they stand out in Explorer and the batch list (23 Nov 2026)."""
    return '-flux' if (body or {}).get('route') == 'cloudflare' else ''


def free_slug(stem, end=''):
    """Folders are generated/codex/<today>-<slug>/; never reuse one (it would overwrite), nor one a queued
    run has already reserved. end: kept after the 24-character cut (-flux)."""
    import datetime
    base = slugify(stem, 'variations')[:24] + end
    day, slug, i = datetime.date.today().isoformat(), base, 2
    taken = {s['batch'] for s in QUEUE} | ({CUR['batch']} if CUR.get('running') else set())
    while (BASE / f'{day}-{slug}').exists() or f'{day}-{slug}' in taken:
        slug, i = f'{base}-{i}', i + 1
    return slug, f'{day}-{slug}'


def style_file(key):
    p = ROOT / 'taste' / 'styles' / f'{key}.json'
    if not key or '/' in key or '\\' in key or not p.exists():
        raise ApiError(400, f'unknown style "{key}"')
    return read_json(p, {})


def text_job(*args):
    """scripts/codex_text.py (Codex writes subjects or a prompt; ~15 s). Raises ApiError with Codex's reason."""
    import subprocess
    cmd = [PY, '-I', str(ROOT / 'scripts' / 'codex_text.py'), *args] + (['--dry-run'] if DRY_RUN else [])
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=320)
    if r.returncode or not r.stdout.strip().startswith('{'):
        raise ApiError(502, (r.stderr or r.stdout).strip().splitlines()[-1][:300] if (r.stderr or r.stdout).strip()
                       else 'Codex gave no answer')
    return json.loads(r.stdout)


def clean(s, n=200):
    return ' '.join(str(s or '').split())[:n]


# -- run records: generated/codex/<batch>/run.json says what a run was, where it came from and how it was set

def run_record(batch):
    return read_json(BASE / batch / 'run.json', None) if is_batch(batch) else None


def lineage():
    """{child batch: {'batch', 'file'}}: where each variations / remix batch came from. run.json says it for
    runs started from the app; older variations batches are matched by their seed's bytes (same size first,
    then the same content), so the image a seed was copied from is found without hashing everything."""
    import hashlib
    names = sorted(p.name for p in BASE.iterdir() if is_batch(p.name)) if BASE.exists() else []
    key = tuple((n, int((BASE / n).stat().st_mtime)) for n in names)
    if _lineage['key'] == key:
        return _lineage['map']
    out, sizes = {}, {}
    for n in names:
        for p in (BASE / n).glob('*.png'):
            if not p.name.startswith('seed.'):
                sizes.setdefault(p.stat().st_size, []).append(p)
    digest = lambda p: hashlib.sha1(p.read_bytes()).hexdigest()  # noqa: E731
    for n in names:
        rec = read_json(BASE / n / 'run.json', None)
        if rec and rec.get('source'):
            out[n] = rec['source']
            continue
        seed = seed_file(n)
        if not seed:
            continue
        sp = BASE / n / seed
        cands = [p for p in sizes.get(sp.stat().st_size, []) if p.parent.name != n]
        if cands:
            d = digest(sp)
            hit = next((p for p in cands if digest(p) == d), None)
            if hit:
                out[n] = {'batch': hit.parent.name, 'file': hit.name}
    _lineage.update(key=key, map=out)
    return out


def kind_of_batch(batch, images, rec):
    if rec and rec.get('kind'):
        return rec['kind']
    return 'variations' if seed_file(batch) else 'batch'   # older folders: no run.json to say more


def failure_reason(batch, name):
    """Why Codex made no image, read from its log (23 Nov 2026): {code: limit | filter | timeout | unknown, stage, about}.
    The filter says at which stage it refused: input (the prompt) or output (the finished image)."""
    import re
    p = BASE / batch / f'{name}.codex.log'
    t = p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''
    if 'usage limit' in t:
        return {'code': 'limit'}
    if 'moderation_blocked' in t or 'safety system' in t:
        stage = re.search(r'moderation_stage\W+(\w+)', t)
        about = re.search(r'safety_violations=\[([^\]]*)\]', t)
        return {'code': 'filter', 'stage': stage.group(1) if stage else '', 'about': about.group(1) if about else ''}
    if 'TIMED OUT' in t:
        return {'code': 'timeout'}
    return {'code': 'unknown'}


def failed_images(batch, have):
    """runs.csv rows of this batch that made no image (blocked, timed out), latest try per name."""
    if not rate.RUNS.exists():
        return []
    rows = {}
    for r in csv.DictReader(open(rate.RUNS, encoding='utf-8')):
        if r['batch'] == batch:
            rows[r['name']] = r
    return [{'name': n, 'style': r['style'], 'change': r['change'], 'mode': r['mode'], 'prompt': r['prompt'],
             'date': r['date'], 'time': r['time'], 'seed': r['seed'], 'reason': failure_reason(batch, n),
             'route': r.get('route') or 'codex'}
            for n, r in sorted(rows.items()) if r['ok'] != 'yes' and n not in have]


def all_blocked():
    """Images Codex's safety filter blocked that FLUX hasn't tried yet, per batch, oldest first (23 Nov 2026):
    the "Try them with FLUX" bar on Batches. Skips the batch being made right now and retries already queued."""
    running = CUR.get('batch') if CUR.get('running') else (chat_run() or {}).get('batch') if (chat_run() or {}).get('running') else None
    queued = {(s['batch'], n) for s in QUEUE for n in s.get('expected', [])}
    out = []
    for p in sorted(BASE.iterdir()) if BASE.exists() else []:
        if not is_batch(p.name) or p.name == running:
            continue
        names = [f['name'] for f in failed_images(p.name, set(rate.batch_images(p.name)))
                 if f['reason'].get('code') == 'filter' and f['route'] == 'codex' and (p.name, f['name']) not in queued]
        if names:
            out.append({'batch': p.name, 'names': names})
    return out


def spec_blocked_flux(batch, names):
    """One run per batch: its filter-blocked images again, same prompts and references, made by FLUX."""
    specs = [spec_retry({'batch': batch, 'name': n}) for n in names]
    jobs = [j for s in specs for j in s['jobs']]
    styles = sorted({st for s in specs for st in s['styles']})
    return {'kind': 'retry', 'title': f'Blocked → FLUX: {batch} ({len(jobs)})', 'batch': batch, 'jobs': jobs,
            'styles': styles, 'n': len(jobs), 'expected': [j['name'] for j in jobs], 'route': 'cloudflare'}


def unmade_images(batch, have):
    """A batch run from the app that stopped early (usage limit, 3 failures in a row, Stop): the images its
    run.json planned that have no PNG, in run order, and why it stopped if Codex's log says (23 Nov 2026)."""
    rec = run_record(batch) or {}
    if rec.get('kind') != 'batch' or not rec.get('styles') or not rec.get('n') or not (BASE / batch / 'subjects.json').is_file():
        return [], ''
    names = [f'{s}-{i + 1}' for s in rec['styles'] for i in range(int(rec['n'])) if f'{s}-{i + 1}' not in have]
    why = ''
    for n in reversed(names):
        log = BASE / batch / f'{n}.codex.log'
        if log.is_file():
            text = log.read_text(encoding='utf-8', errors='replace')
            if 'usage limit' in text:
                why = "Cloudflare's free images for today ran out" if 'Cloudflare' in text else 'Codex hit its usage limit'
            break
    return names, why


def planned_names(rec):
    """Every image a run from the app set out to make, by name, from its run.json."""
    kind, n = rec.get('kind'), int(rec.get('n') or 0)
    if kind == 'batch':
        return [f'{s}-{i + 1}' for s in rec.get('styles') or [] for i in range(n)]
    if kind == 'variations':
        return [f'{i}-{c}' for i, c in enumerate(rec.get('changes') or CHANGES[:n], 1)]
    if kind == 'remix':
        return [f'remix-{i}' for i in range(1, n + 1)]
    if kind == 'single' and rec.get('subject'):
        stem = '-'.join(slugify(rec['subject'], 'image').split('-')[:3])
        return [f'{stem}-{i}' for i in range(1, n + 1)]
    return []


def limit_stopped(batch, have=None):
    """A run that Codex's usage limit cut short (23 Nov 2026): the images it refused for the limit, plus the
    ones the run never reached (it stops after 2 failures). Images blocked by the filter are left out: they
    would only fail again. Names already queued are left out too. run.json's limit_hit keeps the evidence once
    a retry has overwritten the log."""
    rec = run_record(batch) or {}
    have = set(rate.batch_images(batch)) if have is None else have
    queued = {n for s in QUEUE if s['batch'] == batch for n in s.get('expected') or []}
    names = [n for n in planned_names(rec) if n not in have and n not in queued]
    log = lambda n: BASE / batch / f'{n}.codex.log'  # noqa: E731
    hit = {n for n in names if log(n).is_file() and 'usage limit' in log(n).read_text(encoding='utf-8', errors='replace')}
    if not hit and not rec.get('limit_hit'):
        return []
    if rec['kind'] in ('remix', 'single') and not (BASE / batch / '.jobs.json').is_file():
        return []   # nothing to rebuild the prompts from
    return [n for n in names if n in hit or not log(n).is_file()]


def all_limit_stopped():
    """Every batch with images to resume, oldest run first. Skips the batch being made right now."""
    running = CUR.get('batch') if CUR.get('running') else (chat_run() or {}).get('batch') if (chat_run() or {}).get('running') else None
    out = []
    for p in BASE.iterdir() if BASE.exists() else []:
        if not is_batch(p.name) or p.name == running or not (p / 'run.json').is_file():
            continue
        names = limit_stopped(p.name)
        if names:
            rec = run_record(p.name)
            out.append({'batch': p.name, 'title': rec.get('title') or p.name, 'kind': rec.get('kind'),
                        'started': rec.get('started', ''), 'names': names})
    return sorted(out, key=lambda b: (b['started'], b['batch']))


# -- the queue

def save_queue():
    write_json(QUEUE_FILE, QUEUE)


def public(spec):
    keys = ('id', 'kind', 'title', 'batch', 'expected', 'created', 'source', 'styles', 'n')
    return {k: spec.get(k) for k in keys}


def enqueue(spec):
    import time
    spec.update(id=f'{int(time.time() * 1000)}', created=time.time())
    with _QLOCK:
        QUEUE.append(spec)
        save_queue()
        pos = len(QUEUE) + (1 if CUR.get('running') or (not DRY_RUN and (chat_run() or {}).get('running')) else 0)
    _WAKE.set()
    return {**job_state(), 'queued_id': spec['id'], 'position': pos}


# The queue holds instead of failing every run in turn (23 Nov 2026): a script that doesn't compile (a session
# mid-edit) made ten queued runs fail in a second each, one error toast per run. Two holds:
# - auto: some scripts/*.py doesn't compile. Checked before each run; lifts by itself once it compiles again.
# - after a run that made nothing and failed on a Python error (one that compiling can't catch): lifts when
#   Marc presses Continue (POST /api/queue/resume) or the app restarts (it does when scripts/ change).
_COMPILED = {}            # path -> (mtime, error or '')
SCRIPT_ERROR = re.compile(r'\b(SyntaxError|IndentationError|NameError|ImportError|ModuleNotFoundError|AttributeError|TypeError)\b')


def broken_scripts():
    """'name.py line N: message' for the first script in scripts/ that doesn't compile, else ''."""
    for p in sorted((ROOT / 'scripts').glob('*.py')):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if _COMPILED.get(p, (None,))[0] != m:
            try:
                compile(p.read_bytes(), str(p), 'exec')
                err = ''
            except SyntaxError as e:
                err = f'{p.name} line {e.lineno}: {e.msg}'
            except Exception as e:  # noqa: BLE001  (unreadable mid-write: try again next tick)
                err = f'{p.name}: {e}'
            _COMPILED[p] = (m, err)
        if _COMPILED[p][1]:
            return _COMPILED[p][1]
    return ''


def check_failed_run():
    """After a run ends (CUR): nothing made and its log shows a Python error -> hold the queue."""
    import time
    if CUR.get('stopped') or CUR.get('dry_run') or not CUR.get('batch'):
        return
    folder = BASE / CUR['batch']
    if any((folder / f'{n}.png').exists() for n in CUR.get('expected') or []):
        return
    hit = next((line for line in reversed(CUR.get('log') or []) if SCRIPT_ERROR.search(line)), '')
    if hit:
        HOLD.update(reason=hit.split('FAILED', 1)[-1].strip(' :')[-160:], since=time.time(), auto=False)


def worker():
    """Starts the next queued run when nothing is running (neither from the app nor from chat)."""
    import time
    while True:
        _WAKE.wait(3)
        _WAKE.clear()
        with _QLOCK:
            if not QUEUE:
                HOLD.clear()          # a hold is about the runs waiting: none left, none to hold
            # a dry run spends nothing and writes no progress file: it never waits for a real run
            if RESTARTING.is_set() or CUR.get('running') or not QUEUE or (not DRY_RUN and (chat_run() or {}).get('running')):
                continue
            broken = broken_scripts()
            if broken:
                if not HOLD:
                    HOLD.update(reason=broken, since=time.time(), auto=True)
                elif HOLD.get('auto'):
                    HOLD['reason'] = broken
                continue
            if HOLD.get('auto'):
                HOLD.clear()          # fixed: go on by itself
            if HOLD:
                continue
            spec = QUEUE.pop(0)
            save_queue()
            CUR.clear()
            CUR.update(spec, running=True, phase='Starting', started=time.time(), finished=None, returncode=None,
                       log=[], stopped=False, cancel=False, dry_run=DRY_RUN, error=None)
        try:
            launch(spec)
        except Exception as e:  # report it on the page; the queue goes on
            CUR['log'].append(f'ERROR: {e}')
            CUR.update(running=False, finished=time.time(), returncode=-1, error=str(e), phase='')
        with _QLOCK:
            remember_finished()
            if QUEUE:
                check_failed_run()
        _WAKE.set()


def launch(spec):
    import shutil, subprocess, time
    if spec['kind'] == 'variations' and not DRY_RUN:   # variations.py names its folder by today's date
        end = '-flux' if spec.get('route') == 'cloudflare' else ''
        spec['slug'], spec['batch'] = free_slug(spec['slug'].removesuffix(end) if end else spec['slug'], end)
        CUR['batch'] = spec['batch']
    folder = SPECS / spec['id'] if DRY_RUN else BASE / spec['batch']
    folder.mkdir(parents=True, exist_ok=True)
    say = lambda line: CUR.__setitem__('log', CUR['log'] + [f'{time.strftime("%H:%M:%S")}  {line}'])  # noqa: E731
    if spec['kind'] == 'batch':
        subjects = {}
        for st in spec['styles']:
            have = [s for s in spec['subjects'].get(st, []) if s.strip()][:spec['n']]
            if len(have) < spec['n']:
                CUR['phase'] = f'Codex is writing subjects for {style_file(st).get("name", st)}'
                say(CUR['phase'])
                have += text_job('subjects', '--style', st, '--n', str(spec['n'] - len(have)),
                                 '--hint', spec['hints'].get(st, ''), *(['--wild'] if spec.get('experimental') else []))['subjects']
            if CUR.get('cancel'):
                raise RuntimeError('stopped before the first image')
            subjects[st] = have
            for s in have:
                say(f'subject {st}: {s}')
        spec['subjects'] = CUR['subjects'] = subjects
        write_json(folder / 'subjects.json', subjects)
        if spec.get('use_kept'):
            spec['kept_refs'] = {st: kept_paths(st) for st in spec['styles'] if kept_paths(st)}
            if spec['kept_refs']:
                write_json(folder / '.kept-refs.json', spec['kept_refs'])
                say('kept examples go along: ' + ', '.join(f'{st} ({len(v)})' for st, v in spec['kept_refs'].items()))
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'batch.py'), '--out', str(folder), '--subjects', str(folder / 'subjects.json'),
               '--styles', ','.join(spec['styles']), '--n', str(spec['n']), '--wildcards', str(spec['wildcards']),
               '--ratio', spec['ratio']]
        if spec.get('kept_refs'):
            cmd += ['--kept-refs', str(folder / '.kept-refs.json')]
        if spec.get('experimental'):
            cmd.append('--experimental')
    elif spec['kind'] == 'finish':   # same subjects, seed (the folder name) and kept examples as the first run
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'batch.py'), '--out', str(folder), '--subjects', str(folder / 'subjects.json'),
               '--styles', ','.join(spec['all_styles']), '--n', str(spec['n']), '--wildcards', str(spec['wildcards']),
               '--ratio', spec['ratio'], '--only', ','.join(spec['expected'])]
        if (folder / '.kept-refs.json').is_file():
            cmd += ['--kept-refs', str(folder / '.kept-refs.json')]
        if spec.get('experimental'):
            cmd.append('--experimental')
    elif spec['kind'] == 'resume' and not spec.get('jobs'):   # variations cut short: same seed, folder and numbers
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'variations.py'), str(BASE / spec['batch'] / seed_file(spec['batch'])),
               '--style', spec['style'], '--changes', ','.join(spec['changes']), '--out', str(folder),
               '--only', ','.join(spec['expected'])]
        if spec.get('subject'):
            cmd += ['--subject', spec['subject']]
        if spec.get('note'):
            cmd += ['--note', spec['note']]
    elif spec['kind'] in ('remix', 'single', 'retry', 'resume'):
        if spec['kind'] == 'single' and spec.get('use_kept'):
            paths = kept_paths(spec['styles'][0])
            if paths:
                spec['kept_refs'] = {spec['styles'][0]: paths}
                for i, j in enumerate(spec['jobs']):
                    j['ref'], j['kept'] = pick_refs(paths, i), True
                say(f'kept examples go along ({len(paths)} kept)')
        write_json(folder / '.jobs.json', spec['jobs'])
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'run_list.py'), '--out', str(folder), '--jobs', str(folder / '.jobs.json')]
    else:  # variations
        src = BASE / spec['source']['batch'] / spec['source']['file']
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'variations.py'), str(src), '--style', spec['style'],
               '--changes', ','.join(spec['changes']), '--slug', spec['slug']]
        if spec.get('subject'):
            cmd += ['--subject', spec['subject']]
        if spec.get('note'):
            cmd += ['--note', spec['note']]
    if DRY_RUN:
        cmd.append('--dry-run')
    elif spec['kind'] in ('finish', 'retry', 'resume') and run_record(spec['batch']):
        # keep the first run's record ("How it was made"); a retry used to overwrite it (fixed 23 Nov 2026)
        if spec['kind'] == 'finish':
            rec = run_record(spec['batch'])
            rec.setdefault('finished_later', []).append(time.strftime('%Y-%m-%d %H:%M'))
            write_json(folder / 'run.json', rec)
    else:
        rec = {k: spec.get(k) for k in ('kind', 'title', 'source', 'styles', 'n', 'subjects', 'hints', 'ratio',
                                         'wildcards', 'experimental', 'style', 'changes', 'subject', 'note', 'change', 'keep', 'kept_refs', 'route')
               if spec.get(k) not in (None, '', [], {})}
        rec.update(started=time.strftime('%Y-%m-%d %H:%M'), by='web app')
        write_json(folder / 'run.json', rec)
    if CUR.get('cancel'):
        raise RuntimeError('stopped before the first image')
    CUR['phase'] = ('Making images' + (' with FLUX' if spec.get('route') == 'cloudflare' else '')) if not DRY_RUN else 'Dry run: printing the prompts'
    # the route reaches codex_run.py gen through batch.py / run_list.py / variations.py, which pass the environment on
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace',
                            env={**os.environ, 'TASTE_ROUTE': spec.get('route') or 'codex'})
    PROC['p'] = proc
    for line in proc.stdout:
        CUR['log'] = (CUR['log'] + [line.rstrip()])[-200:]
    CUR.update(running=False, returncode=proc.wait(), finished=time.time(), phase='')
    PROC.clear()
    if not DRY_RUN and run_record(spec['batch']):   # remember the usage limit: a later retry overwrites the log
        logs = [folder / f'{n}.codex.log' for n in spec['expected']]
        if any(p.is_file() and 'usage limit' in p.read_text(encoding='utf-8', errors='replace') for p in logs):
            rec = run_record(spec['batch'])
            rec['limit_hit'] = time.strftime('%Y-%m-%d %H:%M')
            write_json(folder / 'run.json', rec)
    if DRY_RUN:
        shutil.rmtree(folder, ignore_errors=True)
    elif spec['kind'] in ('batch', 'finish'):
        subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'sheet.py'), str(folder)], cwd=ROOT, capture_output=True)


def remember_finished():
    """Keep a short record of the run that just ended (CUR), for GET /api/job."""
    folder = BASE / CUR['batch']
    rec = {**public(CUR), **{k: CUR.get(k) for k in ('started', 'finished', 'stopped', 'dry_run', 'error', 'returncode')},
           'made': [] if CUR.get('dry_run') else [n for n in CUR['expected'] if (folder / f'{n}.png').exists()],
           'exists': is_batch(CUR['batch']), 'log': CUR['log'][-80:]}
    RECENT.append(rec)
    del RECENT[:-5]


def stop_current():
    """Stop the running run: the app's own, or one started from chat (its pid is in .progress.json).
    Ends the whole process tree, so the codex exec of the current image stops too."""
    import subprocess
    pid = None
    if CUR.get('running'):
        CUR['cancel'] = True
        CUR['stopped'] = True
        pid = PROC['p'].pid if PROC.get('p') else None
        if pid is None:
            return  # still writing subjects: launch() sees cancel before the first image
    else:
        run = chat_run()
        if not (run and run.get('running') and run.get('pid')):
            raise ApiError(409, 'nothing is running')
        pid = run['pid']
    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
    # The killed run can't write its last line: do it for it, so the next queued run starts at once.
    import time
    with LOCK:
        d = read_json(BASE / '.progress.json', None)
        if isinstance(d, dict) and d.get('pid') == pid and d.get('finished') is None:
            d.update(finished=time.time(), current=None, log=(d.get('log') or []) + [f'{time.strftime("%H:%M:%S")}  STOPPED from the web app'])
            write_json(BASE / '.progress.json', d)


def chat_run():
    """A run's live progress: scripts/progress.py writes generated/codex/.progress.json as it goes (batch.py,
    variations.py, run_list.py, a lone codex_run.py). No heartbeat for 45 s = the run was stopped."""
    import time
    try:
        d = read_json(BASE / '.progress.json', None)
    except OSError:  # being replaced right now: next poll
        return None
    if not isinstance(d, dict) or not d.get('batch') or not isinstance(d.get('expected'), list):
        return None
    alive = d.get('finished') is None and time.time() - d.get('updated', 0) < 45
    return {**d, 'running': alive, 'finished': d.get('finished') or (None if alive else d.get('updated')),
            'stopped': not alive and d.get('finished') is None, 'from_chat': True, 'dry_run': False}


def job_state():
    """What is running (or ran last), what is queued. The app's own run wins over the progress file unless
    a run from chat started after it."""
    with _QLOCK:
        cur = {k: v for k, v in CUR.items()}
        queue = [public(s) for s in QUEUE]
        hold = dict(HOLD) if HOLD and QUEUE else None
    return {**_job_state(cur, queue), 'hold': hold}


def _job_state(cur, queue):
    prog = chat_run()
    # a live run from chat, or one that started after the app's run ended, takes over once the app's run is done
    if cur and (cur['running'] or not (prog and (prog['running'] or prog['started'] > (cur['finished'] or 0)))):
        run = {**public(cur), **{k: cur.get(k) for k in ('running', 'phase', 'started', 'finished', 'returncode',
                                                         'stopped', 'dry_run', 'error', 'log', 'subjects')},
               'failed': [], 'current': None, 'from_chat': False}
        if prog and prog['batch'] == cur['batch'] and prog['started'] >= cur['started'] - 1:
            run.update(expected=prog['expected'], failed=prog['failed'], current=prog['current'],
                       log=[line for line in cur['log'] if 'subject' in line or 'Codex' in line] + prog['log'])
            if not cur['running'] and prog['running']:  # the process tree is gone; the file just hasn't caught up
                run['current'] = None
    elif prog:
        run = {**prog, 'title': prog.get('kind', 'run'), 'phase': 'Making images' if prog['running'] else ''}
    else:
        return {'running': False, 'queue': queue, 'recent': list(RECENT), 'suggest': suggestions()}
    folder = BASE / run['batch']
    made = [n for n in run['expected'] if (folder / f'{n}.png').exists()]
    return {**run, 'exists': is_batch(run['batch']), 'made': made, 'queue': queue, 'recent': list(RECENT),
            'suggest': suggestions()}


# -- run specs: what each kind of run needs, checked before it joins the queue

KEEPABLE = ('subject', 'palette', 'composition', 'light', 'medium')


def spec_batch(body, preview=False):
    """{styles: [..], n: 1-24, subjects: {style: [..]}, hints: {style: '..'}, ratio, wildcards: 0|1, name}"""
    styles = list(dict.fromkeys(s for s in body.get('styles') or [] if isinstance(s, str)))
    if not styles:
        raise ApiError(400, 'pick at least one style')
    info = {s: style_file(s) for s in styles}
    n = int(body.get('n') or 4)
    if not 1 <= n <= 24:
        raise ApiError(400, 'images per style: 1 to 24')
    ratio = body.get('ratio') or 'mixed'
    if ratio not in RATIO_CHOICES:
        raise ApiError(400, 'ratio: mixed, wide, portrait or square')
    experimental = bool(body.get('experimental'))
    wildcards = 1 if body.get('wildcards') and n > 1 and not experimental else 0
    subjects = {s: [clean(x) for x in (body.get('subjects') or {}).get(s, []) if clean(x)][:n] for s in styles}
    hints = {s: clean((body.get('hints') or {}).get(s), 200) for s in styles}
    placeholders = set()
    if preview:   # never call Codex for a preview: fill with the style's own example subjects
        for s in styles:
            pool = info[s].get('subjects') or ['a scene that suits the style']
            for i in range(len(subjects[s]), n):
                subjects[s].append(pool[i % len(pool)])
                placeholders.add(f'{s}-{i + 1}')
    names = [info[s].get('name', s) for s in styles]
    title = clean(body.get('name'), 60) or (', '.join(names[:3]) + (f' +{len(names) - 3}' if len(names) > 3 else ''))
    if experimental and not clean(body.get('name'), 60):
        title = 'Experimental: ' + title
    _, batch = free_slug(clean(body.get('name'), 60) or ('exp-' if experimental else '') + '-'.join(styles[:2]), flux_end(body))
    return {'kind': 'batch', 'title': title, 'batch': batch, 'styles': styles, 'n': n, 'ratio': ratio,
            'use_kept': bool(body.get('use_kept')), 'wildcards': wildcards, 'experimental': experimental, 'subjects': subjects, 'hints': hints, 'placeholders': placeholders,
            'expected': [f'{s}-{i + 1}' for s in styles for i in range(n)]}


def spec_single(body):
    """One image (or a few) from a style and a subject I write: {style, subject, ratio, n: 1-10}."""
    style = str(body.get('style', ''))
    st = style_file(style)
    subject = clean(body.get('subject'))
    if not subject:
        raise ApiError(400, 'write a subject')
    ratio = body.get('ratio') or 'wide'
    if ratio not in RATIO_CHOICES[1:]:
        raise ApiError(400, 'ratio: wide, portrait or square')
    n = max(1, min(10, int(body.get('n') or 1)))
    _, batch = free_slug(subject[:24], flux_end(body))
    stem = '-'.join(slugify(subject, 'image').split('-')[:3])   # first words, never cut mid-word
    jobs = [{'name': f'{stem}-{i}', 'style': style, 'subject': subject, 'ratio': ratio, 'mode': 'text'}
            for i in range(1, n + 1)]
    return {'kind': 'single', 'title': f'{st.get("name", style)}: {subject[:50]}', 'batch': batch, 'jobs': jobs,
            'styles': [style], 'n': n, 'subject': subject, 'ratio': ratio, 'use_kept': bool(body.get('use_kept')),
            'expected': [j['name'] for j in jobs]}


def spec_remix(body):
    """A new image from one I made, with a rewritten prompt: {batch, file, prompt, change, keep, ref: bool, n: 1-4}."""
    src = source_image(str(body.get('batch', '')), str(body.get('file', '')))
    prompt = clean(body.get('prompt'), 4000)
    if not prompt:
        raise ApiError(400, 'the prompt is empty')
    change = clean(body.get('change'), 200)
    n = max(1, min(4, int(body.get('n') or 1)))
    style = rate.batch_runs(src.parent.name).get(src.stem, {}).get('style', '')
    _, batch = free_slug(f'{src.stem}-remix', flux_end(body))
    jobs = [{'name': f'remix-{i}', 'prompt': prompt, 'style': style, 'mode': 'remix',
             'change': f'remix: {change}' if change else 'remix: prompt edited',
             'ref': str(src) if body.get('ref') else ''} for i in range(1, n + 1)]
    return {'kind': 'remix', 'title': f'Remix of {src.stem}' + (f': {change[:40]}' if change else ''), 'batch': batch,
            'jobs': jobs, 'source': {'batch': src.parent.name, 'file': src.name}, 'change': change,
            'keep': [k for k in body.get('keep') or [] if k in KEEPABLE], 'styles': [style] if style else [], 'n': n,
            'expected': [j['name'] for j in jobs]}


def spec_retry(body):
    """Try a failed image again, same prompt, same batch and name: {batch, name}."""
    batch, name = str(body.get('batch', '')), str(body.get('name', ''))
    if not is_batch(batch):
        raise ApiError(404, f'no batch "{batch}"')
    row = next((f for f in failed_images(batch, set(rate.batch_images(batch))) if f['name'] == name), None)
    if not row:
        raise ApiError(404, f'"{name}" did not fail in this batch (or it has an image now)')
    if any(s['batch'] == batch and name in s['expected'] for s in QUEUE):
        raise ApiError(409, 'this retry is already in the queue')
    ref = ''
    kept = row['seed'].startswith('kept ')
    if kept:   # it had kept examples: the same ones this batch was started with (run.json), if they still exist
        paths = [p for p in (run_record(batch) or {}).get('kept_refs', {}).get(row['style'], []) if Path(p).is_file()]
        ref = pick_refs(paths, int(name.rsplit('-', 1)[-1] or 1) - 1) if paths and name.rsplit('-', 1)[-1].isdigit() else ''
    elif row['seed']:   # it had a reference image: the batch's seed copy, else the source named in run.json
        if seed_file(batch):
            ref = str(BASE / batch / seed_file(batch))
        elif (run_record(batch) or {}).get('source'):
            src = run_record(batch)['source']
            if (BASE / src['batch'] / src['file']).is_file():
                ref = str(BASE / src['batch'] / src['file'])
    job = {'name': name, 'prompt': row['prompt'], 'style': row['style'], 'mode': row['mode'] or 'test',
           'change': row['change'], 'ref': ref, 'kept': bool(kept and ref)}
    return {'kind': 'retry', 'title': f'Retry {name}', 'batch': batch, 'jobs': [job],
            'styles': [row['style']] if row['style'] else [], 'n': 1, 'expected': [name]}


def spec_finish(body):
    """Make the images a stopped batch never made, with its own subjects, seed and kept examples: {batch}."""
    batch = str(body.get('batch', ''))
    if not is_batch(batch):
        raise ApiError(404, f'no batch "{batch}"')
    names, _ = unmade_images(batch, set(rate.batch_images(batch)))
    if not names:
        raise ApiError(409, 'every image of this batch is made')
    if any(s['batch'] == batch for s in QUEUE) or (CUR.get('running') and CUR.get('batch') == batch):
        raise ApiError(409, 'a run for this batch is already running or queued')
    rec = run_record(batch)
    styles = [s for s in rec['styles'] if any(n.startswith(s + '-') and n[len(s) + 1:].isdigit() for n in names)]
    return {'kind': 'finish', 'title': f'Finish {rec.get("title") or batch}', 'batch': batch, 'styles': styles,
            'n': int(rec['n']), 'all_styles': rec['styles'], 'ratio': rec.get('ratio') or 'mixed',
            'wildcards': int(rec.get('wildcards') or 0), 'experimental': bool(rec.get('experimental')), 'expected': names}


def spec_resume(body):
    """Make what Codex's usage limit cut short in one run, in its own folder, as the first run set it: {batch}."""
    batch = str(body.get('batch', ''))
    if not is_batch(batch):
        raise ApiError(404, f'no batch "{batch}"')
    if CUR.get('running') and CUR.get('batch') == batch:
        raise ApiError(409, 'a run for this batch is running')
    names = limit_stopped(batch)
    if not names:
        raise ApiError(409, 'nothing in this batch waits to be made again')
    rec = run_record(batch)
    title = f'Resume {rec.get("title") or batch}'
    if rec['kind'] == 'batch':
        styles = [s for s in rec['styles'] if any(n.startswith(s + '-') and n[len(s) + 1:].isdigit() for n in names)]
        return {'kind': 'finish', 'title': title, 'batch': batch, 'styles': styles, 'n': int(rec['n']),
                'all_styles': rec['styles'], 'ratio': rec.get('ratio') or 'mixed',
                'wildcards': int(rec.get('wildcards') or 0), 'experimental': bool(rec.get('experimental')), 'expected': names}
    if rec['kind'] == 'variations':
        if not seed_file(batch):
            raise ApiError(409, 'this batch has no seed to vary')
        return {'kind': 'resume', 'title': title, 'batch': batch, 'style': rec.get('style', ''), 'styles': rec.get('styles') or [],
                'changes': rec.get('changes') or CHANGES[:int(rec.get('n') or 3)], 'subject': rec.get('subject', ''),
                'note': rec.get('note', ''), 'n': len(names), 'expected': names}
    # remix / single: every job of the run shares its prompt (or style, subject, ratio): copy one, rename it
    template = read_json(BASE / batch / '.jobs.json', [])[0]
    jobs = []
    for nm in names:
        j = {**template, 'name': nm}
        if j.get('kept'):
            paths = [p for p in (rec.get('kept_refs') or {}).get(j.get('style'), []) if Path(p).is_file()]
            j['ref'] = pick_refs(paths, int(nm.rsplit('-', 1)[-1]) - 1) if paths else ''
            j['kept'] = bool(j['ref'])
        jobs.append(j)
    return {'kind': 'resume', 'title': title, 'batch': batch, 'jobs': jobs, 'styles': rec.get('styles') or [],
            'n': len(jobs), 'expected': names}


def spec_variations(body):
    src = source_image(str(body.get('batch', '')), str(body.get('file', '')))
    style = str(body.get('style', ''))
    style_file(style)
    changes = [c for c in body.get('changes') or [] if c in CHANGES]
    if not changes:
        n = body.get('n', 3)
        if n not in (3, 4):
            raise ApiError(400, 'pick what changes')
        changes = CHANGES[:n]
    changes = [c for c in CHANGES if c in changes]   # the order variations.py makes them in
    stem = src.stem if src.stem != 'seed' else src.parent.name[11:] + '-seed'
    slug, batch = free_slug(stem, flux_end(body))
    return {'kind': 'variations', 'title': f'Variations of {src.stem}', 'batch': batch, 'slug': slug,
            'source': {'batch': src.parent.name, 'file': src.name}, 'style': style, 'styles': [style],
            'changes': changes, 'subject': clean(body.get('subject')), 'note': clean(body.get('note')),
            'n': len(changes), 'expected': [f'{i}-{c}' for i, c in enumerate(changes, 1)]}


# -- style edits from the page (21 Nov 2026): Marc writes what should change, Codex proposes (read-only), Marc
# approves in the page, this server applies it, rebuilds taste.json, and keeps the before / after for Undo.

STYLE_EDITS = BASE / 'style-edits.json'   # [{id, style, at, change, summary, before, after, source, undone}]
EDITABLE = ('description', 'light', 'composition', 'camera_or_medium', 'mood', 'texture_detail', 'prefer', 'avoid',
            'subjects')
FIELD_NAMES = {'description': 'Description', 'light': 'Light', 'composition': 'Composition', 'camera_or_medium': 'Medium',
               'mood': 'Mood', 'texture_detail': 'Detail', 'prefer': 'Lean towards', 'avoid': 'Avoid', 'subjects': 'Subjects'}


def check_changes(style, changes):
    """Only known fields, same type as now (a list stays a list of short phrases), something really different."""
    now = style_file(style)
    if not isinstance(changes, dict) or not changes:
        raise ApiError(400, 'nothing to change')
    out = {}
    for k, v in changes.items():
        if k not in EDITABLE:
            raise ApiError(400, f'"{k}" cannot be edited here')
        if isinstance(v, list):
            v = [clean(x, 300) for x in v if clean(x, 300)]
            if k in now and isinstance(now[k], str) and k != 'texture_detail':
                raise ApiError(400, f'"{k}" must stay one text')
        elif isinstance(v, str):
            v = clean(v, 1200)
            if k in now and isinstance(now[k], list):
                raise ApiError(400, f'"{k}" must stay a list')
        else:
            raise ApiError(400, f'"{k}": text or a list of texts')
        if k in ('description', 'light', 'composition', 'camera_or_medium', 'mood', 'texture_detail') and not v:
            raise ApiError(400, f'"{FIELD_NAMES[k]}" cannot be empty')
        if v != now.get(k):
            out[k] = v
    if not out:
        raise ApiError(400, 'that is how the style already reads')
    return now, out


def write_style(style, data):
    """Same format as the files in the repo (2 spaces, ASCII escapes, Windows line ends), then rebuild taste.json."""
    import subprocess
    path = ROOT / 'taste' / 'styles' / f'{style}.json'
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\r\n') as fh:
        fh.write(json.dumps(data, indent=2))
    os.replace(tmp, path)
    r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'build_taste.py'), str(ROOT)], cwd=ROOT,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        raise ApiError(500, 'build_taste.py failed: ' + (r.stderr or r.stdout).strip()[-300:])


def apply_style_edit(style, changes, change_text, summary, source, how):
    import time
    with LOCK:
        now, changes = check_changes(style, changes)
        before = {k: now.get(k) for k in changes}
        write_style(style, {**now, **changes})
        edits = read_json(STYLE_EDITS, [])
        rec = {'id': f'{int(time.time() * 1000)}', 'style': style, 'at': time.strftime('%Y-%m-%d %H:%M'),
               'change': clean(change_text, 400), 'summary': clean(summary, 200), 'how': how,
               'before': before, 'after': changes, 'source': source, 'undone': False}
        edits.append(rec)
        write_json(STYLE_EDITS, edits)
    return rec


def undo_style_edit(eid):
    with LOCK:
        edits = read_json(STYLE_EDITS, [])
        rec = next((e for e in edits if e['id'] == eid), None)
        if not rec or rec['undone']:
            raise ApiError(404, 'no such edit, or it is undone already')
        if rec.get('how') in ('new', 'fork'):
            undo_new_style(rec, edits)
            rec['undone'] = True
            write_json(STYLE_EDITS, edits)
            return rec
        now = style_file(rec['style'])
        moved = [k for k, v in rec['after'].items() if now.get(k) != v]
        if moved:
            raise ApiError(409, 'changed again since (' + ', '.join(FIELD_NAMES.get(k, k) for k in moved)
                           + '): undo the later edit first')
        restored = {**now}
        for k, v in rec['before'].items():
            if v is None:
                restored.pop(k, None)   # the field did not exist before (e.g. a first "lean towards")
            else:
                restored[k] = v
        write_style(rec['style'], restored)
        rec['undone'] = True
        write_json(STYLE_EDITS, edits)
    return rec


# -- a new style from reference images (21 Nov 2026): Marc drops 1-4 images, Codex looks at them and writes the
# words, the palette is measured from the pixels; Marc reads and edits the proposal in the page, "Create style"
# writes taste/styles/<key>.json. The images stay in generated/codex/references/ (git-ignored).

REFS = BASE / 'references'
REMOVED = BASE / 'removed-styles'
MAX_REFS = 4


def save_refs(images):
    """Data URLs from the page -> generated/codex/references/.drafts/<id>/ref-N.jpg. Each one is opened and saved
    again with Pillow (max 1280 px), so only real pictures land on disk."""
    import base64, io, time
    from PIL import Image
    if not isinstance(images, list) or not images:
        raise ApiError(400, 'add at least one image')
    if len(images) > MAX_REFS:
        raise ApiError(400, f'{MAX_REFS} images at most')
    decoded = []
    for i, url in enumerate(images, 1):
        head, _, data = str(url).partition(',')
        if not head.startswith('data:image/') or ';base64' not in head:
            raise ApiError(400, 'images only')
        try:
            im = Image.open(io.BytesIO(base64.b64decode(data, validate=True))).convert('RGB')
        except Exception:
            raise ApiError(400, f'image {i} could not be read')
        im.thumbnail((1280, 1280))
        decoded.append(im)
    import shutil
    for old in (REFS / '.drafts').glob('*') if (REFS / '.drafts').is_dir() else []:
        if old.is_dir() and time.time() - old.stat().st_mtime > 86400:   # proposals never created: copies made here
            shutil.rmtree(old, ignore_errors=True)
    draft = f'{int(time.time() * 1000)}'
    folder = REFS / '.drafts' / draft
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, im in enumerate(decoded, 1):
        path = folder / f'ref-{i}.jpg'
        im.save(path, 'JPEG', quality=88)
        paths.append(path)
    return draft, paths


def measured_palette(paths):
    """5 base colours + up to 2 accents from the pixels (scripts/features.py, the recipe the first styles used)."""
    try:
        import features
        return features.palette([features.thumb64(p)[0] for p in paths])
    except Exception:
        return []   # no numpy / scikit-learn: Codex's own palette stays


def draft_folder(draft):
    folder = REFS / '.drafts' / str(draft)
    if not str(draft).isdigit() or not folder.is_dir():
        raise ApiError(404, 'the reference images are gone: start again')
    return folder


def check_new_style(st):
    """A whole style as the page sends it after Marc's edits: the fields build_taste.py needs, typed right."""
    import re
    if not isinstance(st, dict):
        raise ApiError(400, 'no style')
    out = {'name': clean(st.get('name'), 80)}
    if not out['name']:
        raise ApiError(400, 'give the style a name')
    for k in ('description', 'camera_or_medium', 'texture_detail'):
        out[k] = clean(st.get(k), 1200)
    pal = [str(c).lower() for c in st.get('palette') or [] if re.fullmatch(r'#[0-9a-fA-F]{6}', str(c))][:7]
    if len(pal) < 3:
        raise ApiError(400, 'the palette needs at least 3 colours')
    out['palette'] = pal
    for k in ('light', 'composition', 'mood', 'avoid', 'prefer', 'subjects'):
        v = st.get(k) or []
        out[k] = [clean(x, 300) for x in (v if isinstance(v, list) else [v]) if clean(x, 300)][:8]
    for k in ('description', 'light', 'composition', 'camera_or_medium', 'mood', 'texture_detail', 'avoid'):
        if not out[k]:
            raise ApiError(400, f'"{FIELD_NAMES[k]}" cannot be empty')
    for k in ('prefer', 'subjects'):
        if not out[k]:
            del out[k]
    out['use'] = [u for u in st.get('use') or [] if u in ('desktop', 'teams', 'phone', 'post')] or ['desktop']
    return out


def create_style(draft, st, notes, summary):
    import time
    folder = draft_folder(draft)
    st = check_new_style(st)
    key = slugify(st['name'], '')
    if not key:
        raise ApiError(400, 'the name needs letters or numbers')
    with LOCK:
        if (ROOT / 'taste' / 'styles' / f'{key}.json').exists():
            raise ApiError(409, f'a style called "{st["name"]}" exists already: choose another name')
        order = ('name', 'description', 'palette', 'light', 'composition', 'camera_or_medium', 'mood',
                 'texture_detail', 'prefer', 'avoid', 'subjects', 'use')
        write_style(key, {k: st[k] for k in order if k in st})
        dest = REFS / key
        if dest.exists():   # should not happen (Undo moves them out): set the old ones aside
            REMOVED.mkdir(parents=True, exist_ok=True)
            os.replace(dest, REMOVED / f'{key}-refs-{draft}')
        os.replace(folder, dest)
        n = len(list(dest.glob('ref-*.jpg')))
        edits = read_json(STYLE_EDITS, [])
        rec = {'id': f'{int(time.time() * 1000)}', 'style': key, 'at': time.strftime('%Y-%m-%d %H:%M'),
               'change': clean(notes, 400) or f'New style from {n} reference image{"s" if n != 1 else ""}',
               'summary': clean(summary, 300), 'how': 'new', 'before': {}, 'after': st,
               'source': {'refs': dest.name}, 'undone': False}
        edits.append(rec)
        write_json(STYLE_EDITS, edits)
    return rec


def undo_new_style(rec, edits):
    """Undo of a creation: the style file moves to generated/codex/removed-styles/ (never deleted), taste.json is
    rebuilt. Only while no later edit of the style is still in place."""
    import subprocess
    later = [e for e in edits if e['style'] == rec['style'] and int(e['id']) > int(rec['id']) and not e['undone']]
    if later:
        raise ApiError(409, 'the style was changed since: undo those edits first')
    path = ROOT / 'taste' / 'styles' / f'{rec["style"]}.json'
    REMOVED.mkdir(parents=True, exist_ok=True)
    if path.exists():
        os.replace(path, REMOVED / f'{rec["style"]}-{rec["id"]}.json')
    refs = REFS / rec['style']
    if refs.is_dir():   # its references go along, so a later style of the same name starts clean
        os.replace(refs, REMOVED / f'{rec["style"]}-{rec["id"]}-refs')
    r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'build_taste.py'), str(ROOT)], cwd=ROOT,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        raise ApiError(500, 'build_taste.py failed: ' + (r.stderr or r.stdout).strip()[-300:])


def check_fork_style(parent, st):
    """A fork as the page sends it after Marc's edits: the parent's file shape (same keys, same types, palette ==
    palettes[0] when the parent has palettes), never check_new_style, which would drop palettes / use."""
    import re
    if not isinstance(st, dict):
        raise ApiError(400, 'no style')
    hexes = lambda v: [str(c).lower() for c in (v if isinstance(v, list) else []) if re.fullmatch(r'#[0-9a-fA-F]{6}', str(c))][:7]  # noqa: E731
    out = {}
    for k, v in parent.items():
        n = st.get(k)
        if k == 'name':
            out[k] = clean(n, 80)
            if not out[k]:
                raise ApiError(400, 'give the fork a name')
        elif k == 'palette':
            out[k] = hexes(n)
            if len(out[k]) < 3:
                raise ApiError(400, 'the palette needs at least 3 colours')
        elif k == 'palettes':
            out[k] = [p for p in (hexes(x) for x in (n if isinstance(n, list) else [])) if len(p) >= 3] or v
        elif k == 'use':
            out[k] = [u for u in (n if isinstance(n, list) else []) if u in ('desktop', 'teams', 'phone', 'post')] or v
        elif isinstance(v, list):
            out[k] = [clean(x, 300) for x in (n if isinstance(n, list) else [n]) if clean(x, 300)][:8]
            if not out[k] and v:
                raise ApiError(400, f'"{FIELD_NAMES.get(k, k)}" cannot be empty')
        elif isinstance(v, str):
            out[k] = clean(n, 1200)
            if not out[k] and v:
                raise ApiError(400, f'"{FIELD_NAMES.get(k, k)}" cannot be empty')
        else:
            out[k] = v
    if out.get('palettes') and out['palettes'][0] != out['palette']:
        out['palettes'] = [out['palette']] + out['palettes'][1:]
    return out


def create_fork(parent_key, st, change, summary):
    """A new style from an existing one: the parent file's shape, the checked fields, no images or ratings.
    Lineage lives in the style-edits log (how: fork, source.from), not in the style file."""
    import time
    parent = style_file(parent_key)
    st = check_fork_style(parent, st)
    key = slugify(st['name'], '')
    if not key:
        raise ApiError(400, 'the name needs letters or numbers')
    with LOCK:
        if (ROOT / 'taste' / 'styles' / f'{key}.json').exists() or (ARCHIVED / f'{key}.json').exists():
            raise ApiError(409, f'a style called "{st["name"]}" exists already: choose another name')
        write_style(key, st)
        edits = read_json(STYLE_EDITS, [])
        rec = {'id': f'{int(time.time() * 1000)}', 'style': key, 'at': time.strftime('%Y-%m-%d %H:%M'),
               'change': clean(change, 400) or 'Copied as it is', 'summary': clean(summary, 300), 'how': 'fork',
               'before': {}, 'after': st, 'source': {'from': parent_key, 'from_name': parent.get('name', parent_key)},
               'undone': False}
        edits.append(rec)
        write_json(STYLE_EDITS, edits)
    return rec


def migrate_drafts():
    """Marks made before 21 Nov 2026 waited as drafts until "Save ratings". Marks are saved at once now: save the old
    ones on start (not ignored, not rated already), keep a copy of the drafts file, then empty it."""
    drafts = read_json(DRAFTS, {})
    if not drafts:
        return
    saved, ignored, n = saved_ratings(), read_json(IGNORED, {}), 0
    for batch, marks in drafts.items():
        if not is_batch(batch):
            continue
        names = rate.batch_images(batch)
        todo = [(name, d['rating'], d.get('why', '')) for name, d in sorted(marks.items())
                if d.get('rating') in rate.RATINGS_ALLOWED and name in names and (batch, name) not in saved
                and name not in ignored.get(batch, [])]
        if todo:
            rate.append_ratings(batch, todo)
            n += len(todo)
    write_json(DRAFTS.with_name('app-drafts.before-autosave.json'), drafts)
    write_json(DRAFTS, {})
    print(f'saved {n} marks that were waiting as drafts (copy: app-drafts.before-autosave.json)')


# -- distil in the app (21 Nov 2026, "option 1"): Codex proposes per style from the ratings since the last distil,
# Marc reviews and applies style by style, then marks the distil done. Proposals live in distil-run.json, so they
# survive closing the page or restarting the app. Options 2 (scheduled Claude) and 3 (automatic) are parked.

DISTIL_RUN = BASE / 'distil-run.json'
DISTIL_MIN = 2          # ratings a style needs since the last distil before Codex is asked about it
_DLOCK = threading.Lock()
_AUTO = threading.Lock()  # one automatic start at a time (several thumbs can arrive together)
_DRUN = {}              # the current round, in memory once loaded: the worker threads and Marc's decisions share it


def current_run():
    if 'run' not in _DRUN:
        _DRUN['run'] = read_json(DISTIL_RUN, None)
    return _DRUN['run']


def distil_since():
    """{style: {'n', 'up', 'down', 'images': [{batch, name, rating, why}]}} for the ratings since the last distil."""
    out = {}
    for r in rate.since_last():
        if r['rating'] not in ('keep', 'no'):
            continue
        d = out.setdefault(r['style'] or '(no style)', {'n': 0, 'up': 0, 'down': 0, 'images': []})
        d['n'] += 1
        d['up' if r['rating'] == 'keep' else 'down'] += 1
        d['images'].append({'batch': r['batch'], 'name': r['name'], 'rating': r['rating'], 'why': r['why']})
    return out


def distil_state():
    run = current_run()
    st = read_json(rate.STATE, {})
    since = distil_since()
    last = None if run else read_json(DISTIL_RUN.with_name(DISTIL_RUN.stem + '.last.json'), None)
    return {'run': run, 'last': last, 'since': since, 'total': sum(d['n'] for d in since.values()), 'due': rate.DUE,
            'marked': st.get('marked'), 'min': DISTIL_MIN, 'dry_run': DRY_RUN}


def _save_run(run):
    with _DLOCK:
        write_json(DISTIL_RUN, run)


def start_distil(styles):
    """Ask Codex about each style (3 at a time). Each style's card fills in as its answer arrives."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    if RESTARTING.is_set():
        raise ApiError(503, 'the app is restarting after an update: try again in a few seconds')
    since = distil_since()
    all_rows = list(csv.DictReader(open(rate.RATINGS, encoding='utf-8'))) if rate.RATINGS.exists() else []
    run = {'started': time.strftime('%Y-%m-%d %H:%M'), 'running': True, 'finished': None, 'rows_at_start': len(all_rows),
           'styles': {s: {'status': 'waiting', 'n': since[s]['n'], 'up': since[s]['up'], 'down': since[s]['down']} for s in styles}}
    _DRUN['run'] = run
    _save_run(run)
    SPECS.mkdir(parents=True, exist_ok=True)
    rows = [r for r in rate.since_last() if r['rating'] in ('keep', 'no')]

    def one(style):
        card = run['styles'][style]
        card['status'] = 'thinking'
        _save_run(run)
        try:
            f = SPECS / f'distil-{style}.json'
            write_json(f, [{k: r[k] for k in ('rating', 'why', 'change', 'prompt')} for r in rows if r['style'] == style])
            r = text_job('distil', '--style', style, '--ratings', str(f))
            f.unlink(missing_ok=True)
            now = style_file(style)
            card.update(status='ready' if r['changes'] else 'nothing', summary=r.get('summary', ''),
                        changes=r['changes'], before={k: now.get(k) for k in r['changes']}, seconds=r.get('seconds'))
        except Exception as e:  # one style failing never stops the others
            card.update(status='failed', error=str(e)[:300])
        _save_run(run)

    def all_of_them():
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(one, styles))
        run.update(running=False, finished=time.strftime('%Y-%m-%d %H:%M'))
        _save_run(run)
        close_if_decided(run)
    threading.Thread(target=all_of_them, daemon=True).start()
    return run


def close_if_decided(run):
    """A round closes on its own once nothing waits for Marc (21 Nov 2026, "tech out of sight"): no proposal left
    to apply or skip. The next round then starts after the ratings that existed when this one started. A round in
    which every style failed stays open, so its ratings are not lost."""
    import datetime
    if run.get('running') or any(c['status'] == 'ready' for c in run['styles'].values()):
        return False
    if run['styles'] and all(c['status'] == 'failed' for c in run['styles'].values()):
        return False
    if not DRY_RUN:
        rows = run.get('rows_at_start')
        if rows is None:   # a round from before 21 Nov 2026 05:40: everything rated so far
            rows = len(list(csv.DictReader(open(rate.RATINGS, encoding='utf-8')))) if rate.RATINGS.exists() else 0
        write_json(rate.STATE, {'rows': rows, 'marked': datetime.date.today().isoformat()})
    run['closed'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    write_json(DISTIL_RUN.with_name(DISTIL_RUN.stem + '.last.json'), run)
    DISTIL_RUN.unlink(missing_ok=True)
    _DRUN['run'] = None
    return True


def maybe_auto_distil():
    """Codex checks the styles by itself when DUE ratings have piled up since the last round (never in dry run)."""
    if DRY_RUN or RESTARTING.is_set() or current_run() or not _AUTO.acquire(blocking=False):
        return
    try:
        _auto_distil()
    finally:
        _AUTO.release()


def _auto_distil():
    if current_run():
        return
    since = distil_since()
    if sum(d['n'] for d in since.values()) < rate.DUE:
        return
    styles = [k for k, d in sorted(since.items(), key=lambda kv: -kv[1]['n'])
              if d['n'] >= DISTIL_MIN and (ROOT / 'taste' / 'styles' / f'{k}.json').exists()]
    if styles:
        start_distil(styles)


def suggestions():
    """For the header: how many style suggestions wait for Marc (nothing while Codex is still at work)."""
    run = current_run()
    return {'ready': sum(1 for c in run['styles'].values() if c['status'] == 'ready') if run else 0}


# -- archive and history of styles (23 Nov 2026). Archiving moves taste/styles/<key>.json to taste/styles/archived/:
# every script that globs taste/styles/*.json or reads taste.json then skips the style, with no change to it.

STYLES_DIR = ROOT / 'taste' / 'styles'
ARCHIVED = STYLES_DIR / 'archived'
_hist = {}     # {style: (cache key, answer)}: the history is read from files and git, so it is kept until one changes


def archived_keys():
    return sorted(p.stem for p in ARCHIVED.glob('*.json')) if ARCHIVED.is_dir() else []


def style_busy(key):
    """Why a style cannot be switched off right now (a run or a distil round is using it), or ''."""
    with _QLOCK:
        queued = any(key in (s.get('styles') or []) for s in QUEUE)
        running = bool(CUR.get('running')) and key in (CUR.get('styles') or [])
    if running or queued:
        return 'a run that uses it is ' + ('running' if running else 'waiting in the queue')
    run = current_run()
    # a proposal that is ready and waits for Marc does not lock it (23 Nov 2026): switching off sets it aside
    if run and run['styles'].get(key, {}).get('status') in ('waiting', 'thinking'):
        return 'Codex is working on suggestions for it'
    return ''


def rebuild_taste():
    import subprocess
    r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'build_taste.py'), str(ROOT)], cwd=ROOT,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        raise ApiError(500, 'build_taste.py failed: ' + (r.stderr or r.stdout).strip()[-300:])


def _shelve_proposal(key, off):
    """Off: a suggestion waiting for this style is set aside (skipped, why 'switched off'). On again: it comes back."""
    run = current_run()
    card = (run or {}).get('styles', {}).get(key)
    if not card:
        return
    if off and card.get('status') == 'ready':
        card.update(status='skipped', why='switched off')
    elif not off and card.get('status') == 'skipped' and card.get('why') == 'switched off':
        card['status'] = 'ready'
        card.pop('why', None)
    else:
        return
    _save_run(run)


def set_archived(key, off):
    """Switch a style off (move its file to archived/) or on again. Logged like the other style edits."""
    import time
    if not key or '/' in key or '\\' in key or key.startswith('.'):
        raise ApiError(400, f'unknown style "{key}"')
    live, shelf = STYLES_DIR / f'{key}.json', ARCHIVED / f'{key}.json'
    src, dst = (live, shelf) if off else (shelf, live)
    with LOCK:
        if not src.is_file():
            if dst.is_file():
                raise ApiError(409, f'"{key}" is already {"off" if off else "on"}')
            raise ApiError(404, f'unknown style "{key}"')
        if dst.exists():
            raise ApiError(409, f'a style called "{key}" exists already')
        if off and (why := style_busy(key)):
            raise ApiError(409, f'Cannot switch it off now: {why}')
        name = read_json(src, {}).get('name', key)
        ARCHIVED.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        try:
            rebuild_taste()
        except ApiError:
            os.replace(dst, src)   # leave things as they were
            raise
        _shelve_proposal(key, off)
        edits = read_json(STYLE_EDITS, [])
        rec = {'id': f'{int(time.time() * 1000)}', 'style': key, 'at': time.strftime('%Y-%m-%d %H:%M'),
               'change': f'Switched {name} {"off" if off else "on"}', 'summary': '', 'how': 'archive' if off else 'unarchive',
               'before': {}, 'after': {}, 'source': None, 'undone': False}
        edits.append(rec)
        write_json(STYLE_EDITS, edits)
    return rec


def style_runs():
    """{style: [batch rows]}: per style and batch, the images made, their latest marks and when the batch began.
    A row: {batch, date, first ('YYYY-MM-DD HH:MM'), images, up, down, kept, imgs: [(at, mark)]}."""
    marks = {k: v['rating'] for k, v in saved_ratings().items()}
    kept = kept_set()
    per = {}
    if rate.RUNS.exists():
        rows = {}
        for r in csv.DictReader(open(rate.RUNS, encoding='utf-8')):
            rows[(r['batch'], r['name'])] = r   # the last row per image wins
        for (batch, name), r in rows.items():
            if r['ok'] != 'yes' or not r['style'] or not (BASE / batch / f'{name}.png').is_file():
                continue
            at = f"{r['date']} {r['time'] or '00:00'}"
            b = per.setdefault(r['style'], {}).setdefault(batch, {'batch': batch, 'date': r['date'], 'first': at, 'images': 0,
                                                                  'up': 0, 'down': 0, 'kept': 0, 'imgs': []})
            m = marks.get((batch, name))
            b['first'] = min(b['first'], at)
            b['images'] += 1
            b['up'] += m == 'keep'
            b['down'] += m == 'no'
            b['kept'] += (batch, name) in kept
            b['imgs'].append((at, m))
    return {k: sorted(v.values(), key=lambda b: (b['first'], b['batch'])) for k, v in per.items()}


def rate_of(up, down):
    return {'up': up, 'down': down, 'n': up + down, 'rate': round(up / (up + down), 3) if up + down else None}


def styles_overview():
    """One row per style (on and off) for the Styles page: images, thumbs-up rate, kept, last run, sparkline."""
    runs = style_runs()
    out = []
    for key, on in [(k, True) for k in sorted(p.stem for p in STYLES_DIR.glob('*.json'))] + [(k, False) for k in archived_keys()]:
        s = read_json((STYLES_DIR if on else ARCHIVED) / f'{key}.json', {})
        bs = runs.get(key, [])
        up, down = sum(b['up'] for b in bs), sum(b['down'] for b in bs)
        marked = [b for b in bs if b['up'] + b['down']][-8:]
        out.append({'key': key, 'name': s.get('name', key), 'palette': s.get('palette', [])[:5], 'on': on,
                    'images': sum(b['images'] for b in bs), 'batches': len(bs), **rate_of(up, down),
                    'kept': sum(b['kept'] for b in bs), 'last': max((b['first'] for b in bs), default=''),
                    'spark': [rate_of(b['up'], b['down'])['rate'] for b in marked],
                    'busy': style_busy(key) if on else ''})
    return {'styles': out}


def git_events(key):
    """Commits that added or changed the style file: the public repo (older history) and taste/ (the private repo)."""
    import subprocess
    out, private_root = [], None
    for repo, path in ((ROOT, f'taste/styles/{key}.json'), (ROOT / 'taste', f'styles/{key}.json')):
        try:
            r = subprocess.run(['git', '-C', str(repo), 'log', '--diff-filter=AM', '--format=%aI|%s', '--', path],
                               capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
            lines = r.stdout.splitlines() if r.returncode == 0 else []
            if repo != ROOT and lines:
                root = subprocess.run(['git', '-C', str(repo), 'log', '--max-parents=0', '--format=%aI'],
                                      capture_output=True, text=True, timeout=10).stdout.split()
                private_root = root[0] if root else None
        except Exception:
            lines = []
        for line in lines:
            iso, _, subject = line.partition('|')
            out.append({'at': iso[:16].replace('T', ' '), 'iso': iso, 'kind': 'commit', 'title': subject, 'private': repo != ROOT})
    # the move to the private repo only re-adds the file: when the public history says more, leave that commit out
    if any(not e['private'] for e in out) and private_root:
        out = [e for e in out if not (e['private'] and e['iso'] == private_root)]
    return out


def style_history(key):
    on = (STYLES_DIR / f'{key}.json').is_file()
    if not on and not (ARCHIVED / f'{key}.json').is_file():
        raise ApiError(404, f'unknown style "{key}"')
    path = (STYLES_DIR if on else ARCHIVED) / f'{key}.json'
    stamp = lambda p: p.stat().st_mtime_ns if p.exists() else 0  # noqa: E731
    cache_key = tuple(stamp(p) for p in (path, rate.RUNS, rate.RATINGS, STYLE_EDITS, KEPT, ROOT / '.git' / 'logs' / 'HEAD',
                                         ROOT / 'taste' / '.git' / 'logs' / 'HEAD')) \
        + (len([p for p in BASE.iterdir() if p.is_dir()]) if BASE.exists() else 0,)
    hit = _hist.get(key)
    if hit and hit[0] == cache_key:
        return hit[1]
    batches = style_runs().get(key, [])
    edits = [e for e in read_json(STYLE_EDITS, []) if e.get('style') == key]
    kinds = {'new': 'created', 'fork': 'fork', 'codex': 'edit', 'words': 'edit', 'distil': 'distil', 'archive': 'off', 'unarchive': 'on'}
    events = []
    for e in edits:
        events.append({'at': e['at'], 'kind': kinds.get(e.get('how'), 'edit'), 'title': e.get('change', ''),
                       'detail': e.get('summary', ''), 'undone': bool(e.get('undone')), 'id': e.get('id'),
                       **({'of': (e.get('source') or {}).get('from_name') or (e.get('source') or {}).get('from', '')} if e.get('how') == 'fork' else {})})
    for e in read_json(STYLE_EDITS, []):   # forks made from this style: "Forked into <Fork>"
        if e.get('how') == 'fork' and (e.get('source') or {}).get('from') == key:
            events.append({'at': e['at'], 'kind': 'fork-out', 'title': e.get('change', ''), 'detail': e.get('summary', ''),
                           'undone': bool(e.get('undone')), 'id': e.get('id'), 'of': (e.get('after') or {}).get('name', e['style'])})
    commits = git_events(key)
    if not any(e['kind'] in ('created', 'fork') and not e['undone'] for e in events) and commits:
        min(commits, key=lambda c: c['iso'])['kind'] = 'created'
    events += [{k: v for k, v in c.items() if k not in ('iso', 'private')} | {'undone': False} for c in commits]
    events.sort(key=lambda e: (e['at'], e.get('id') or ''))
    imgs = sorted((i for b in batches for i in b['imgs']), key=lambda i: i[0])   # by time only: marks can be None
    live = [e for e in events if not e['undone'] and e['kind'] != 'fork-out']   # forking out changes nothing here
    cuts = [e['at'] for e in live]

    def segment(lo, hi):   # images made from lo (included) to hi (excluded): the thumbs-up rate and n
        sel = [m for at, m in imgs if (lo is None or at >= lo) and (hi is None or at < hi)]
        return {**rate_of(sel.count('keep'), sel.count('no')), 'images': len(sel)}
    for i, e in enumerate(live):
        e['before'] = segment(cuts[i - 1] if i else None, e['at'])
        e['after'] = segment(e['at'], cuts[i + 1] if i + 1 < len(cuts) else None)
    for e in events:
        if e['undone'] or e['kind'] == 'fork-out':
            e['before'] = e['after'] = None
        e['index'] = sum(1 for b in batches if b['first'] < e['at'])   # it sits after this many batches
    rows = [{k: v for k, v in b.items() if k != 'imgs'} | rate_of(b['up'], b['down']) for b in batches]
    up, down = sum(b['up'] for b in batches), sum(b['down'] for b in batches)
    ans = {'key': key, 'on': on, 'name': read_json(path, {}).get('name', key), 'events': events, 'batches': rows,
           'total': {'images': sum(b['images'] for b in batches), 'kept': sum(b['kept'] for b in batches), **rate_of(up, down)}}
    _hist[key] = (cache_key, ans)
    return ans


# ---------------------------------------------------------------- HTTP

class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = 'taste-app'

    # Routes: (method, first path part) -> method name. Kept as a table so the API reads at a glance.
    ROUTES = {
        ('GET', 'api/batches'): 'get_batches',
        ('GET', 'api/batch'): 'get_batch',
        ('GET', 'api/styles'): 'get_styles',
        ('GET', 'api/styles/overview'): 'get_styles_page',
        ('GET', 'api/styles/history'): 'get_style_history',
        ('POST', 'api/styles/switch'): 'post_style_switch',
        ('PUT', 'api/mark'): 'put_mark',
        ('POST', 'api/keep'): 'post_keep',
        ('GET', 'api/kept'): 'get_kept',
        ('POST', 'api/publish'): 'post_publish',
        ('GET', 'api/leaning'): 'get_leaning',
        ('POST', 'api/ignore'): 'post_ignore',
        ('POST', 'api/save'): 'post_save',
        ('GET', 'api/allowance'): 'get_allowance',
        ('POST', 'api/cloudflare/connect'): 'post_cloudflare_connect',
        ('POST', 'api/cloudflare/disconnect'): 'post_cloudflare_disconnect',
        ('GET', 'api/blocked'): 'get_blocked',
        ('POST', 'api/blocked/flux'): 'post_blocked_flux',
        ('POST', 'api/guess'): 'post_guess',
        ('POST', 'api/variations'): 'post_variations',
        ('POST', 'api/run'): 'post_run',
        ('GET', 'api/stopped'): 'get_stopped',
        ('POST', 'api/resume-all'): 'post_resume_all',
        ('POST', 'api/preview'): 'post_preview',
        ('POST', 'api/stop'): 'post_stop',
        ('POST', 'api/queue/cancel'): 'post_queue_cancel',
        ('POST', 'api/queue/resume'): 'post_queue_resume',
        ('POST', 'api/queue/move'): 'post_queue_move',
        ('POST', 'api/text/subjects'): 'post_text_subjects',
        ('POST', 'api/text/rewrite'): 'post_text_rewrite',
        ('POST', 'api/reveal'): 'post_reveal',
        ('GET', 'api/notes'): 'get_notes',
        ('POST', 'api/notes/delete'): 'post_notes_delete',
        ('POST', 'api/notes'): 'post_notes',
        ('POST', 'api/style/propose'): 'post_style_propose',
        ('POST', 'api/style/apply'): 'post_style_apply',
        ('POST', 'api/style/undo'): 'post_style_undo',
        ('POST', 'api/style/new/propose'): 'post_style_new_propose',
        ('POST', 'api/style/new/create'): 'post_style_new_create',
        ('POST', 'api/style/fork/propose'): 'post_style_fork_propose',
        ('POST', 'api/style/fork/create'): 'post_style_fork_create',
        ('GET', 'api/style/edits'): 'get_style_edits',
        ('GET', 'api/distil/state'): 'get_distil_state',
        ('POST', 'api/distil/run'): 'post_distil_run',
        ('POST', 'api/distil/decide'): 'post_distil_decide',
        ('POST', 'api/distil/mark'): 'post_distil_mark',
        ('GET', 'api/job'): 'get_job',
        ('GET', 'api/overview'): 'get_overview',
        ('GET', 'api/distil'): 'get_distil',
        ('GET', 'api/gallery'): 'get_gallery',
        ('GET', 'api/similar'): 'get_similar',
    }

    def log_message(self, fmt, *args):  # quiet: only errors reach the console
        if args and str(args[1])[:1] in '45':
            sys.stderr.write('%s %s\n' % (self.command, fmt % args))

    # -- plumbing

    def check_host(self):
        """Reject requests whose Host is not this machine (blocks DNS-rebinding tricks from web pages)."""
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        if host not in ('127.0.0.1', 'localhost'):
            raise ApiError(403, 'local use only')

    def read_body(self, limit=100_000):
        """JSON body of a write. Writes need the page's own header: a page on another site can't add it
        without a CORS preflight, which this server never answers, so only the taste page can write."""
        if self.headers.get('X-Taste-App') != '1' or 'application/json' not in (self.headers.get('Content-Type') or ''):
            raise ApiError(403, 'writes only from the taste page')
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise ApiError(413, 'request too large')
        try:
            return json.loads(self.rfile.read(n) or b'{}')
        except json.JSONDecodeError:
            raise ApiError(400, 'bad JSON')

    def image_from(self, body):
        """(batch, name) from a request body, checked: the image must exist and not be saved yet."""
        batch, name = str(body.get('batch', '')), str(body.get('name', ''))
        if not is_batch(batch) or name not in rate.batch_images(batch):
            raise ApiError(404, f'no image "{name}" in batch "{batch}"')
        if (batch, name) in saved_ratings():
            raise ApiError(409, 'this image is rated: take the mark back first')
        return batch, name

    def send(self, status, body, ctype='application/json', cache=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache or 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, cache=None):
        self.send(200, path.read_bytes(), TYPES.get(path.suffix.lower(), 'application/octet-stream'), cache)

    def handle_any(self, method):
        with _ALOCK:
            ACTIVE[0] += 1
        try:
            self.answer(method)
        finally:
            with _ALOCK:
                ACTIVE[0] -= 1

    def answer(self, method):
        try:
            self.check_host()
            path = unquote(urlparse(self.path).path).strip('/')
            parts = path.split('/')
            # 1. API
            for (m, prefix), fn in sorted(self.ROUTES.items(), key=lambda kv: -len(kv[0][1])):   # longest path first
                if m == method and (path == prefix or path.startswith(prefix + '/')):
                    args = [p for p in path[len(prefix):].split('/') if p]
                    return self.send(200, getattr(self, fn)(*args))
            if method != 'GET':
                if path.startswith('api/') and code_stamp() > BORN[0]:   # the page is newer than this server (24 Nov 2026)
                    raise ApiError(409, 'the app was just updated and restarts by itself once the current run ends; try again then')
                raise ApiError(404, 'not found')
            # 2. Images and thumbnails: /img/<batch>/<file>, /thumb/<batch>/<file>
            if parts[0] in ('img', 'thumb') and len(parts) == 3:
                batch, file = parts[1], parts[2]
                if not is_batch(batch) or file.startswith('.') or not (BASE / batch / file).is_file() \
                        or Path(file).suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                    raise ApiError(404, 'no such image')
                # The URL carries ?v=<mtime>, so the browser may keep the file: a new image gets a new URL.
                src = thumbnail(batch, file) if parts[0] == 'thumb' else BASE / batch / file
                return self.send_file(src, cache='private, max-age=31536000, immutable')
            # 2a. A batch as one zip: /zip/<batch>?files=a.png,b.png (no files: every image; 23 Nov 2026). PNGs are already
            #     compressed, so they are stored as they are: fast, same size.
            if parts[0] == 'zip' and len(parts) == 2:
                batch = parts[1]
                if not is_batch(batch):
                    raise ApiError(404, f'no batch "{batch}"')
                images = {f'{n}.png' for n in rate.batch_images(batch)}   # the batch's own images: no seed, no sheet
                asked = parse_qs(urlparse(self.path).query).get('files', [''])[0]
                files = sorted(images & set(asked.split(','))) if asked else sorted(images)
                if not files:
                    raise ApiError(404, 'no images to zip')
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
                    for f in files:
                        z.write(BASE / batch / f, f)
                self.send_response(200)
                body = buf.getvalue()
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Content-Disposition', f'attachment; filename="{batch}.zip"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
                return
            # 2b. Reference images of a style: /ref/<style>/ref-N.jpg
            if parts[0] == 'ref' and len(parts) == 3:
                folder, file = parts[1], parts[2]
                f = REFS / folder / file
                if folder.startswith('.') or not (file.startswith('ref-') and file.endswith('.jpg')) or not f.is_file():
                    raise ApiError(404, 'no such image')
                return self.send_file(f, cache='private, max-age=3600')
            # 3. The page itself: / -> app/index.html, anything else from app/
            target = (APP_DIR / (path or 'index.html')).resolve()
            if APP_DIR.resolve() not in target.parents or not target.is_file():
                raise ApiError(404, 'not found')
            return self.send_file(target)
        except ApiError as e:
            self.send(e.status, {'error': str(e)})
        except Exception as e:  # report, keep serving
            self.send(500, {'error': f'{type(e).__name__}: {e}'})

    def do_GET(self):
        self.handle_any('GET')

    def do_POST(self):
        self.handle_any('POST')

    def do_PUT(self):
        self.handle_any('PUT')

    # -- API handlers: return plain data, the plumbing turns it into JSON

    def get_batches(self):
        return {'batches': list_batches()}

    def get_batch(self, batch=''):
        if not is_batch(batch):
            raise ApiError(404, f'no batch "{batch}"')
        images = batch_images(batch)
        lin = lineage()
        children = []
        for c, src in sorted(lin.items()):
            if src.get('batch') == batch:
                names = rate.batch_images(c)
                children.append({'batch': c, 'file': src['file'], 'kind': kind_of_batch(c, [], run_record(c)),
                                 'images': len(names), 'preview': names[0] + '.png' if names else None})
        unmade = unmade_images(batch, {im['name'] for im in images})
        return {**summary(batch, images), 'items': images, 'run': run_record(batch), 'parent': lin.get(batch),
                'children': children, 'failed': failed_images(batch, {im['name'] for im in images}),
                'unmade': unmade[0], 'unmade_why': unmade[1], 'planned': len(unmade[0]) + len(images),
                'resume': limit_stopped(batch, {im['name'] for im in images}) if run_record(batch) else [],
                'path': str(BASE / batch), 'rel_path': f'generated/codex/{batch}'}

    def put_mark(self):
        """Mark one image, saved at once: {batch, name, rating: keep (up) | no (down) | null (take back), why}.
        Appends a row to ratings.csv (the latest row per image wins) and says which parts of the style's prompt the
        mark moves (scripts/leaning.py), so the page can tell Marc how new runs will lean."""
        body = self.read_body()
        batch, name = str(body.get('batch', '')), str(body.get('name', ''))
        if not is_batch(batch) or name not in rate.batch_images(batch):
            raise ApiError(404, f'no image "{name}" in batch "{batch}"')
        rating, why = body.get('rating'), ' '.join(str(body.get('why') or '').split())[:300]
        if rating not in (None, *rate.RATINGS_ALLOWED):
            raise ApiError(400, 'rating must be keep (up), no (down) or null')
        with LOCK:
            if name in read_json(IGNORED, {}).get(batch, []):
                raise ApiError(409, 'this image is ignored: restore it first')
            now = saved_ratings().get((batch, name))
            if rating is None:
                if now:
                    rate.append_ratings(batch, [(name, 'cleared', '')], allow_clear=True)
            elif not now or now['rating'] != rating or now['why'] != why:
                rate.append_ratings(batch, [(name, rating, why)])
        threading.Thread(target=maybe_auto_distil, daemon=True).start()
        run = rate.batch_runs(batch).get(name, {})
        from leaning import matched_axes
        return {'ok': True, 'style': run.get('style', ''), 'moves': matched_axes(run.get('style', ''), run.get('prompt', '')),
                'since_last': len(rate.since_last()), 'due': rate.DUE}

    def post_keep(self):
        """Keep (or stop keeping) one image as an example of its style: {batch, name, kept: true|false}.
        New batch and single-image runs of that style can send up to 2 kept images along as references."""
        body = self.read_body()
        batch, name = str(body.get('batch', '')), str(body.get('name', ''))
        if not is_batch(batch) or name not in rate.batch_images(batch):
            raise ApiError(404, f'no image "{name}" in batch "{batch}"')
        style = rate.batch_runs(batch).get(name, {}).get('style', '')
        want = bool(body.get('kept'))
        if want and not style:
            raise ApiError(400, 'this image has no style to be an example of')
        with LOCK:
            rest = [k for k in kept_list() if (k['batch'], k['name']) != (batch, name)]
            if want:
                import time
                rest.append({'batch': batch, 'name': name, 'style': style, 'at': time.strftime('%Y-%m-%d %H:%M')})
            write_json(KEPT, rest)
        return {'ok': True, 'kept': want, 'style': style, 'count': sum(1 for k in rest if k.get('style') == style)}

    def post_publish(self):
        """Pick (or take back) one image for the public gallery site: {batch, name, published: true|false}.
        Only the file generated/codex/publish.json changes; scripts/publish.py reads it."""
        body = self.read_body()
        batch, name = str(body.get('batch', '')), str(body.get('name', ''))
        if not is_batch(batch) or name not in rate.batch_images(batch):
            raise ApiError(404, f'no image "{name}" in batch "{batch}"')
        style = rate.batch_runs(batch).get(name, {}).get('style', '')
        want = bool(body.get('published'))
        with LOCK:
            rest = [k for k in publish_list() if (k['batch'], k['name']) != (batch, name)]
            if want:
                import time
                rest.append({'batch': batch, 'name': name, 'style': style, 'at': time.strftime('%Y-%m-%d %H:%M')})
            write_json(PUBLISH, rest)
        schedule_gallery_sync()
        return {'ok': True, 'published': want, 'count': len(rest)}

    def get_kept(self):
        """How many examples are kept per style (the New run page offers to send them along)."""
        counts = {}
        for k in kept_list():
            if k.get('style') and (BASE / k['batch'] / f"{k['name']}.png").is_file():
                counts[k['style']] = counts.get(k['style'], 0) + 1
        return {'counts': counts}

    def get_leaning(self, style=''):
        """What the ratings say per option of each style's prompt, and liked / disliked subjects."""
        from leaning import leaning, latest_marks
        taste = read_json(ROOT / 'taste' / 'taste.json', {}).get('styles', {})
        marks = latest_marks()
        keys = [style] if style else sorted(taste)
        return {'leaning': {k: leaning(k, taste, marks) for k in keys if k in taste}}

    def post_ignore(self):
        """Hide or show one image: {batch, name, ignored: true|false}. The file stays on disk."""
        body = self.read_body()
        batch, name = self.image_from(body)
        with LOCK:
            ignored = read_json(IGNORED, {})
            names = set(ignored.get(batch, []))
            (names.add if body.get('ignored') else names.discard)(name)
            if names:
                ignored[batch] = sorted(names)
            else:
                ignored.pop(batch, None)
            write_json(IGNORED, ignored)
        return {'ok': True}

    def post_save(self):
        """Append the batch's drafts to ratings.csv (ignored images left out), then clear those drafts."""
        batch = str(self.read_body().get('batch', ''))
        if not is_batch(batch):
            raise ApiError(404, f'no batch "{batch}"')
        with LOCK:
            drafts = read_json(DRAFTS, {})
            mine = drafts.get(batch, {})
            ignored = set(read_json(IGNORED, {}).get(batch, []))
            saved, names = saved_ratings(), rate.batch_images(batch)
            marks = [(n, d['rating'], d.get('why', '')) for n, d in sorted(mine.items())
                     if d.get('rating') and n in names and n not in ignored and (batch, n) not in saved]
            if not marks:
                raise ApiError(400, 'nothing to save: mark an image first')
            rows = rate.append_ratings(batch, marks)   # the one writer, shared with rate.py
            for n, _, _ in marks:
                mine.pop(n)
            if not mine:
                drafts.pop(batch, None)
            write_json(DRAFTS, drafts)
        return {'saved': len(rows), 'since_last': len(rate.since_last()), 'due': rate.DUE}

    def get_allowance(self):
        return allowance()

    def post_guess(self):
        body = self.read_body()
        return guess_styles(source_image(str(body.get('batch', '')), str(body.get('file', ''))))

    def post_variations(self):
        """Variations of one image: {batch, file, style, changes: [palette, subject, composition, mood] (or n: 3|4),
        subject, note}. Queued: spends Codex allowance when it runs (unless --dry-run)."""
        return self.post_run({**self.read_body(), 'kind': 'variations'})

    def post_run(self, body=None):
        """Queue one run. kind: batch | single | remix | retry | finish | resume | variations (see the spec_* helpers)."""
        body = body or self.read_body()
        make = {'batch': spec_batch, 'single': spec_single, 'remix': spec_remix, 'retry': spec_retry,
                'finish': spec_finish, 'resume': spec_resume, 'variations': spec_variations}.get(body.get('kind'))
        if not make:
            raise ApiError(400, f'unknown kind "{body.get("kind")}"')
        with _QLOCK:
            spec = make(body)
        spec.pop('placeholders', None)
        # Made with (23 Nov 2026): codex, or cloudflare (FLUX, scripts/cf_run.py). A finish, retry or resume keeps
        # the route of the run it continues unless the page says otherwise.
        route = body.get('route') if body.get('route') in ('codex', 'cloudflare') else \
            (run_record(spec.get('batch', '')) or {}).get('route') if body.get('kind') in ('finish', 'retry', 'resume') else None
        spec['route'] = route or 'codex'
        if spec['route'] == 'cloudflare':
            if not cf_run.creds():
                raise ApiError(409, 'Connect Cloudflare first (New run, Made with: FLUX).')
            if spec.get('title') and 'FLUX' not in spec['title']:
                spec['title'] += ' · FLUX'
        return enqueue(spec)

    def post_cloudflare_connect(self):
        """Save the Cloudflare account ID and API token (Connect Cloudflare), after Cloudflare's free verify call.
        Kept in %USERPROFILE%\\.taste\\cloudflare.json, outside the repo; never logged or sent back."""
        body = self.read_body()
        account, token = str(body.get('account_id', '')).strip(), str(body.get('token', '')).strip()
        if not account or not token or len(account) > 64 or len(token) > 200 or not account.isalnum():
            raise ApiError(400, 'Paste the account ID (letters and numbers) and the API token.')
        ok, why = cf_run.verify(account, token)
        if not ok:
            raise ApiError(400, why)
        cf_run.save_creds(account, token)
        return {'connected': True}

    def get_blocked(self):
        """Images Codex's filter blocked that FLUX hasn't tried yet (the bar on Batches)."""
        with _QLOCK:
            runs = all_blocked()
        return {'runs': runs, 'images': sum(len(r['names']) for r in runs), 'connected': bool(cf_run.creds())}

    def post_blocked_flux(self):
        """Queue the blocked images again with FLUX, one run per batch: {} for all, or {batch, name} for one tile."""
        body = self.read_body()
        if not cf_run.creds():
            raise ApiError(409, 'Connect Cloudflare first (New run, Made with: FLUX).')
        with _QLOCK:
            runs = all_blocked()
        if body.get('batch'):
            runs = [{'batch': r['batch'], 'names': [n for n in r['names'] if not body.get('name') or n == body['name']]}
                    for r in runs if r['batch'] == body['batch']]
        queued, images, res = 0, 0, None
        for r in runs:
            if not r['names']:
                continue
            try:
                with _QLOCK:
                    spec = spec_blocked_flux(r['batch'], r['names'])
            except ApiError:
                continue   # its state changed meanwhile
            res = enqueue(spec)
            queued, images = queued + 1, images + len(spec['expected'])
        if not queued:
            raise ApiError(404, 'Nothing blocked is left to try with FLUX.')
        return {**res, 'runs': queued, 'images': images}

    def post_cloudflare_disconnect(self):
        self.read_body()
        cf_run.forget_creds()
        return {'connected': False}

    def get_stopped(self):
        """Runs Codex's usage limit cut short, with what each still has to make (for "Resume all")."""
        with _QLOCK:
            runs = all_limit_stopped()
        return {'runs': runs, 'images': sum(len(r['names']) for r in runs)}

    def post_resume_all(self):
        """Queue one resume run per batch the usage limit cut short, oldest first. One click on the Batches page."""
        self.read_body()
        queued, res, images = [], None, 0
        with _QLOCK:
            runs = all_limit_stopped()
        for r in runs:
            try:
                with _QLOCK:
                    spec = spec_resume({'batch': r['batch']})
            except ApiError:
                continue   # its state changed meanwhile (a run started, images arrived)
            res = enqueue(spec)
            queued.append(res['queued_id'])
            images += len(spec['expected'])
        if not queued:
            raise ApiError(409, 'nothing waits to be made again')
        return {**res, 'queued_ids': queued, 'runs': len(queued), 'images': images}

    def post_preview(self):
        """The prompts a batch would use, without running Codex (batch.py --dry-run). Missing subjects are
        filled with the style's own examples, marked, so the preview never spends anything."""
        import subprocess, tempfile
        spec = spec_batch(self.read_body(), preview=True)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'subjects.json'
            write_json(f, spec['subjects'])
            extra = []
            kept = {st: kept_paths(st) for st in spec['styles']} if spec['use_kept'] else {}
            if any(kept.values()):
                write_json(Path(tmp) / 'kept.json', {st: v for st, v in kept.items() if v})
                extra = ['--kept-refs', str(Path(tmp) / 'kept.json')]
            r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'batch.py'), '--out', str(Path(tmp) / 'out'),
                                '--subjects', str(f), '--styles', ','.join(spec['styles']), '--n', str(spec['n']),
                                '--wildcards', str(spec['wildcards']), '--ratio', spec['ratio'], '--dry-run', *extra,
                                *(['--experimental'] if spec['experimental'] else [])],
                               cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        out = []
        for line in r.stdout.splitlines():
            if line.startswith('{'):
                d = json.loads(line)
                d['placeholder'] = d['name'] in spec['placeholders']
                out.append(d)
        if not out:
            raise ApiError(500, (r.stderr or r.stdout).strip()[-300:] or 'no prompts')
        return {'prompts': out}

    def post_stop(self):
        self.read_body()
        stop_current()
        return job_state()

    def post_queue_cancel(self):
        qid = str(self.read_body().get('id', ''))
        with _QLOCK:
            before = len(QUEUE)
            QUEUE[:] = [s for s in QUEUE if s['id'] != qid]
            if len(QUEUE) == before:
                raise ApiError(404, 'not in the queue any more (it may have started)')
            save_queue()
        return job_state()

    def post_queue_move(self):
        """Up / down in the queue (24 Nov 2026): swap a waiting run with its neighbour; delta -1 up, +1 down."""
        body = self.read_body()
        qid, delta = str(body.get('id', '')), int(body.get('delta', 0))
        if delta not in (-1, 1):
            raise ApiError(400, 'delta must be -1 or 1')
        with _QLOCK:
            i = next((k for k, s in enumerate(QUEUE) if s['id'] == qid), None)
            if i is None:
                raise ApiError(404, 'not in the queue any more (it may have started)')
            j = i + delta
            if 0 <= j < len(QUEUE):
                QUEUE[i], QUEUE[j] = QUEUE[j], QUEUE[i]
                save_queue()
        return job_state()

    def post_queue_resume(self):
        """Continue: lift a hold on the queue (a script-error hold that still doesn't compile comes back)."""
        self.read_body()
        with _QLOCK:
            HOLD.clear()
        _WAKE.set()
        return job_state()

    def post_text_subjects(self):
        """Codex writes fresh subjects for one style: {style, n, hint}. About 15 s; spends a little allowance."""
        body = self.read_body()
        style_file(str(body.get('style', '')))
        n = max(1, min(12, int(body.get('n') or 4)))
        return text_job('subjects', '--style', body['style'], '--n', str(n), '--hint', clean(body.get('hint'), 200),
                        *(['--wild'] if body.get('experimental') else []))

    def post_text_rewrite(self):
        """Codex rewrites an image prompt: {prompt, change, keep: [...]}. About 15 s.
        No prompt on record: {batch, file, style?, change, keep} and Codex writes one from the image (23 Nov 2026)."""
        body = self.read_body()
        prompt, change = clean(body.get('prompt'), 4000), clean(body.get('change'), 400)
        if not change:
            raise ApiError(400, 'say what should change')
        keep = ', '.join(k for k in body.get('keep') or [] if k in KEEPABLE)
        if prompt:
            return text_job('rewrite', '--prompt', prompt, '--change', change, '--keep', keep)
        img = source_image(str(body.get('batch', '')), str(body.get('file', '')))
        style = str(body.get('style') or '')
        style = style if re.fullmatch(r'[\w-]+', style) and (ROOT / 'taste' / 'styles' / f'{style}.json').is_file() else ''
        return text_job('rewrite', '--image', str(img), '--change', change, '--keep', keep,
                        *(['--style', style] if style else []))

    def post_reveal(self):
        """Open a batch folder in Windows Explorer (this machine only)."""
        import subprocess
        batch = str(self.read_body().get('batch', ''))
        if not is_batch(batch):
            raise ApiError(404, f'no batch "{batch}"')
        subprocess.Popen(['explorer.exe', str(BASE / batch)])
        return {'ok': True}

    def get_notes(self):
        return {'notes': read_json(NOTES, {'notes': []})['notes']}

    def post_notes(self):
        """A note for Claude Code: {text, style?, batch?, name?}. Claude reads them with scripts/notes.py."""
        import time
        body = self.read_body()
        text = ' '.join(str(body.get('text') or '').split())[:1000]
        if not text:
            raise ApiError(400, 'write the note first')
        style, batch, name = str(body.get('style') or ''), str(body.get('batch') or ''), str(body.get('name') or '')
        if style:
            style_file(style)
        if batch and not is_batch(batch):
            raise ApiError(404, f'no batch "{batch}"')
        if name and name not in rate.batch_images(batch):
            raise ApiError(404, f'no image "{name}" in "{batch}"')
        note = {'id': f'{int(time.time() * 1000)}', 'created': time.strftime('%Y-%m-%d %H:%M'), 'text': text,
                'style': style, 'batch': batch, 'name': name, 'status': 'open', 'answer': '', 'answered': ''}
        with LOCK:
            d = read_json(NOTES, {'notes': []})
            d['notes'].append(note)
            write_json(NOTES, d)
        return note

    def post_notes_delete(self):
        """Take back a note Claude hasn't answered yet."""
        nid = str(self.read_body().get('id', ''))
        with LOCK:
            d = read_json(NOTES, {'notes': []})
            keep = [n for n in d['notes'] if not (n['id'] == nid and n['status'] == 'open')]
            if len(keep) == len(d['notes']):
                raise ApiError(404, 'no open note with that id (answered notes stay)')
            d['notes'] = keep
            write_json(NOTES, d)
        return {'ok': True}

    def post_style_propose(self):
        """Codex proposes an edit to one style: {style, change}. Read-only, ~15 s; nothing is written."""
        body = self.read_body()
        style, change = str(body.get('style', '')), clean(body.get('change'), 400)
        now = style_file(style)
        if not change:
            raise ApiError(400, 'say what should change')
        r = text_job('style', '--style', style, '--change', change)
        return {**r, 'before': {k: now.get(k) for k in r['changes']}}

    def post_style_apply(self):
        """Apply an edit Marc approved: {style, changes: {field: value}, change, summary, how: codex|words,
        source: {batch, name}}. Rebuilds taste.json; the next image in this style uses it."""
        body = self.read_body()
        src = body.get('source') or {}
        source = {'batch': str(src.get('batch', '')), 'name': str(src.get('name', ''))} if src.get('batch') else None
        rec = apply_style_edit(str(body.get('style', '')), body.get('changes'), body.get('change', ''),
                               body.get('summary', ''), source, 'codex' if body.get('how') == 'codex' else 'words')
        return rec

    def post_style_undo(self):
        return undo_style_edit(str(self.read_body().get('id', '')))

    def post_style_new_propose(self):
        """{images: [data URL, ...], name, notes} -> Codex looks at the images and proposes a whole style
        (~30-60 s); the palette is measured from the pixels. Nothing in taste/ is written yet."""
        body = self.read_body(limit=12_000_000)
        draft, paths = save_refs(body.get('images'))
        name, notes = clean(body.get('name'), 80), clean(body.get('notes'), 400)
        args = ['new', '--images', *map(str, paths)]
        if name:
            args += ['--name', name]
        if notes:
            args += ['--notes', notes]
        r = text_job(*args)
        pal = measured_palette(paths)
        if len(pal) >= 3:
            r['style']['palette'] = pal
        return {**r, 'draft': draft, 'measured': len(pal) >= 3}

    def post_style_new_create(self):
        """{draft, style: {...}, notes, summary}: Marc's Create. Writes taste/styles/<key>.json, rebuilds taste.json,
        moves the references to generated/codex/references/<key>/, logs it for Undo."""
        body = self.read_body()
        return create_style(str(body.get('draft', '')), body.get('style'), body.get('notes', ''),
                            body.get('summary', ''))

    def post_style_fork_propose(self):
        """{style, name, change, copy}: Codex writes a variant of one style (read-only, ~30 s), or copy: true returns
        the parent as it is, no Codex. Nothing is written."""
        body = self.read_body()
        parent = style_file(str(body.get('style', '')))
        name, change = clean(body.get('name'), 80), clean(body.get('change'), 400)
        if body.get('copy'):
            return {'style': {**parent, 'name': name or f"{parent.get('name', '')} (fork)"}, 'summary': '', 'copy': True}
        if not change:
            raise ApiError(400, 'say what should be different, or copy it as it is')
        args = ['fork', '--style', str(body.get('style')), '--change', change]
        if name:
            args += ['--name', name]
        return {**text_job(*args), 'parent': parent}

    def post_style_fork_create(self):
        """{from, style: {...}, change, summary}: Marc's Create. Writes taste/styles/<key>.json, rebuilds taste.json,
        logs it (how: fork) for Undo."""
        body = self.read_body()
        return create_fork(str(body.get('from', '')), body.get('style'), body.get('change', ''), body.get('summary', ''))

    def get_style_edits(self, style=''):
        """Edits made from the page, newest first (one style, or all)."""
        edits = [e for e in read_json(STYLE_EDITS, []) if (not style or e['style'] == style) and e.get('how') not in ('archive', 'unarchive')]
        return {'edits': list(reversed(edits))[:30]}

    def get_distil_state(self):
        return distil_state()

    def post_distil_run(self):
        """Ask Codex for proposals: {styles: [...]} or every style with DISTIL_MIN+ ratings since the last distil."""
        body = self.read_body()
        run = current_run()
        if run and run.get('running'):
            raise ApiError(409, 'Codex is still working on the last request')
        since = distil_since()
        styles = [s for s in (body.get('styles') or sorted(since, key=lambda k: -since[k]['n']))
                  if s in since and since[s]['n'] >= DISTIL_MIN and (ROOT / 'taste' / 'styles' / f'{s}.json').exists()]
        if not styles:
            raise ApiError(400, f'no style has {DISTIL_MIN} or more ratings since the last distil')
        start_distil(styles)
        return distil_state()

    def post_distil_decide(self):
        """Apply (with the fields Marc kept) or skip one style's proposal: {style, action: apply|skip, changes}."""
        body = self.read_body()
        style, action = str(body.get('style', '')), body.get('action')
        run = current_run()
        card = (run or {}).get('styles', {}).get(style)
        if not card or card.get('status') not in ('ready', 'nothing', 'failed'):
            raise ApiError(409, 'no proposal waiting for this style')
        if action == 'apply':
            rec = apply_style_edit(style, body.get('changes'), f'distil {run["started"][:10]}', card.get('summary', ''),
                                   None, 'distil')
            card.update(status='applied', edit=rec['id'])
        elif action == 'skip':
            card['status'] = 'skipped'
        else:
            raise ApiError(400, 'action: apply or skip')
        _save_run(run)
        close_if_decided(run)
        return distil_state()

    def post_distil_mark(self):
        """Mark the distil done (distil.py --mark): the next one starts after the ratings so far. Marc's call."""
        import subprocess
        self.read_body()
        if DRY_RUN:
            raise ApiError(409, 'dry run: the distil is not marked (start the app without --dry-run to mark it)')
        if (current_run() or {}).get('running'):
            raise ApiError(409, 'Codex is still working: wait for the last proposals first')
        r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'distil.py'), '--mark'], cwd=ROOT, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=60)
        if r.returncode:
            raise ApiError(500, (r.stderr or r.stdout).strip()[-300:])
        run = current_run()
        if run and run.get('running'):
            raise ApiError(409, 'Codex is still working: wait for the last proposals first')
        if run:   # keep a copy of the last round, then start clean
            write_json(BASE / 'distil-run.last.json', run)
        DISTIL_RUN.unlink(missing_ok=True)
        _DRUN['run'] = None
        return distil_state()

    def get_job(self):
        return job_state()

    def get_overview(self):
        """Saved ratings per style (all, and since the last distil), the distil countdown, unsaved marks."""
        import collections
        rows = list(csv.DictReader(open(rate.RATINGS, encoding='utf-8'))) if rate.RATINGS.exists() else []
        state = read_json(rate.STATE, {})
        done = state.get('rows', 0)
        per = collections.defaultdict(lambda: {'all': {'keep': 0, 'almost': 0, 'no': 0},
                                               'since': {'keep': 0, 'almost': 0, 'no': 0}})
        marks = rate.latest(rows)   # latest mark per image: a changed mark counts once
        for i, r in marks:
            if r['rating'] in rate.RATINGS_SEEN:
                per[r['style'] or '(no style)']['all'][r['rating']] += 1
                if i >= done:
                    per[r['style'] or '(no style)']['since'][r['rating']] += 1
        unsaved = {}
        rows = [r for _, r in marks]
        done_n = sum(1 for i, _ in marks if i < done)
        return {'styles': per, 'total': len(rows), 'since_last': len(rows) - done_n, 'due': rate.DUE,
                'marked': state.get('marked'),
                'unsaved': {b: n for b, n in unsaved.items() if n},
                'ignored': sum(len(v) for v in read_json(IGNORED, {}).values())}

    def get_distil(self):
        """What distil.py prints now (the summary); the Distil page has the proposals and the mark."""
        import subprocess
        r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'distil.py')], cwd=ROOT, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=60)
        return {'output': (r.stdout + r.stderr).strip(), 'returncode': r.returncode}

    def get_styles(self):
        """The styles that are on, whole: name, palette, description, light, composition, medium, mood, detail,
        avoid, subjects and uses (the picker and labels use the first three, the Taste page all of it).
        'archived' holds the ones switched off (23 Nov 2026), so labels still find their names."""
        out, off = {}, {}
        for folder, into in ((STYLES_DIR, out), (ARCHIVED, off)):
            for p in sorted(folder.glob('*.json')):
                s = read_json(p, {})
                into[p.stem] = {**s, 'name': s.get('name', p.stem), 'palette': s.get('palette', [])[:7],
                                'description': s.get('description', '')}
                refs = REFS / p.stem
                if refs.is_dir():   # started from reference images in the page
                    into[p.stem]['refs'] = sorted(f.name for f in refs.glob('ref-*.jpg'))
        return {'styles': out, 'archived': off}

    def get_styles_page(self):
        """The Styles page: one row per style, on and off. Free: reads files."""
        return styles_overview()

    def get_style_history(self, key=''):
        """One style's timeline, runs and thumbs-up rate before and after each event. Free: files and git log."""
        return style_history(key)

    def post_style_switch(self):
        """Switch a style off or on: {style, on: true|false}. Off moves its file to taste/styles/archived/."""
        body = self.read_body()
        return set_archived(str(body.get('style', '')), not body.get('on'))

    def get_similar(self, batch='', name='', mode=''):
        """The 8 images that look most like this one (colour and framing, scripts/similar.py), in the Gallery's shape.
        mode 'same': only this image's style. Free: reads thumbnails, spends nothing."""
        from similar import update_index, nearest
        if not is_batch(batch) or name not in rate.batch_images(batch):
            raise ApiError(404, f'no image "{name}" in batch "{batch}"')
        imgs = {f"{x['batch']}/{x['name']}": x for x in self.gallery_images()}
        me = f'{batch}/{name}'
        if me not in imgs:
            return {'items': []}
        with LOCK_SIMILAR:
            vectors = update_index(BASE / '.look-index.json',
                                   [(k, thumbnail(x['batch'], x['file']), x['mtime']) for k, x in imgs.items()])
        allowed = {k for k, x in imgs.items() if x['style'] == imgs[me]['style']} if mode == 'same' else None
        return {'items': [{**imgs[k], 'distance': round(d, 2)} for k, d in nearest(vectors, me, 8, allowed)]}

    def get_gallery(self):
        """Every image of every batch, newest first, ignored ones left out. The Gallery and Taste pages show
        these; the Gallery's large view can mark them too (PUT /api/mark, 21 Nov 2026). Seeds are left out
        (rate.batch_images skips them), so wallpapers by other people never show here."""
        return {'images': self.gallery_images()}

    def gallery_images(self):
        out = []
        names = [p.name for p in BASE.iterdir() if is_batch(p.name)] if BASE.exists() else []
        shared = (all_runs(), saved_ratings(), read_json(IGNORED, {}), kept_set(), publish_set())
        for b in names:
            for im in batch_images(b, shared):
                if im['status'] == 'ignored':
                    continue
                s = im['draft']   # the current mark ("saved" is always empty since marks save at once)
                out.append({'batch': b, 'name': im['name'], 'file': im['file'], 'mtime': im['mtime'],
                            'style': im['style'], 'mode': im['mode'], 'change': im['change'],
                            'prompt': im['prompt'], 'width': im['width'], 'height': im['height'],
                            'date': im['date'] or b[:10], 'number': im['number'], 'seed': im['seed'],
                            'time': im['time'], 'seconds': im['seconds'], 'route': im['route'],
                            'rating': s['rating'] if s else None, 'why': s['why'] if s else '', 'kept': im['kept'],
                            'published': im['published']})
        out.sort(key=lambda x: x['mtime'], reverse=True)
        return out


def supervise():
    """The process that was started keeps the server running as a child, with the project .venv Python, and starts
    it again when it exits with RESTART: its code changed while nothing was running (23 Nov 2026). So the page
    never meets a server older than itself, and whoever started the app (a terminal, the preview) keeps one process
    on the same port. This loop never reloads itself: keep it small."""
    import subprocess
    venv = ROOT / '.venv' / 'Scripts' / 'python.exe'
    py = str(venv) if venv.exists() else sys.executable
    env = {**os.environ, 'TASTE_APP_PARENT': str(os.getpid())}
    args = sys.argv[1:]
    import time
    while True:
        try:
            code = subprocess.call([py, '-I', str(Path(__file__).resolve()), *args], env=env)
            if code not in (0, RESTART):
                # A crash, usually a half-finished edit in scripts/ (one session's edit in two steps, 23 Nov 2026):
                # wait for the next change, settled for 10 s, and try again instead of leaving the app down.
                print('The app stopped with an error (above). It starts again by itself once scripts/ change.',
                      flush=True)
                seen = code_stamp()
                while code_stamp() <= seen or time.time() - code_stamp() < 10:
                    time.sleep(2)
                code = RESTART
        except KeyboardInterrupt:
            return 0
        if code != RESTART:
            return code
        print('scripts/ changed: the app starts again', flush=True)
        if '--no-browser' not in args:
            args = [*args, '--no-browser']   # the page is open already


def exit_with_parent(ppid):
    """The supervisor was closed or killed: stop too, so no orphan keeps the port."""
    import time
    if os.name == 'nt':
        import ctypes
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = ctypes.c_void_p
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        h = k.OpenProcess(0x00100000, False, ppid)   # SYNCHRONIZE: enough to wait for it
        if not h:
            os._exit(0)                                # already gone
        k.WaitForSingleObject(h, 0xFFFFFFFF)
    else:
        while os.getppid() == ppid:
            time.sleep(2)
    os._exit(0)


def code_stamp():
    """Newest change to the server's own code: this file and the modules it imports."""
    return max((p.stat().st_mtime for p in (ROOT / 'scripts').glob('*.py')), default=0)


class AppServer(ThreadingHTTPServer):
    """The port is ours alone. Python's server asks for SO_REUSEADDR, which on Windows lets a second server listen on
    a port that is already taken, without any error: two apps then split the requests and "next free port" never
    happens (seen 23 Nov 2026). On Windows: exclusive use instead; elsewhere SO_REUSEADDR is harmless."""
    if os.name == 'nt':
        allow_reuse_address = False

        def server_bind(self):
            import socket
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()


def restart_when_idle(httpd, state_file):
    """Code changed (Claude or Codex edited scripts/): once nothing is running, hand the last runs to the next
    server and stop with RESTART. A run, a queued run starting, a distil round or a request being answered
    holds the restart; the queue and the distil round are files, so they carry over by themselves."""
    import time
    born = BORN[0] = code_stamp()
    while True:
        time.sleep(5)
        now = code_stamp()
        if now <= born or time.time() - now < 10:   # unchanged, or still being edited
            continue
        with _QLOCK:
            if CUR.get('running') or (current_run() or {}).get('running') or _AUTO.locked():
                continue
            RESTARTING.set()
            state_file.write_text(json.dumps({'port': httpd.server_address[1], 'cur': CUR, 'recent': RECENT},
                                             ensure_ascii=False, default=str), encoding='utf-8')
        while ACTIVE[0]:                 # let open requests finish (a Codex text job can take minutes)
            time.sleep(0.2)
        httpd.shutdown()                 # main() then waits for any last request and exits with RESTART
        return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8777)
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    ap.add_argument('--dry-run', action='store_true',
                    help='every run and text job is a dry run: no Codex call, no allowance spent')
    a = ap.parse_args()
    parent = os.environ.get('TASTE_APP_PARENT')
    if not parent:
        sys.exit(supervise())
    threading.Thread(target=exit_with_parent, args=(int(parent),), daemon=True).start()
    global DRY_RUN
    DRY_RUN = a.dry_run
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    # After a restart: the same port as before, and the last runs, so the page reports them as if nothing happened.
    state_file = BASE / f'.app-restart-{a.port}.json'
    state = read_json(state_file, {}) if state_file.exists() else {}
    state_file.unlink(missing_ok=True)
    CUR.update(state.get('cur') or {})
    RECENT[:] = state.get('recent') or []
    import time
    httpd = None
    for _ in range(25 if state.get('port') else 0):   # the old server has just let go of it
        try:
            httpd = AppServer(('127.0.0.1', state['port']), Handler)
            port = state['port']
            break
        except OSError:
            time.sleep(0.2)
    for port in ([] if httpd else range(a.port, a.port + 10)):  # next free port if this one is taken
        try:
            httpd = AppServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    if not httpd:
        sys.exit(f'no free port between {a.port} and {a.port + 9}')
    migrate_drafts()
    global QUEUE_FILE, DISTIL_RUN
    if DRY_RUN:   # its own queue and distil round: a dry-run item must never become real after a restart
        QUEUE_FILE = BASE / 'app-queue.dry.json'
        DISTIL_RUN = BASE / 'distil-run.dry.json'
    QUEUE[:] = [q for q in read_json(QUEUE_FILE, []) if isinstance(q, dict) and q.get('id')]
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=maybe_auto_distil, daemon=True).start()
    threading.Thread(target=restart_when_idle, args=(httpd, state_file), daemon=True).start()
    url = f'http://127.0.0.1:{port}/'
    print(f'taste app on {url}  (Ctrl+C to stop)' + ('  [dry run: runs spend nothing]' if DRY_RUN else ''),
          flush=True)
    if not a.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')
        return
    while ACTIVE[0]:                     # a request that slipped in just before the stop
        time.sleep(0.2)
    httpd.server_close()
    sys.exit(RESTART)


if __name__ == '__main__':
    main()
