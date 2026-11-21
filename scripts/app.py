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

Files this server reads or writes (all in generated/codex/)
  <batch>/*.png        images (read), seed.* is the seed of a variations batch
  runs.csv             one row per generated image (read): style, change, seed, prompt
  ratings.csv          saved ratings (read; appended through rate.append_ratings)
  app-drafts.json      marks not saved yet, so they survive closing the tab (written)
  app-ignored.json     images hidden from the grid and left out of ratings (written)
  .thumbs/             small JPEG copies for the grid (written, safe to delete)
  distil-state.json    where the last distil stopped (read only: --mark stays a command-line step)
  <batch>/run.json     what a run started here was, where it came from and how it was set (written)
  app-queue.json       runs waiting (written; app-queue.dry.json with --dry-run, so a test never runs for real)
  claude-notes.json    notes for Claude Code (written here, answered with scripts/notes.py)
  .progress.json       live progress of the running run (read; written by the run scripts)

Runs (21 Nov 2026): one queue, one image run at a time. New runs (batch.py), single images, remixes and retries
(run_list.py) and variations (variations.py) are queued from the page; a run started from chat holds the queue
until it ends. Codex also writes subjects and rewrites prompts (codex_text.py, read-only text jobs).

Draft, then save: marks are drafts until "Save ratings" appends them to ratings.csv in one go.
Saved ratings are read-only here, because distil.py remembers its place by row count.
"""
import argparse, csv, json, os, sys, threading, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import rate  # noqa: E402  (shared paths and the one writer of ratings.csv)

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
    """ratings.csv as {(batch, name): row}. A later row for the same image wins."""
    if not rate.RATINGS.exists():
        return {}
    return {(r['batch'], r['name']): r for r in csv.DictReader(open(rate.RATINGS, encoding='utf-8'))}


# ---------------------------------------------------------------- batches and images

def is_batch(name):
    """A batch is a folder directly inside generated/codex/ (never '..', never a hidden folder)."""
    return bool(name) and not name.startswith('.') and '/' not in name and '\\' not in name \
        and (BASE / name).is_dir()


def seed_file(batch):
    seeds = sorted(p.name for p in (BASE / batch).glob('seed.*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'))
    return seeds[0] if seeds else None


def batch_images(batch):
    """Every image of a batch with what the app shows about it.
    status: 'rated' (saved, read-only) > 'ignored' > 'draft' (marked, not saved) > 'new'."""
    runs = rate.batch_runs(batch)
    saved = saved_ratings()
    drafts = read_json(DRAFTS, {}).get(batch, {})
    ignored = set(read_json(IGNORED, {}).get(batch, []))
    out = []
    for i, name in enumerate(rate.batch_images(batch), 1):
        run = runs.get(name, {})
        s = saved.get((batch, name))
        marked = (drafts.get(name) or {}).get('rating')  # a "why" alone is kept, but is not a draft yet
        status = 'rated' if s else 'ignored' if name in ignored else 'draft' if marked else 'new'
        out.append({
            'name': name, 'file': f'{name}.png', 'number': i, 'status': status,
            'mtime': int((BASE / batch / f'{name}.png').stat().st_mtime),
            'style': run.get('style', ''), 'mode': run.get('mode', ''), 'change': run.get('change', ''),
            'seed': run.get('seed', ''), 'prompt': run.get('prompt', ''),
            'width': run.get('width', ''), 'height': run.get('height', ''),
            'date': run.get('date', ''), 'time': run.get('time', ''), 'seconds': run.get('seconds', ''),
            'draft': drafts.get(name),
            'saved': {'rating': s['rating'], 'why': s['why'], 'date': s['date']} if s else None,
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
    out = [summary(b, batch_images(b)) for b in names]
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
WEEK_BUDGET = 200         # README "Allowance": 10 % of the week for images = about 200 images (remeasured 20 Nov 2026)
DRY_RUN = False           # --dry-run: every run and text job is a dry run (no Codex, no allowance)
QUEUE_FILE = BASE / 'app-queue.json'    # runs waiting: a restart of the app keeps them
NOTES = BASE / 'claude-notes.json'      # notes for Claude Code (scripts/notes.py reads and answers them)
SPECS = BASE / '.app'                   # files of dry runs (subjects, jobs), deleted when the run ends
QUEUE = []                # specs waiting, first = next
CUR = {}                  # the run the app started last (running or finished); read by GET /api/job
PROC = {}                 # its process: {'p': Popen}
RECENT = []               # the last finished app runs, newest last: the page reports each one once, even when
                          # the next queued run starts at once
_QLOCK = threading.Lock()
_WAKE = threading.Event()
_guess = None             # nearest.model, loaded on first use (a few seconds: sklearn + 1,000 thumbnails)
_GUESS_LOCK = threading.Lock()  # its own lock: loading it must not hold up marking
_lineage = {'key': None, 'map': {}}


def allowance():
    """Codex usage now (scripts/codex_run.py read: from Codex's own session log, never typed)
    plus how many images were made in the last 7 days (runs.csv)."""
    import datetime, subprocess
    r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'read'],
                       capture_output=True, text=True, encoding='utf-8', timeout=60)
    now = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip().startswith('{') else None
    since = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    week = 0
    if rate.RUNS.exists():
        week = sum(1 for row in csv.DictReader(open(rate.RUNS, encoding='utf-8'))
                   if row['ok'] == 'yes' and row['date'] >= since)
    queued = sum(len(s['expected']) for s in QUEUE)
    return {'now': now, 'unknown_reason': None if now else (r.stderr or r.stdout).strip()[-300:],
            'week_images': week, 'week_budget': WEEK_BUDGET, 'dry_run': DRY_RUN, 'queued_images': queued}


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
    return {'top': [{'style': s, 'distance': d} for s, d in top], 'far': far}


def slugify(text, fallback='run'):
    return '-'.join(''.join(c if c.isalnum() else ' ' for c in text.lower()).split())[:32].strip('-') or fallback


def free_slug(stem):
    """Folders are generated/codex/<today>-<slug>/; never reuse one (it would overwrite), nor one a queued
    run has already reserved."""
    import datetime
    base = slugify(stem, 'variations')[:24]
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


def failed_images(batch, have):
    """runs.csv rows of this batch that made no image (blocked, timed out), latest try per name."""
    if not rate.RUNS.exists():
        return []
    rows = {}
    for r in csv.DictReader(open(rate.RUNS, encoding='utf-8')):
        if r['batch'] == batch:
            rows[r['name']] = r
    return [{'name': n, 'style': r['style'], 'change': r['change'], 'mode': r['mode'], 'prompt': r['prompt'],
             'date': r['date'], 'time': r['time'], 'seed': r['seed']}
            for n, r in sorted(rows.items()) if r['ok'] != 'yes' and n not in have]


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


def worker():
    """Starts the next queued run when nothing is running (neither from the app nor from chat)."""
    import time
    while True:
        _WAKE.wait(3)
        _WAKE.clear()
        with _QLOCK:
            # a dry run spends nothing and writes no progress file: it never waits for a real run
            if CUR.get('running') or not QUEUE or (not DRY_RUN and (chat_run() or {}).get('running')):
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
        _WAKE.set()


def launch(spec):
    import shutil, subprocess, time
    if spec['kind'] == 'variations' and not DRY_RUN:   # variations.py names its folder by today's date
        spec['slug'], spec['batch'] = free_slug(spec['slug'])
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
                                 '--hint', spec['hints'].get(st, ''))['subjects']
            if CUR.get('cancel'):
                raise RuntimeError('stopped before the first image')
            subjects[st] = have
            for s in have:
                say(f'subject {st}: {s}')
        spec['subjects'] = CUR['subjects'] = subjects
        write_json(folder / 'subjects.json', subjects)
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'batch.py'), '--out', str(folder), '--subjects', str(folder / 'subjects.json'),
               '--styles', ','.join(spec['styles']), '--n', str(spec['n']), '--wildcards', str(spec['wildcards']),
               '--ratio', spec['ratio']]
    elif spec['kind'] in ('remix', 'single', 'retry'):
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
    else:
        rec = {k: spec.get(k) for k in ('kind', 'title', 'source', 'styles', 'n', 'subjects', 'hints', 'ratio',
                                         'wildcards', 'style', 'changes', 'subject', 'note', 'change', 'keep')
               if spec.get(k) not in (None, '', [], {})}
        rec.update(started=time.strftime('%Y-%m-%d %H:%M'), by='web app')
        write_json(folder / 'run.json', rec)
    if CUR.get('cancel'):
        raise RuntimeError('stopped before the first image')
    CUR['phase'] = 'Making images' if not DRY_RUN else 'Dry run: printing the prompts'
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    PROC['p'] = proc
    for line in proc.stdout:
        CUR['log'] = (CUR['log'] + [line.rstrip()])[-200:]
    CUR.update(running=False, returncode=proc.wait(), finished=time.time(), phase='')
    PROC.clear()
    if DRY_RUN:
        shutil.rmtree(folder, ignore_errors=True)
    elif spec['kind'] == 'batch':
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
        return {'running': False, 'queue': queue, 'recent': list(RECENT)}
    folder = BASE / run['batch']
    made = [n for n in run['expected'] if (folder / f'{n}.png').exists()]
    return {**run, 'exists': is_batch(run['batch']), 'made': made, 'queue': queue, 'recent': list(RECENT)}


# -- run specs: what each kind of run needs, checked before it joins the queue

KEEPABLE = ('subject', 'palette', 'composition', 'light', 'medium')


def spec_batch(body, preview=False):
    """{styles: [..], n: 1-8, subjects: {style: [..]}, hints: {style: '..'}, ratio, wildcards: 0|1, name}"""
    styles = list(dict.fromkeys(s for s in body.get('styles') or [] if isinstance(s, str)))
    if not styles:
        raise ApiError(400, 'pick at least one style')
    info = {s: style_file(s) for s in styles}
    n = int(body.get('n') or 4)
    if not 1 <= n <= 8:
        raise ApiError(400, 'images per style: 1 to 8')
    ratio = body.get('ratio') or 'mixed'
    if ratio not in RATIO_CHOICES:
        raise ApiError(400, 'ratio: mixed, wide, portrait or square')
    wildcards = 1 if body.get('wildcards') and n > 1 else 0
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
    _, batch = free_slug(clean(body.get('name'), 60) or '-'.join(styles[:2]))
    return {'kind': 'batch', 'title': title, 'batch': batch, 'styles': styles, 'n': n, 'ratio': ratio,
            'wildcards': wildcards, 'subjects': subjects, 'hints': hints, 'placeholders': placeholders,
            'expected': [f'{s}-{i + 1}' for s in styles for i in range(n)]}


def spec_single(body):
    """One image (or a few) from a style and a subject I write: {style, subject, ratio, n: 1-4}."""
    style = str(body.get('style', ''))
    st = style_file(style)
    subject = clean(body.get('subject'))
    if not subject:
        raise ApiError(400, 'write a subject')
    ratio = body.get('ratio') or 'wide'
    if ratio not in RATIO_CHOICES[1:]:
        raise ApiError(400, 'ratio: wide, portrait or square')
    n = max(1, min(4, int(body.get('n') or 1)))
    _, batch = free_slug(subject[:24])
    stem = '-'.join(slugify(subject, 'image').split('-')[:3])   # first words, never cut mid-word
    jobs = [{'name': f'{stem}-{i}', 'style': style, 'subject': subject, 'ratio': ratio, 'mode': 'text'}
            for i in range(1, n + 1)]
    return {'kind': 'single', 'title': f'{st.get("name", style)}: {subject[:50]}', 'batch': batch, 'jobs': jobs,
            'styles': [style], 'n': n, 'subject': subject, 'ratio': ratio, 'expected': [j['name'] for j in jobs]}


def spec_remix(body):
    """A new image from one I made, with a rewritten prompt: {batch, file, prompt, change, keep, ref: bool, n: 1-4}."""
    src = source_image(str(body.get('batch', '')), str(body.get('file', '')))
    prompt = clean(body.get('prompt'), 4000)
    if not prompt:
        raise ApiError(400, 'the prompt is empty')
    change = clean(body.get('change'), 200)
    n = max(1, min(4, int(body.get('n') or 1)))
    style = rate.batch_runs(src.parent.name).get(src.stem, {}).get('style', '')
    _, batch = free_slug(f'{src.stem}-remix')
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
    if row['seed']:   # it had a reference image: the batch's seed copy, else the source named in run.json
        if seed_file(batch):
            ref = str(BASE / batch / seed_file(batch))
        elif (run_record(batch) or {}).get('source'):
            src = run_record(batch)['source']
            if (BASE / src['batch'] / src['file']).is_file():
                ref = str(BASE / src['batch'] / src['file'])
    job = {'name': name, 'prompt': row['prompt'], 'style': row['style'], 'mode': row['mode'] or 'test',
           'change': row['change'], 'ref': ref}
    return {'kind': 'retry', 'title': f'Retry {name}', 'batch': batch, 'jobs': [job],
            'styles': [row['style']] if row['style'] else [], 'n': 1, 'expected': [name]}


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
    slug, batch = free_slug(stem)
    return {'kind': 'variations', 'title': f'Variations of {src.stem}', 'batch': batch, 'slug': slug,
            'source': {'batch': src.parent.name, 'file': src.name}, 'style': style, 'styles': [style],
            'changes': changes, 'subject': clean(body.get('subject')), 'note': clean(body.get('note')),
            'n': len(changes), 'expected': [f'{i}-{c}' for i, c in enumerate(changes, 1)]}


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
        ('PUT', 'api/draft'): 'put_draft',
        ('POST', 'api/ignore'): 'post_ignore',
        ('POST', 'api/save'): 'post_save',
        ('GET', 'api/allowance'): 'get_allowance',
        ('POST', 'api/guess'): 'post_guess',
        ('POST', 'api/variations'): 'post_variations',
        ('POST', 'api/run'): 'post_run',
        ('POST', 'api/preview'): 'post_preview',
        ('POST', 'api/stop'): 'post_stop',
        ('POST', 'api/queue/cancel'): 'post_queue_cancel',
        ('POST', 'api/text/subjects'): 'post_text_subjects',
        ('POST', 'api/text/rewrite'): 'post_text_rewrite',
        ('POST', 'api/reveal'): 'post_reveal',
        ('GET', 'api/notes'): 'get_notes',
        ('POST', 'api/notes/delete'): 'post_notes_delete',
        ('POST', 'api/notes'): 'post_notes',
        ('GET', 'api/job'): 'get_job',
        ('GET', 'api/overview'): 'get_overview',
        ('GET', 'api/distil'): 'get_distil',
        ('GET', 'api/gallery'): 'get_gallery',
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

    def read_body(self):
        """JSON body of a write. Writes need the page's own header: a page on another site can't add it
        without a CORS preflight, which this server never answers, so only the taste page can write."""
        if self.headers.get('X-Taste-App') != '1' or 'application/json' not in (self.headers.get('Content-Type') or ''):
            raise ApiError(403, 'writes only from the taste page')
        n = int(self.headers.get('Content-Length') or 0)
        if n > 100_000:
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
            raise ApiError(409, 'this rating is saved already; saved ratings are read-only')
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
        try:
            self.check_host()
            path = unquote(urlparse(self.path).path).strip('/')
            parts = path.split('/')
            # 1. API
            for (m, prefix), fn in self.ROUTES.items():
                if m == method and (path == prefix or path.startswith(prefix + '/')):
                    args = [p for p in path[len(prefix):].split('/') if p]
                    return self.send(200, getattr(self, fn)(*args))
            if method != 'GET':
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
        return {**summary(batch, images), 'items': images, 'run': run_record(batch), 'parent': lin.get(batch),
                'children': children, 'failed': failed_images(batch, {im['name'] for im in images}),
                'path': str(BASE / batch), 'rel_path': f'generated/codex/{batch}'}

    def put_draft(self):
        """Set or clear one draft: {batch, name, rating: keep (up)|no (down)|null, why}."""
        body = self.read_body()
        batch, name = self.image_from(body)
        rating, why = body.get('rating'), ' '.join(str(body.get('why') or '').split())[:300]
        if rating not in (None, *rate.RATINGS_ALLOWED):
            raise ApiError(400, 'rating must be keep (up), no (down) or null')
        with LOCK:
            drafts = read_json(DRAFTS, {})
            mine = drafts.setdefault(batch, {})
            if rating is None and not why:
                mine.pop(name, None)
            else:
                mine[name] = {'rating': rating, 'why': why}
            if not mine:
                drafts.pop(batch)
            write_json(DRAFTS, drafts)
        return {'ok': True}

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
        """Queue one run. kind: batch | single | remix | retry | variations (see the spec_* helpers)."""
        body = body or self.read_body()
        make = {'batch': spec_batch, 'single': spec_single, 'remix': spec_remix, 'retry': spec_retry,
                'variations': spec_variations}.get(body.get('kind'))
        if not make:
            raise ApiError(400, f'unknown kind "{body.get("kind")}"')
        with _QLOCK:
            spec = make(body)
        spec.pop('placeholders', None)
        return enqueue(spec)

    def post_preview(self):
        """The prompts a batch would use, without running Codex (batch.py --dry-run). Missing subjects are
        filled with the style's own examples, marked, so the preview never spends anything."""
        import subprocess, tempfile
        spec = spec_batch(self.read_body(), preview=True)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'subjects.json'
            write_json(f, spec['subjects'])
            r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'batch.py'), '--out', str(Path(tmp) / 'out'),
                                '--subjects', str(f), '--styles', ','.join(spec['styles']), '--n', str(spec['n']),
                                '--wildcards', str(spec['wildcards']), '--ratio', spec['ratio'], '--dry-run'],
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

    def post_text_subjects(self):
        """Codex writes fresh subjects for one style: {style, n, hint}. About 15 s; spends a little allowance."""
        body = self.read_body()
        style_file(str(body.get('style', '')))
        n = max(1, min(12, int(body.get('n') or 4)))
        return text_job('subjects', '--style', body['style'], '--n', str(n), '--hint', clean(body.get('hint'), 200))

    def post_text_rewrite(self):
        """Codex rewrites an image prompt: {prompt, change, keep: [...]}. About 15 s."""
        body = self.read_body()
        prompt, change = clean(body.get('prompt'), 4000), clean(body.get('change'), 400)
        if not prompt or not change:
            raise ApiError(400, 'give the prompt and what should change')
        keep = ', '.join(k for k in body.get('keep') or [] if k in KEEPABLE)
        return text_job('rewrite', '--prompt', prompt, '--change', change, '--keep', keep)

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
        for i, r in enumerate(rows):
            if r['rating'] in rate.RATINGS_SEEN:
                per[r['style'] or '(no style)']['all'][r['rating']] += 1
                if i >= done:
                    per[r['style'] or '(no style)']['since'][r['rating']] += 1
        # Unsaved = what "Save ratings" would write: marked, not ignored, not saved already.
        unsaved = {b: sum(1 for im in batch_images(b) if im['status'] == 'draft')
                   for b in read_json(DRAFTS, {}) if is_batch(b)}
        return {'styles': per, 'total': len(rows), 'since_last': max(0, len(rows) - done), 'due': rate.DUE,
                'marked': state.get('marked'),
                'unsaved': {b: n for b, n in unsaved.items() if n},
                'ignored': sum(len(v) for v in read_json(IGNORED, {}).values())}

    def get_distil(self):
        """What distil.py prints now. Read-only: --mark is never run from here."""
        import subprocess
        r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'distil.py')], cwd=ROOT, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=60)
        return {'output': (r.stdout + r.stderr).strip(), 'returncode': r.returncode}

    def get_styles(self):
        """The 14 styles, whole: name, palette, description, light, composition, medium, mood, detail,
        avoid, subjects and uses (the picker and labels use the first three, the Taste page all of it)."""
        out = {}
        for p in sorted((ROOT / 'taste' / 'styles').glob('*.json')):
            s = read_json(p, {})
            out[p.stem] = {**s, 'name': s.get('name', p.stem), 'palette': s.get('palette', [])[:7],
                           'description': s.get('description', '')}
        return {'styles': out}

    def get_gallery(self):
        """Every image of every batch, newest first, ignored ones left out. Read-only: the Gallery and
        Taste pages show these; marking stays in the batch view. Seeds are left out (rate.batch_images
        skips them), so wallpapers by other people never show here."""
        out = []
        names = [p.name for p in BASE.iterdir() if is_batch(p.name)] if BASE.exists() else []
        for b in names:
            for im in batch_images(b):
                if im['status'] == 'ignored':
                    continue
                s = im['saved']
                out.append({'batch': b, 'name': im['name'], 'file': im['file'], 'mtime': im['mtime'],
                            'style': im['style'], 'mode': im['mode'], 'change': im['change'],
                            'prompt': im['prompt'], 'width': im['width'], 'height': im['height'],
                            'date': im['date'] or b[:10],
                            'rating': s['rating'] if s else None, 'why': s['why'] if s else ''})
        out.sort(key=lambda x: x['mtime'], reverse=True)
        return {'images': out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8777)
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    ap.add_argument('--dry-run', action='store_true',
                    help='every run and text job is a dry run: no Codex call, no allowance spent')
    a = ap.parse_args()
    global DRY_RUN
    DRY_RUN = a.dry_run
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    for port in range(a.port, a.port + 10):  # next free port if this one is taken
        try:
            httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit(f'no free port between {a.port} and {a.port + 9}')
    global QUEUE_FILE
    if DRY_RUN:   # its own queue: a dry-run item must never become a real run after a restart
        QUEUE_FILE = BASE / 'app-queue.dry.json'
    QUEUE[:] = [q for q in read_json(QUEUE_FILE, []) if isinstance(q, dict) and q.get('id')]
    threading.Thread(target=worker, daemon=True).start()
    url = f'http://127.0.0.1:{port}/'
    print(f'taste app on {url}  (Ctrl+C to stop)' + ('  [dry run: runs spend nothing]' if DRY_RUN else ''))
    if not a.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')


if __name__ == '__main__':
    main()
