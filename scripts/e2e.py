"""Regression check for the web app: Playwright tests on a throwaway copy with fake data.

  .venv/Scripts/python -I scripts/e2e.py              # test the last commit (HEAD), about 1-2 minutes
  .venv/Scripts/python -I scripts/e2e.py --working    # test the files as they are now (use before committing)
  .venv/Scripts/python -I scripts/e2e.py --hook       # from post-commit: only when app/, scripts/ or tests/ changed;
                                                      # one run at a time; writes generated/e2e/last.json; mails
  .venv/Scripts/python -I scripts/e2e.py --serve      # make the copy, start it, print its address, wait (Enter / Ctrl+C)
  .venv/Scripts/python -I scripts/e2e.py --status     # what the SessionStart hook prints: nothing when the last check passed
  extra flags: --force (hook: skip the path filter) --no-mail --keep (keep the copy) --sabotage (break a JS module in
  the copy on purpose) --fake-route (add a page with no test to the copy) -k <pytest expression> -x

What it does: `git archive HEAD app scripts tests` into a temp folder, fake styles, pictures, runs and ratings
(tests/fixtures/make_fixtures.py), the app started there with --dry-run on a free port and a fake home folder, then
pytest. Marc's real generated/ and taste/ folders are never read or written, ComfyUI and Ollama are never started.
Output (git-ignored): generated/e2e/ (last.json from the hook, e2e.log, screenshots of failures per run).
"""
import datetime, hashlib, json, os, shutil, socket, subprocess, sys, tarfile, tempfile, time, io, re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'generated' / 'e2e'
LAST, LOG, LOCK, PENDING, RUNNING = OUT / 'last.json', OUT / 'e2e.log', OUT / '.lock', OUT / '.pending', OUT / 'running.json'
WATCHED = ('app/', 'scripts/', 'tests/')
MAIL = Path.home() / 'Claude' / 'setup' / 'scripts' / 'send-mail.mjs'   # Marc's mail helper, outside the repo
RATINGS = ROOT / 'generated' / 'codex' / 'ratings.csv'
LOCAL_PORTS = (8188, 11434)   # ComfyUI, Ollama: must never be started by this check


def say(msg):
    print(msg, flush=True)


def log(msg):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(f'{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n')


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, encoding='utf-8').stdout.strip()


def free_port(start=8795):
    for p in range(start, start + 100):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise SystemExit('no free port from 8795 up')


def port_open(p):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', p)) == 0


# ---------------------------------------------------------------- the copy

def snapshot(dest, working):
    """HEAD (git archive) or the files as they are now (tracked and new, not ignored) of app/, scripts/, tests/."""
    if working:
        files = git('ls-files', '-co', '--exclude-standard', '--', 'app', 'scripts', 'tests').splitlines()
        for f in files:
            src = ROOT / f
            if src.is_file():
                (dest / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest / f)
        return
    data = subprocess.run(['git', '-C', str(ROOT), 'archive', 'HEAD', 'app', 'scripts', 'tests'], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter='data')


def sabotage(dest):
    """Break one module in the copy: the page cannot start."""
    f = dest / 'app' / 'js' / 'batches.js'
    f.write_text(f.read_text(encoding='utf-8') + '\nthrow new Error("sabotage: e2e.py --sabotage");\n', encoding='utf-8')


def fake_route(dest):
    f = dest / 'app' / 'js' / 'main.js'
    t = f.read_text(encoding='utf-8')
    f.write_text(t.replace("const pages = {", "const pages = { zzfake: 'zzfake',", 1), encoding='utf-8')


def start_server(copy, port):
    """The app in dry-run mode inside the copy, with a fake home folder (so ~/.taste, ~/.codex are not the real ones)."""
    home = copy / 'home'
    home.mkdir(exist_ok=True)
    env = {**os.environ, 'USERPROFILE': str(home), 'HOME': str(home), 'PYTHONDONTWRITEBYTECODE': '1'}
    env.pop('TASTE_APP_PARENT', None)
    out = open(copy / 'server.log', 'w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, '-I', str(copy / 'scripts' / 'app.py'), '--dry-run', '--no-browser', '--port', str(port)],
                            cwd=copy, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    for _ in range(100):
        if proc.poll() is not None:
            break
        if port_open(port):
            return proc
        time.sleep(0.2)
    stop_server(proc)
    raise SystemExit('the app did not start in the copy:\n' + (copy / 'server.log').read_text(encoding='utf-8', errors='replace')[-1500:])


def stop_server(proc):
    subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)


# ---------------------------------------------------------------- one run

