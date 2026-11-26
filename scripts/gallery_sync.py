"""Keep the public taste-gallery site in step: publish.py --sync, then commit and push taste-gallery.

  .venv/Scripts/python -I scripts/gallery_sync.py                 # sync now (the app calls this ~5 min after the last Publish toggle)
  .venv/Scripts/python -I scripts/gallery_sync.py --hook <repo>   # from a post-commit hook: sync only after a major commit
  .venv/Scripts/python -I scripts/gallery_sync.py --install-hooks # (re)install the post-commit hooks in taste and taste/
                                                                   # (they also start the regression check, scripts/e2e.py --hook)

Major commit: touches styles or taste.json in the private repo taste/, or the README (its changelog feeds the site)
in either repo. A commit that changes scripts/build_taste.py or scripts/pack.py also writes a note to
generated/kit-update-needed.md: the slimmed copies in taste-gallery/kit/ need the same change.

Does nothing while there are no picks (generated/codex/publish.json empty), so the sample site is never wiped.
Commits only docs/data and docs/img in taste-gallery (other sessions may be editing the page files) and pushes only
when an `origin` remote exists. Logs to generated/codex/gallery-sync.log. One run at a time (a lock file).
"""
import datetime, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GALLERY = Path(os.environ.get('TASTE_GALLERY') or ROOT.parent / 'taste-gallery')   # env overrides: for tests
LOG = ROOT / 'generated' / 'codex' / 'gallery-sync.log'
LOCK = ROOT / 'generated' / 'codex' / '.gallery-sync.lock'
PICKS = Path(os.environ.get('TASTE_PICKS') or ROOT / 'generated' / 'codex' / 'publish.json')
KIT_NOTE = ROOT / 'generated' / 'kit-update-needed.md'
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
HOOK = """#!/bin/sh
# Installed by scripts/gallery_sync.py --install-hooks: keeps the public taste-gallery site in step after major commits.
# Runs in the background so the commit returns at once; output goes to generated/codex/gallery-sync.log.
# The second line (26 Nov 2026) starts the regression check of the web app (scripts/e2e.py): it acts only on commits
# in this repo that touch app/, scripts/ or tests/, one run at a time; output goes to generated/e2e/.
ROOT="{root}"
nohup "$ROOT/.venv/Scripts/python.exe" -I "$ROOT/scripts/gallery_sync.py" --hook "$(git rev-parse --show-toplevel)" >/dev/null 2>&1 &
nohup "$ROOT/.venv/Scripts/python.exe" -I "$ROOT/scripts/e2e.py" --hook "$(git rev-parse --show-toplevel)" >/dev/null 2>&1 </dev/null &
exit 0
"""


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    print(msg)


def git(repo, *args, check=True):
    r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and r.returncode:
        raise RuntimeError(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout.strip()


def changed_files(repo):
    return git(repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', '--root', 'HEAD').splitlines()


def is_major(repo, files):
    private = Path(repo).resolve() == (ROOT / 'taste').resolve()
    if private and any(f.startswith('styles/') or f == 'taste.json' for f in files):
        return True
    return 'README.md' in files


def kit_note(files):
    hit = [f for f in files if f in ('scripts/build_taste.py', 'scripts/pack.py')]
    if hit:
        KIT_NOTE.parent.mkdir(parents=True, exist_ok=True)
        with open(KIT_NOTE, 'a', encoding='utf-8') as fh:
            fh.write(f"- {datetime.date.today()}: {', '.join(hit)} changed (commit {git(ROOT, 'rev-parse', '--short', 'HEAD')}); "
                     f"bring the same change to taste-gallery/kit/scripts/ if it applies.\n")
        log(f'kit note written: {", ".join(hit)}')


def picks():
    try:
        return json.loads(PICKS.read_text(encoding='utf-8')) or []
    except (OSError, ValueError):
        return []


def sync(reason):
    if not picks():
        log(f'{reason}: no picks yet, site left as it is')
        return 0
    if not (GALLERY / '.git').exists():
        log(f'{reason}: {GALLERY} is not a git repo, stopped')
        return 1
    r = subprocess.run([str(PY), '-I', str(ROOT / 'scripts' / 'publish.py'), '--sync',
                        '--picks', str(PICKS), '--out', str(GALLERY / 'docs')], cwd=ROOT,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        log(f'{reason}: publish.py failed (exit {r.returncode}), nothing committed:\n{(r.stdout + r.stderr)[-1500:]}')
        return r.returncode
    git(GALLERY, 'add', '-A', '--', 'docs/data', 'docs/img')
    staged = git(GALLERY, 'diff', '--cached', '--name-only', '--', 'docs/data', 'docs/img')
    if not staged:
        log(f'{reason}: site already up to date')
        return 0
    n = len(picks())
    git(GALLERY, 'commit', '-q', '-m', f'site: sync {n} published pictures and evolution data', '--', 'docs/data', 'docs/img')
    if 'origin' in git(GALLERY, 'remote').split():
        git(GALLERY, 'push', '-q', 'origin', 'HEAD')
        log(f'{reason}: committed and pushed ({len(staged.splitlines())} files)')
    else:
        log(f'{reason}: committed locally ({len(staged.splitlines())} files); no origin remote yet, not pushed')
    return 0


def install_hooks():
    for repo in (ROOT, ROOT / 'taste'):
        hooks = Path(git(repo, 'rev-parse', '--git-path', 'hooks'))
        hooks = hooks if hooks.is_absolute() else repo / hooks
        target = hooks / 'post-commit'
        if target.exists() and 'gallery_sync.py' not in target.read_text(encoding='utf-8', errors='replace'):
            print(f'{target} exists and is not ours; left alone')
            continue
        target.write_text(HOOK.format(root=ROOT.as_posix()), encoding='utf-8', newline='\n')
        os.chmod(target, 0o755)
        print('installed', target)


def main():
    if '--install-hooks' in sys.argv:
        install_hooks()
        return 0
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime < 900:
            log('another sync is running; skipped')
            return 0
        LOCK.unlink()   # stale lock from a crashed run
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        if '--hook' in sys.argv:
            repo = Path(sys.argv[sys.argv.index('--hook') + 1])
            files = changed_files(repo)
            if repo.resolve() == ROOT.resolve():
                kit_note(files)
            if not is_major(repo, files):
                return 0
            return sync(f'after commit {git(repo, "rev-parse", "--short", "HEAD")} in {repo.name}')
        return sync('manual' if len(sys.argv) == 1 else ' '.join(sys.argv[1:]))
    except Exception as e:   # a hook must never fail loudly; say it in the log
        log(f'error: {e}')
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.exit(main())
