"""Generate one image with Codex CLI (Marc's ChatGPT plan, no API key) and log the run.

Usage (from the project root):
  .venv/Scripts/python -I scripts/codex_run.py gen --out generated/codex/<batch> --name <name> --prompt "<text>"
        [--ref <seed image>] [--style <style>] [--mode variations|text|test] [--change "<what this one changes>"]
  .venv/Scripts/python -I scripts/codex_run.py gen --out ... --name ... --style <style> --subject "<scene>"
        [--ratio wide|square|portrait]      # prompt built from taste/taste.json (image for a text)
  .venv/Scripts/python -I scripts/codex_run.py read      # usage now, from the newest Codex session log

One fresh `codex exec` per image. Codex only generates and copies the PNG into --out; it never views the
result and never touches the taste files. Afterwards this script reads tokens and the five-hour / weekly
allowance from Codex's own session log (~/.codex/sessions) and the PNG's real pixel size, and appends
one row to generated/codex/runs.csv (git-ignored). Numbers are never typed by hand.
One recovery only: if the PNG is not in --out, copy it from ~/.codex/generated_images/<session>/.
Otherwise the run is logged as failed; stop and report, do not loop.
"""
import argparse, csv, datetime, json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / 'generated' / 'codex' / 'runs.csv'
CODEX = Path.home() / '.codex'
HEADER = ['date', 'time', 'batch', 'name', 'mode', 'style', 'change', 'seed', 'ok', 'width', 'height',
          'tokens', 'five_hour_first', 'five_hour_last', 'weekly_first', 'weekly_last', 'seconds', 'session', 'prompt']

JOB = """Image job. Use the image_gen tool exactly once. Do not write code to draw, do not view, open or describe the result, and do not create or edit any other file.
{ref}Image prompt: {prompt}
When it is done, copy the generated PNG to {name}.png in the current directory. Reply with the file name only."""
REF = ('The attached image ({path}) is the seed: pass it to image_gen as referenced_image_paths. '
       'Keep its overall look unless the prompt says what to change; make a new image, not a copy.\n')


def readings(path):
    """All usage readings in one session log, oldest first: (total tokens, five-hour %, weekly %)."""
    out = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            if '"token_count"' not in line:
                continue
            try:
                p = json.loads(line).get('payload', {})
            except json.JSONDecodeError:
                continue
            r = p.get('rate_limits') or {}
            if p.get('type') == 'token_count' and r.get('primary'):
                tok = ((p.get('info') or {}).get('total_token_usage') or {}).get('total_tokens')
                out.append((tok, r['primary']['used_percent'], r['secondary']['used_percent']))
    return out


def find_session(cwd, since):
    """Newest Codex session log started after `since` whose working folder is `cwd`."""
    want = os.path.normcase(os.path.abspath(cwd))
    cands = [p for p in (CODEX / 'sessions').rglob('rollout-*.jsonl') if p.stat().st_mtime >= since]
    for p in sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True):
        with open(p, encoding='utf-8') as fh:
            meta = json.loads(fh.readline()).get('payload', {})
        if os.path.normcase(os.path.abspath(meta.get('cwd', ''))) == want:
            return p, meta.get('id', '')
    return None, ''


RATIOS = {'wide': 'Wide 16:9 desktop wallpaper.', 'square': 'Square 1:1 image for a LinkedIn post.',
          'portrait': 'Portrait 4:5 image for a LinkedIn post.'}


def compose(a):
    """Short prompt: ratio + subject + one style block from the generated taste file."""
    taste = json.load(open(ROOT / 'taste' / 'taste.json', encoding='utf-8'))['styles']
    if a.style not in taste:
        sys.exit(f'unknown style "{a.style}"; pick one of: {", ".join(taste)}')
    return f"{RATIOS[a.ratio]} Subject: {a.subject}. {taste[a.style]['prompt']}"


def gen(a):
    if not a.prompt:
        if not (a.style and a.subject):
            sys.exit('give --prompt, or --style and --subject')
        a.prompt = compose(a)
    out = (ROOT / a.out).resolve() if not os.path.isabs(a.out) else Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ref = Path(a.ref).resolve() if a.ref else None
    job = JOB.format(ref=REF.format(path=ref) if ref else '', prompt=a.prompt, name=a.name)
    cmd = [shutil.which('codex') or 'codex', 'exec', '--skip-git-repo-check', '-s', 'workspace-write']
    if ref:
        cmd += ['-i', str(ref)]
    start = time.time()
    res = subprocess.run(cmd, input=job, cwd=out, capture_output=True, text=True, encoding='utf-8',
                         errors='replace', timeout=900)
    secs = round(time.time() - start)
    (out / f'{a.name}.codex.log').write_text((res.stdout or '')[-3000:] + '\n--- stderr ---\n' + (res.stderr or '')[-3000:],
                                             encoding='utf-8')
    session, sid = find_session(out, start - 5)
    png = out / f'{a.name}.png'
    if not png.exists() and sid:  # the one recovery
        found = sorted((CODEX / 'generated_images' / sid).glob('*.png'), key=lambda p: p.stat().st_mtime)
        if found:
            shutil.copy2(found[-1], png)
            print('recovered the PNG from ~/.codex/generated_images')
    w = h = ''
    if png.exists():
        from PIL import Image
        w, h = Image.open(png).size
    r = readings(session) if session else []
    first, last = (r[0], r[-1]) if r else ((None, '', ''), (None, '', ''))
    now = datetime.datetime.now()
    row = [now.date().isoformat(), now.strftime('%H:%M'), out.name, a.name, a.mode, a.style, a.change,
           ref.name if ref else '', 'yes' if png.exists() else 'no', w, h, last[0] if last[0] is not None else '',
           first[1], last[1], first[2], last[2], secs, sid, a.prompt]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, 'a', encoding='utf-8', newline='') as fh:
        wr = csv.writer(fh)
        if new:
            wr.writerow(HEADER)
        wr.writerow(row)
    print(json.dumps(dict(zip(HEADER[:18], row[:18]))))
    if not png.exists():
        print(f'FAILED: no image. Codex exit code {res.returncode}; see {a.name}.codex.log', file=sys.stderr)
        sys.exit(2)


def read_now():
    files = sorted((CODEX / 'sessions').rglob('rollout-*.jsonl'), key=lambda p: p.stat().st_mtime)
    for p in reversed(files):
        r = readings(p)
        if r:
            print(json.dumps({'five_hour': r[-1][1], 'weekly': r[-1][2], 'session_log': p.name,
                              'as_of': datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='minutes')}))
            return
    sys.exit('No usage reading found under ~/.codex/sessions; report usage as unknown.')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('gen')
    g.add_argument('--out', required=True)
    g.add_argument('--name', required=True)
    g.add_argument('--prompt', default='')
    g.add_argument('--subject', default='')
    g.add_argument('--ratio', default='wide', choices=['wide', 'square', 'portrait'])
    g.add_argument('--ref', default='')
    g.add_argument('--style', default='')
    g.add_argument('--mode', default='test')
    g.add_argument('--change', default='')
    sub.add_parser('read')
    a = ap.parse_args()
    gen(a) if a.cmd == 'gen' else read_now()
