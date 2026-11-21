"""Run a short list of images from a jobs file: remixes, single images and retries started from the web app
(21 Nov 2026). Batches with fresh subjects stay with batch.py, variations of a seed with variations.py.

Usage (from the project root):
  .venv/Scripts/python -I scripts/run_list.py --out generated/codex/<batch> --jobs <jobs.json> [--dry-run]

<jobs.json> is a list; each job is one codex_run.py gen call:
  {"name": "remix-1", "prompt": "...", "ref": "<path to a reference image>", "style": "...", "mode": "remix",
   "change": "remix: less pink"}
  or {"name": "fern-1", "style": "...", "subject": "...", "ratio": "wide", "mode": "text"}
Writes live progress for the web app (scripts/progress.py). One recovery happens inside codex_run.py; here
2 failures in a row stop the list, as the repo rules say. --dry-run prints each prompt and spends nothing.
"""
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from progress import Progress, CHILD_ENV  # noqa: E402

PY = sys.executable
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--out', required=True)
ap.add_argument('--jobs', required=True)
ap.add_argument('--dry-run', action='store_true')
a = ap.parse_args()

jobs = json.load(open(a.jobs, encoding='utf-8'))


def command(j):
    cmd = [PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'gen', '--out', a.out, '--name', j['name'],
           '--mode', j.get('mode', 'test')]
    for key in ('prompt', 'ref', 'style', 'subject', 'ratio', 'change'):
        if j.get(key):
            cmd += [f'--{key}', str(j[key])]
    return cmd


if a.dry_run:
    for j in jobs:
        if j.get('prompt'):
            print(json.dumps({'name': j['name'], 'change': j.get('change', ''), 'prompt': j['prompt']}, ensure_ascii=False))
        else:
            r = subprocess.run(command(j) + ['--print'], capture_output=True, text=True, encoding='utf-8')
            print(r.stdout.strip() or r.stderr.strip())
    sys.exit(0)

prog = Progress(a.out, [j['name'] for j in jobs], 'list')
fails = 0
for j in jobs:
    prog.begin(j['name'], j.get('subject') or j.get('change', ''))
    res = subprocess.run(command(j), capture_output=True, text=True, encoding='utf-8', errors='replace', env=CHILD_ENV)
    if res.returncode == 0:
        print(f'ok {j["name"]}', flush=True)
        prog.ok(j['name'])
        fails = 0
    else:
        why = ((res.stderr or res.stdout or '').strip().splitlines() or [''])[-1][:200]
        print(f'FAILED {j["name"]}: {why}', flush=True)
        prog.fail(j['name'], why)
        fails += 1
        if fails >= 2:
            print('STOPPED: 2 failures in a row')
            prog.line('STOPPED: 2 failures in a row')
            break
prog.end('done')