def run(working=False, sabotaged=False, fake=False, keep=False, pytest_args=(), serve=False, label=None):
    """Returns {'status', 'failing', 'duration', 'passed', 'total', 'out'}."""
    t0 = time.time()
    sha = git('rev-parse', '--short', 'HEAD')
    outdir = OUT / (label or ('working' if working else sha))
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True, exist_ok=True)
    before = (RATINGS.read_bytes() if RATINGS.exists() else b'')
    ports_before = {p: port_open(p) for p in LOCAL_PORTS}
    copy = Path(tempfile.mkdtemp(prefix='taste-e2e-'))
    proc = None
    try:
        snapshot(copy, working)
        sys.path.insert(0, str(copy / 'tests' / 'fixtures'))
        import make_fixtures
        make_fixtures.build(copy)
        if sabotaged:
            sabotage(copy)
        if fake:
            fake_route(copy)
        port = free_port()
        proc = start_server(copy, port)
        url = f'http://127.0.0.1:{port}'
        if serve:
            say(f'the copy is on {url}  (folder {copy}); press Enter or Ctrl+C to stop and delete it')
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            return {'status': 'pass', 'failing': [], 'duration': 0, 'passed': 0, 'total': 0, 'out': str(outdir)}
        xml = outdir / 'junit.xml'
        cmd = [sys.executable, '-I', '-m', 'pytest', 'tests/e2e', '-q', '-p', 'no:cacheprovider', f'--junitxml={xml}',
               '--screenshot=only-on-failure', f'--output={outdir / "screens"}', *pytest_args]
        env = {**os.environ, 'TASTE_E2E_URL': url, 'TASTE_E2E_COPY': str(copy), 'PYTHONDONTWRITEBYTECODE': '1'}
        r = subprocess.run(cmd, cwd=copy, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        (outdir / 'pytest.txt').write_text(r.stdout + r.stderr, encoding='utf-8')
        failing, passed, total = [], 0, 0
        if xml.exists():
            for tc in ET.parse(xml).getroot().iter('testcase'):
                total += 1
                bad = tc.find('failure') if tc.find('failure') is not None else tc.find('error')
                if bad is not None:
                    why = (bad.get('message') or '').splitlines()
                    failing.append({'test': f'{tc.get("classname", "").replace("tests.e2e.", "")}::{tc.get("name")}'.lstrip(':'),
                                    'why': (why[0] if why else '')[:200]})
                elif tc.find('skipped') is None:
                    passed += 1
        status = 'pass' if r.returncode == 0 and not failing else 'fail'
        if status == 'fail' and not failing:   # pytest itself broke (no tests collected, import error…)
            failing.append({'test': 'pytest', 'why': (r.stdout + r.stderr).strip().splitlines()[-1][:200] if (r.stdout + r.stderr).strip() else 'no output'})
        shutil.copy2(copy / 'server.log', outdir / 'server.log') if (copy / 'server.log').exists() else None
        return {'status': status, 'failing': failing, 'duration': round(time.time() - t0), 'passed': passed, 'total': total, 'out': str(outdir)}
    finally:
        if proc:
            stop_server(proc)
        if sys.path and sys.path[0].endswith('fixtures'):
            sys.path.pop(0)
        if not keep:
            time.sleep(0.5)
            shutil.rmtree(copy, ignore_errors=True)
        after = (RATINGS.read_bytes() if RATINGS.exists() else b'')
        if hashlib.sha256(before).digest() != hashlib.sha256(after).digest():
            log('note: generated/codex/ratings.csv changed during the run (a mark made in the real app, not by this check)')
        for p, was in ports_before.items():
            if not was and port_open(p):
                log(f'WARNING: something now answers on 127.0.0.1:{p} that did not before the run')


def summary(res, what):
    line = f'e2e {res["status"].upper()}: {res["passed"]} of {res["total"]} tests passed in {res["duration"]} s ({what})'
    if res['failing']:
        line += '\nfailing:\n' + '\n'.join(f'  - {f["test"]}: {f["why"]}' for f in res['failing'])
    return line


# ---------------------------------------------------------------- the hook: filter, one at a time, report

def mail(subject, body, tag):
    OUT.mkdir(parents=True, exist_ok=True)
    draft = OUT / f'mail-{tag}.md'
    draft.write_text(f'Subject: {subject}\n\n{body}\n', encoding='utf-8')
    r = subprocess.run(['node', str(MAIL), str(draft)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    log(f'mail "{subject}": {(r.stdout + r.stderr).strip()[-200:]}')
    return r.returncode == 0 and 'sent' in r.stdout


def report(res, sha, subject, no_mail):
    """last.json for the app chip and the Claude session hook; one email per new break and one per fix."""
    prev = json.loads(LAST.read_text(encoding='utf-8')) if LAST.exists() else {}
    key = hashlib.sha1('\n'.join(sorted(f['test'] for f in res['failing'])).encode()).hexdigest()[:10]
    state = {'sha': sha, 'full_sha': git('rev-parse', 'HEAD'), 'subject': subject, 'at': datetime.datetime.now().isoformat(timespec='seconds'),
             'status': res['status'], 'failing': res['failing'], 'passed': res['passed'], 'total': res['total'],
             'duration': res['duration'], 'out': res['out'], 'log': str(LOG), 'key': key if res['failing'] else '',
             'mailed_key': prev.get('mailed_key', ''), 'broken_since': prev.get('broken_since', '')}
    names = '\n'.join(f'  - {f["test"]}: {f["why"]}' for f in res['failing'])
    if res['status'] == 'fail':
        state['broken_since'] = state['broken_since'] or f'{sha} {subject}'
        if state['mailed_key'] != key and not no_mail:
            body = (f'The regression check of the taste app failed on commit {sha} ({subject}).\n\nFailing tests:\n{names}\n\n'
                    f'Log: {LOG}\nScreenshots: {res["out"]}\n\nThe next Claude session in the taste project is told about it first. '
                    f'You will get one more email when it is fixed.')
            if mail(f'taste app: regression found on {sha}', body, f'broken-{sha}'):
                state['mailed_key'] = key
    else:
        if prev.get('status') == 'fail' and prev.get('mailed_key') and not no_mail:
            body = (f'The regression check of the taste app passes again on commit {sha} ({subject}).\n\n'
                    f'It was broken since: {prev.get("broken_since", "?")}.')
            mail(f'taste app: regression fixed on {sha}', body, f'fixed-{sha}')
        state['mailed_key'] = state['broken_since'] = ''
    LAST.parent.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps(state, indent=1), encoding='utf-8')


def alive(pid):
    r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True)
    return str(pid) in r.stdout


def hook(flags, run_kwargs, repo=None):
    if repo and Path(repo).resolve() != ROOT.resolve():   # the hook is shared with the private taste/ repo: not ours
        return 0
    changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', '--root', 'HEAD').splitlines()
    if '--force' not in flags and not any(f.startswith(WATCHED) for f in changed):
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            pid = int(LOCK.read_text() or 0)
        except ValueError:
            pid = 0
        if time.time() - LOCK.stat().st_mtime < 900 and pid and alive(pid):
            PENDING.write_text('x')   # the run in progress will go once more on the latest HEAD
            log('a run is in progress; this commit is covered by one more run after it')
            return 0
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        while True:
            PENDING.unlink(missing_ok=True)
            sha, subject = git('rev-parse', '--short', 'HEAD'), git('log', '-1', '--format=%s')
            RUNNING.write_text(json.dumps({'sha': sha, 'since': datetime.datetime.now().isoformat(timespec='seconds')}))
            try:
                res = run(**run_kwargs)
            except BaseException as e:   # the check itself broke: say so as a failure, never silently
                res = {'status': 'fail', 'failing': [{'test': 'e2e.py', 'why': f'{type(e).__name__}: {e}'[:200]}], 'duration': 0, 'passed': 0, 'total': 0, 'out': str(OUT)}
            finally:
                RUNNING.unlink(missing_ok=True)
            log(summary(res, sha))
            report(res, sha, subject, '--no-mail' in flags)
            if not PENDING.exists():
                break
    finally:
        LOCK.unlink(missing_ok=True)
    if PENDING.exists():   # a commit landed in the last instant: one more pass
        return hook({**{f: 1 for f in flags}, '--force': 1}, run_kwargs, repo)
    return 0


def status():
    """For the SessionStart hook in .claude/settings.json: say nothing when the last check passed; when it failed, the
    sha, the failing tests and where the log is, so the session fixes that first."""
    if not LAST.exists():
        return 0
    last = json.loads(LAST.read_text(encoding='utf-8'))
    if last.get('status') != 'fail':
        return 0
    print(f'REGRESSION CHECK FAILING (scripts/e2e.py): after commit {last["sha"]} "{last["subject"]}" ({last["at"]}); '
          f'broken since {last.get("broken_since") or last["sha"]}.')
    print('Failing tests (fix this first, before the new task; Marc was told by email):')
    for f in last['failing']:
        print(f'  - {f["test"]}: {f["why"]}')
    print(f'Log: {last["log"]}   Screenshots and pytest output: {last["out"]}')
    print('Try the fix with `.venv/Scripts/python -I scripts/e2e.py --working` (about 2 minutes) before committing it.')
    return 0


def main():
    a = sys.argv[1:]
    flags = {x for x in a if x.startswith('--')}
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    extra = []
    if '-k' in a:
        extra += ['-k', a[a.index('-k') + 1]]
    if '-x' in a:
        extra.append('-x')
    kw = dict(working='--working' in flags, sabotaged='--sabotage' in flags, fake='--fake-route' in flags,
              keep='--keep' in flags, pytest_args=extra, serve='--serve' in flags)
    if '--status' in flags:
        return status()
    if '--hook' in flags:
        pos = [x for x in a if not x.startswith('-') and Path(x).is_dir()]
        try:
            return hook(flags, kw, pos[0] if pos else None)
        except Exception as e:   # a hook must never fail loudly
            log(f'error: {e}')
            return 1
    res = run(**kw)
    say(summary(res, 'working tree' if kw['working'] else f'HEAD {git("rev-parse", "--short", "HEAD")}'))
    say(f'screenshots and logs: {res["out"]}')
    return 0 if res['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
