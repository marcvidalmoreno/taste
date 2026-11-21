"""Live progress of an image run, for the web app (20 Nov 2026).

batch.py, variations.py and a lone codex_run.py gen write generated/codex/.progress.json (git-ignored) as
they go: which images are expected, which one is being made now, what failed, and the last log lines.
scripts/app.py reads it in GET /api/job, so the header chip and the batch grid show runs started from chat
too, not only the ones started from the page. A heartbeat every 10 s tells the app the run is still alive;
a run killed half-way stops beating and the app shows it as stopped.

Child processes get TASTE_PROGRESS=1, so codex_run.py doesn't overwrite its parent's file.
"""
import json, os, threading, time
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / 'generated' / 'codex' / '.progress.json'
CHILD_ENV = {**os.environ, 'TASTE_PROGRESS': '1'}


def is_child():
    return os.environ.get('TASTE_PROGRESS') == '1'


def clock(secs):
    secs = int(secs)
    return f'{secs // 60}:{secs % 60:02d}'


class Progress:
    def __init__(self, out, expected, kind):
        now = time.time()
        self.d = {'kind': kind, 'batch': Path(out).name, 'expected': list(expected), 'failed': [], 'pid': os.getpid(),
                  'current': None, 'started': now, 'updated': now, 'finished': None, 'log': []}
        self.lock = threading.Lock()
        self.write()
        threading.Thread(target=self._beat, daemon=True).start()

    def _beat(self):
        while self.d['finished'] is None:
            time.sleep(10)
            self.write()

    def write(self):
        """Best effort: progress must never break a run (the app may be reading the file right now)."""
        with self.lock:
            self.d['updated'] = time.time()
            try:
                FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = FILE.with_name(f'.progress.{os.getpid()}.tmp')
                tmp.write_text(json.dumps(self.d, ensure_ascii=False), encoding='utf-8')
                for _ in range(5):
                    try:
                        os.replace(tmp, FILE)
                        break
                    except PermissionError:
                        time.sleep(0.1)
            except OSError:
                pass

    def line(self, text):
        self.d['log'] = (self.d['log'] + [f'{time.strftime("%H:%M:%S")}  {text}'])[-80:]
        self.write()

    def begin(self, name, subject=''):
        self.d['current'] = {'name': name, 'subject': subject, 'since': time.time()}
        self.line(f'making {name}' + (f': {subject}' if subject else ''))

    def ok(self, name):
        took = time.time() - (self.d['current'] or {}).get('since', time.time())
        self.d['current'] = None
        self.line(f'ok {name} ({clock(took)})')

    def fail(self, name, why=''):
        self.d['current'] = None
        self.d['failed'].append(name)
        self.line(f'FAILED {name}' + (f': {why}' if why else ''))

    def end(self, text=''):
        if text:
            self.line(text)
        self.d['current'] = None
        self.d['finished'] = time.time()
        self.write()
