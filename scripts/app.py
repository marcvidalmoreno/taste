"""Local web app to view, mark and save ratings for the images made through Codex.

Usage (from the project root):
  .venv/Scripts/python -I scripts/app.py              # starts on http://127.0.0.1:8777 and opens the browser
  .venv/Scripts/python -I scripts/app.py --no-browser --port 8780

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
    count = lambda st: sum(1 for im in images if im['status'] == st)  # noqa: E731
    return {'batch': batch, 'date': batch[:10], 'images': len(images),
            'to_rate': count('new') + count('draft'), 'drafts': count('draft'),
            'rated': count('rated'), 'ignored': count('ignored'),
            'newest': max((im['mtime'] for im in images), default=int((BASE / batch).stat().st_mtime)),
            'preview': [im['file'] for im in images if im['status'] != 'ignored'][:4],
            'seed': seed_file(batch)}


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


# ---------------------------------------------------------------- variations: one job at a time

PY = sys.executable
CHANGES = ['palette', 'subject', 'composition', 'mood']   # the order scripts/variations.py makes them in
WEEK_BUDGET = 40          # README "Allowance": 10 % of the week for images = at least ~40 images
DRY_RUN = False           # --dry-run: jobs run variations.py --dry-run (no Codex, no allowance)
JOB = {'running': False}  # the one variation job; read by GET /api/job
_guess = None             # nearest.model, loaded on first use (a few seconds: sklearn + 1,000 thumbnails)
_GUESS_LOCK = threading.Lock()  # its own lock: loading it must not hold up marking


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
    return {'now': now, 'unknown_reason': None if now else (r.stderr or r.stdout).strip()[-300:],
            'week_images': week, 'week_budget': WEEK_BUDGET, 'dry_run': DRY_RUN}


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


def free_slug(stem):
    """variations.py writes to generated/codex/<today>-<slug>/; never reuse a folder (it would overwrite)."""
    import datetime
    base = ''.join(c if c.isalnum() else '-' for c in stem.lower()).strip('-')[:24] or 'variations'
    day, slug, i = datetime.date.today().isoformat(), base, 2
    while (BASE / f'{day}-{slug}').exists():
        slug, i = f'{base}-{i}', i + 1
    return slug, f'{day}-{slug}'


def start_job(src, style, subject, n):
    import subprocess, time
    slug, batch = free_slug(src.stem if src.stem != 'seed' else src.parent.name[11:] + '-seed')
    cmd = [PY, '-I', str(ROOT / 'scripts' / 'variations.py'), str(src), '--style', style, '--n', str(n), '--slug', slug]
    if subject:
        cmd += ['--subject', subject]
    if DRY_RUN:
        cmd.append('--dry-run')
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    JOB.clear()
    JOB.update(running=True, batch=batch, source={'batch': src.parent.name, 'file': src.name}, style=style, n=n,
               expected=[f'{i}-{c}' for i, c in enumerate(CHANGES[:n], 1)], started=time.time(),
               finished=None, returncode=None, log=[], dry_run=DRY_RUN)

    def follow():  # read the script's output as it comes, keep the last lines for the page
        for line in proc.stdout:
            JOB['log'] = (JOB['log'] + [line.rstrip()])[-80:]
        JOB.update(running=False, returncode=proc.wait(), finished=time.time())
    threading.Thread(target=follow, daemon=True).start()


def job_state():
    if 'batch' not in JOB:
        return {'running': False}
    folder = BASE / JOB['batch']
    made = [n for n in JOB['expected'] if (folder / f'{n}.png').exists()]
    return {**JOB, 'exists': folder.is_dir(), 'made': made}


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
        ('GET', 'api/job'): 'get_job',
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
        return {**summary(batch, images), 'items': images}

    def put_draft(self):
        """Set or clear one draft: {batch, name, rating: keep|almost|no|null, why}."""
        body = self.read_body()
        batch, name = self.image_from(body)
        rating, why = body.get('rating'), ' '.join(str(body.get('why') or '').split())[:300]
        if rating not in (None, *rate.RATINGS_ALLOWED):
            raise ApiError(400, 'rating must be keep, almost, no or null')
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
        """Start variations.py on one image: {batch, file, style, subject, n}. Spends Codex allowance
        (unless --dry-run), so the page only calls this after Marc confirmed the style and the cost."""
        body = self.read_body()
        src = source_image(str(body.get('batch', '')), str(body.get('file', '')))
        style, n = str(body.get('style', '')), body.get('n', 3)
        subject = ' '.join(str(body.get('subject') or '').split())[:200]
        if not (ROOT / 'taste' / 'styles' / f'{style}.json').exists():
            raise ApiError(400, f'unknown style "{style}"')
        if n not in (3, 4):
            raise ApiError(400, 'n must be 3 or 4')
        with LOCK:
            if JOB.get('running'):
                raise ApiError(409, 'a variation job is already running: one at a time')
            start_job(src, style, subject, n)
        return job_state()

    def get_job(self):
        return job_state()

    def get_styles(self):
        """The 14 styles: key, display name and palette (for the style picker and labels)."""
        out = {}
        for p in sorted((ROOT / 'taste' / 'styles').glob('*.json')):
            s = read_json(p, {})
            out[p.stem] = {'name': s.get('name', p.stem), 'palette': s.get('palette', [])[:7],
                           'description': s.get('description', '')}
        return {'styles': out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8777)
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    ap.add_argument('--dry-run', action='store_true',
                    help='variation jobs run variations.py --dry-run: no Codex call, no allowance spent')
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
    url = f'http://127.0.0.1:{port}/'
    print(f'taste app on {url}  (Ctrl+C to stop)' + ('  [dry run: variations spend nothing]' if DRY_RUN else ''))
    if not a.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')


if __name__ == '__main__':
    main()
