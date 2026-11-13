"""Local web app to view, mark and save ratings for the images made through Codex.

Usage (from the project root):
  .venv/Scripts/python -I scripts/app.py              # starts on http://127.0.0.1:8765 and opens the browser
  .venv/Scripts/python -I scripts/app.py --no-browser --port 8770

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
  .thumbs/             small JPEG copies for the grid (written, safe to delete)
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
        status = 'rated' if s else 'ignored' if name in ignored else 'draft' if name in drafts else 'new'
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

    # -- API handlers: return plain data, the plumbing turns it into JSON

    def get_batches(self):
        return {'batches': list_batches()}

    def get_batch(self, batch=''):
        if not is_batch(batch):
            raise ApiError(404, f'no batch "{batch}"')
        images = batch_images(batch)
        return {**summary(batch, images), 'items': images}

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
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    a = ap.parse_args()
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
    print(f'taste app on {url}  (Ctrl+C to stop)')
    if not a.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')


if __name__ == '__main__':
    main()
