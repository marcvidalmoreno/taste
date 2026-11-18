"""Run a batch of test images with fresh subjects, mixed looks and one wildcard per style (18 Nov 2026).

Usage (from the project root):
  .venv/Scripts/python -I scripts/batch.py --out generated/codex/<batch> --subjects <subjects.json>
        [--styles a,b] [--n 4] [--start 0] [--wildcards 1] [--seed S] [--dry-run]
  --start K: begin at subject K (image names K+1...), to use a subjects file's later subjects in a second batch

<subjects.json> is {"<style>": ["subject", ...], ...}, written fresh by Claude Code for each batch (keep it in
the batch folder, git-ignored). Styles default to the keys of that file. Per style, image i gets subject i
(cycled), a ratio from wide / portrait / square / wide, and its own random mix of light, framing, mood and palette
(codex_run.py --mix). The last --wildcards images of each style also push one random dimension to an extreme
(codex_run.py --extreme). Everything picked is logged in the "change" column, so ratings show what worked.
--dry-run prints the prompts and spends nothing. A failed or blocked image is skipped (codex_run makes its one
recovery); 3 failures in a row stop the run.
"""
import argparse, json, random, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from codex_run import EXTREMES  # noqa: E402

RATIOS = ['wide', 'portrait', 'square', 'wide']
PY = sys.executable

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--out', required=True)
ap.add_argument('--subjects', required=True)
ap.add_argument('--styles', default='')
ap.add_argument('--n', type=int, default=4)
ap.add_argument('--start', type=int, default=0)
ap.add_argument('--wildcards', type=int, default=1)
ap.add_argument('--seed', default='')
ap.add_argument('--dry-run', action='store_true')
a = ap.parse_args()

subjects = json.load(open(a.subjects, encoding='utf-8'))
taste = json.load(open(ROOT / 'taste' / 'taste.json', encoding='utf-8'))['styles']
styles = a.styles.split(',') if a.styles else list(subjects)
unknown = [s for s in styles if s not in taste or not subjects.get(s)]
if unknown:
    sys.exit(f'no such style or no subjects for: {", ".join(unknown)}')
seed = a.seed or Path(a.out).name
rnd = random.Random(seed)
fails = 0
for style in styles:
    for i in range(a.start, a.start + a.n):
        name = f'{style}-{i + 1}'
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'gen', '--out', a.out, '--name', name,
               '--style', style, '--subject', subjects[style][i % len(subjects[style])],
               '--ratio', RATIOS[i % len(RATIOS)], '--mix', seed, '--mode', 'test']
        if i >= a.start + a.n - a.wildcards:
            cmd += ['--extreme', rnd.choice(sorted(EXTREMES))]
        if a.dry_run:
            out = subprocess.run(cmd + ['--print'], capture_output=True, text=True, encoding='utf-8')
            print(out.stdout.strip() or out.stderr.strip())
            continue
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        if res.returncode == 0:
            print(f'ok {name}', flush=True)
            fails = 0
        else:
            print(f'FAILED {name}', flush=True)
            fails += 1
            if fails >= 3:
                print('STOPPED: 3 failures in a row')
                break
    else:
        continue
    break
if not a.dry_run:
    subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'read'])
    print(f'next: {PY} -I scripts/sheet.py {a.out}, then rate in the web app')
