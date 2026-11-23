"""Run a batch of test images with fresh subjects, mixed looks and one wildcard per style (18 Nov 2026).

Usage (from the project root):
  .venv/Scripts/python -I scripts/batch.py --out generated/codex/<batch> --subjects <subjects.json>
        [--styles a,b] [--n 4] [--start 0] [--wildcards 1] [--ratio mixed|wide|portrait|square] [--seed S] [--dry-run]
  --start K: begin at subject K (image names K+1...), to use a subjects file's later subjects in a second batch
  --only a-3,b-1: make only these images of the batch, with the same picks as the first run (Finish this batch,
        23 Nov 2026: the web app runs it for the images a stopped run never made)

<subjects.json> is {"<style>": ["subject", ...], ...}, written fresh by Claude Code for each batch (keep it in
the batch folder, git-ignored). Styles default to the keys of that file. Per style, image i gets subject i
(cycled), a ratio from wide / portrait / square / wide, and its own mix of light, framing, mood and palette
(codex_run.py --mix --slot i: options spread so the images of a style don't repeat one until all are used). The last --wildcards images of each style also push one random dimension to an extreme
(codex_run.py --extreme). Everything picked is logged in the "change" column, so ratings show what worked.
--experimental (23 Nov 2026, the web app's "Experimental" switch): every image gets a palette the style never uses
(codex_run.py --new-palette), options picked evenly instead of leaning on the ratings (--no-lean), and every image
after the first of each style gets a wildcard (never the palette one, which the new palette already covers).
--dry-run prints the prompts and spends nothing. A failed or blocked image is skipped (codex_run makes its one
recovery); 3 failures in a row stop the run.
"""
import argparse, json, random, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from codex_run import EXTREMES  # noqa: E402
from progress import Progress, CHILD_ENV  # noqa: E402

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
ap.add_argument('--ratio', default='mixed', choices=['mixed', 'wide', 'portrait', 'square'],
                help='mixed (default): wide, portrait, square, wide in turn; or one ratio for every image')
ap.add_argument('--seed', default='')
ap.add_argument('--kept-refs', default='', help='JSON {style: [image paths]}: kept examples sent along as references (2 per image, turning)')
ap.add_argument('--only', default='', help='comma-separated image names: make only these (the rest are skipped, picks unchanged)')
ap.add_argument('--experimental', action='store_true', help='new palettes, no leaning, a wildcard on all but the first image')
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
kept = json.load(open(a.kept_refs, encoding='utf-8')) if a.kept_refs else {}
PER_IMAGE = 2
fails = 0
names = [f'{s}-{i + 1}' for s in styles for i in range(a.start, a.start + a.n)]
only = set(a.only.split(',')) if a.only else None
if only:
    names = [n for n in names if n in only]
prog = None if a.dry_run else Progress(a.out, names, 'batch')
for style in styles:
    for i in range(a.start, a.start + a.n):
        name = f'{style}-{i + 1}'
        cmd = [PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'gen', '--out', a.out, '--name', name,
               '--style', style, '--subject', subjects[style][i % len(subjects[style])],
               '--ratio', RATIOS[i % len(RATIOS)] if a.ratio == 'mixed' else a.ratio, '--mix', seed, '--slot', str(i), '--mode', 'test']
        have = kept.get(style) or []
        for k in range(min(PER_IMAGE, len(have))):
            cmd += ['--ref', have[(i * PER_IMAGE + k) % len(have)]]
        if have:
            cmd.append('--refs-kept')
        if a.experimental:
            cmd += ['--new-palette', '--no-lean']
            if i > a.start or a.n == 1:   # picked before the --only skip, so a finish gets the first run's wildcard
                cmd += ['--extreme', rnd.choice(sorted(x for x in EXTREMES if x != 'palette'))]
        elif i >= a.start + a.n - a.wildcards:   # picked before the --only skip, so a finish gets the first run's wildcard
            cmd += ['--extreme', rnd.choice(sorted(EXTREMES))]
        if only is not None and name not in only:
            continue
        if a.dry_run:
            out = subprocess.run(cmd + ['--print'], capture_output=True, text=True, encoding='utf-8')
            print(out.stdout.strip() or out.stderr.strip())
            continue
        prog.begin(name, subjects[style][i % len(subjects[style])])
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=CHILD_ENV)
        if res.returncode == 0:
            print(f'ok {name}', flush=True)
            prog.ok(name)
            fails = 0
        else:
            print(f'FAILED {name}', flush=True)
            why = ((res.stderr or res.stdout or '').strip().splitlines() or [''])[-1][:200]
            prog.fail(name, why)
            fails += 1
            if fails >= 3:
                print('STOPPED: 3 failures in a row')
                prog.line('STOPPED: 3 failures in a row')
                break
    else:
        continue
    break
if not a.dry_run:
    prog.end('done')
    subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'read'])
    print(f'next: {PY} -I scripts/sheet.py {a.out}, then rate in the web app')
