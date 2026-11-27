"""Coverage guard (27 Nov 2026): stops the regression check from quietly covering less of the app as features land.

  .venv/Scripts/python -I scripts/coverage_guard.py            # check the files as they are now
  .venv/Scripts/python -I scripts/coverage_guard.py --staged   # check what is staged (the pre-commit hook uses this)

It reads, in a second and without a browser:
- every write route (POST / PUT / DELETE) in the ROUTES table of scripts/app.py, against tests/e2e/coverage.json,
  which names the test that clicks each one, or says "skip: <why>";
- every page in the `pages` map of app/js/main.js, against PAGES in tests/e2e/test_1_pages.py.
A route or page with no entry, an entry for a route that is gone, or a named test that does not exist fails.
Whether a named test really sends its request is checked by the full suite (tests/e2e/test_9_coverage.py).
The pre-commit hook (scripts/gallery_sync.py --install-hooks) runs it on commits touching app/, scripts/ or tests/.
Skip it once with `git commit --no-verify`.
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = 'tests/e2e/coverage.json'


def read(rel, root=ROOT, staged=False):
    if staged:
        r = subprocess.run(['git', '-C', str(root), 'show', f':{rel}'], capture_output=True)
        if r.returncode == 0:
            return r.stdout.decode('utf-8')
    f = root / rel
    return f.read_text(encoding='utf-8') if f.exists() else None


def write_routes(app_src):
    m = re.search(r'ROUTES = \{(.*?)\n    \}', app_src, re.S)
    if not m:
        raise SystemExit('coverage guard: no ROUTES table in scripts/app.py')
    return [f'{a} {b}' for a, b in re.findall(r"\('(POST|PUT|DELETE|PATCH)',\s*'([^']+)'\)", m.group(1))]


def route_for(method, path, routes):
    """The write route a request lands on: same rule as app.py, the longest matching prefix wins."""
    best = None
    for r in routes:
        m, prefix = r.split(' ', 1)
        if m == method and (path == prefix or path.startswith(prefix + '/')) and (not best or len(prefix) > len(best.split(' ', 1)[1])):
            best = r
    return best


def problems(root=ROOT, staged=False):
    out = []
    routes = write_routes(read('scripts/app.py', root, staged))
    raw = read(LEDGER, root, staged)
    if not (raw or '').strip():
        return [f'{LEDGER} is missing' + (' or not staged' if staged else '')]
    ledger = json.loads(raw)
    tests = '\n'.join(read(str(f.relative_to(root)).replace('\\', '/'), root, staged) or '' for f in sorted((root / 'tests' / 'e2e').glob('test_*.py')))
    for r in routes:
        if r not in ledger:
            out.append(f'{r}: new write action with no test. Add a test in tests/e2e/ and name it in {LEDGER} '
                       f'(or "skip: <why>" if it reaches outside the laptop)')
    for r, v in ledger.items():
        if r not in routes:
            out.append(f'{r}: in {LEDGER} but no longer in scripts/app.py; remove the line')
        elif not str(v).startswith('skip:') and not re.search(rf'^def {re.escape(v)}\(', tests, re.M):
            out.append(f'{r}: names test "{v}", which is not in tests/e2e/')
    main_js, pages_py = read('app/js/main.js', root, staged), read('tests/e2e/test_1_pages.py', root, staged)
    m, p = re.search(r'const pages = \{(.*?)\}', main_js or '', re.S), re.search(r'PAGES = \{(.*?)\n\}', pages_py or '', re.S)
    if m and p:
        missing = sorted(set(re.findall(r'(\w+)\s*:', m.group(1))) - set(re.findall(r"^\s*'(\w*)'\s*:", p.group(1), re.M)))
        out += [f'page "{k}" in app/js/main.js has no test: add it to PAGES in tests/e2e/test_1_pages.py' for k in missing]
    return out


def main():
    found = problems(staged='--staged' in sys.argv)
    if not found:
        return 0
    print('Coverage guard: the commit adds something the regression check does not test.')
    for f in found:
        print('  -', f)
    print('Skip once (not recommended): git commit --no-verify')
    return 1


if __name__ == '__main__':
    sys.exit(main())
