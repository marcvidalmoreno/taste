"""Variations mode: from one image Marc likes, make 3-4 similar images, each changing one thing.

Usage (from the project root):
  .venv/Scripts/python -I scripts/variations.py <seed image> [--style <style>] [--subject "<new subject>"] [--n 3|4]
        [--note "<instruction for every image>"] [--changes palette,subject,composition,mood] [--slug <name>] [--dry-run]
  --changes (21 Nov 2026): pick which variations to make, in any combination; overrides --n
  --out <batch folder> --only 3-composition,4-mood (23 Nov 2026): resume a stopped run in its own folder

- Style: give --style (Claude looks at the seed once, or Marc names it). Without it the script prints the
  top-3 guesses from scripts/nearest.py and stops: the guess alone is right only about a third of the time.
- One fresh Codex run per image (scripts/codex_run.py), the seed attached as reference.
  1 palette  - same subject and composition, palette and light pulled to the style
  2 subject  - same palette, light and composition, new subject (--subject, or one from the style, or Codex picks)
  3 composition - same palette and subject, different framing
  4 mood (only with --n 4) - same scene, other time of day
- Ends with a contact sheet (scripts/sheet.py) and the rating line to fill in.
Output: generated/codex/<date>-<slug>/ (git-ignored). The seed is copied there as seed.<ext>.
"""
import argparse, datetime, json, os, random, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
COMPOSITIONS = ['a wider view with much more empty space around the subject',
                'a closer view, the subject large and placed off-centre',
                'a low horizon, most of the frame given to sky or ceiling',
                'a high viewpoint looking down on the scene']

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed')
ap.add_argument('--style', default='')
ap.add_argument('--subject', default='')
ap.add_argument('--note', default='', help='one instruction for every image, e.g. "no planet in the sky"')
ap.add_argument('--n', type=int, default=3, choices=[3, 4])
ap.add_argument('--changes', default='', help='comma list of palette, subject, composition, mood; overrides --n')
ap.add_argument('--slug', default='')
ap.add_argument('--out', default='', help='an existing batch folder to add to (resume, 23 Nov 2026); overrides --slug')
ap.add_argument('--only', default='', help='comma list of names to make (e.g. 3-composition,4-mood); numbering stays')
ap.add_argument('--dry-run', action='store_true')
a = ap.parse_args()
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

seed = Path(a.seed).resolve()
subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'build_taste.py'), str(ROOT)], check=True, capture_output=True)
taste = json.load(open(ROOT / 'taste' / 'taste.json', encoding='utf-8'))['styles']
style = a.style
if not style:
    sys.path.insert(0, str(ROOT / 'scripts'))
    from nearest import model
    top, far, _ = model(str(ROOT))(str(seed))
    print(f'pick a style with --style; best guesses: {", ".join(s for s, _ in top)}{" (far from all styles)" if far else ""}')
    sys.exit(3)
if style not in taste:
    sys.exit(f'unknown style "{style}"; pick one of: {", ".join(taste)}')
s = taste[style]
subject = a.subject or (random.choice(s['subjects']) if s['subjects'] else
                        'a different subject that suits the same kind of scene (your choice)')
slug = a.slug or seed.stem.lower().replace(' ', '-')[:30]
batch = Path(a.out).resolve() if a.out else ROOT / 'generated' / 'codex' / f'{datetime.date.today().isoformat()}-{slug}'
jobs = [('palette', 'Keep the subject and composition of the seed; change only the colour palette and light to match the style notes.'),
        ('subject', f'Keep the palette, light and composition of the seed; change only the subject to: {subject}.'),
        ('composition', f'Keep the palette, light and kind of subject of the seed; change only the composition to {random.choice(COMPOSITIONS)}.'),
        ('mood', 'Keep the subject and composition of the seed; change only the time of day and mood (dawn if the seed is dark, dusk if it is bright).')]
if a.changes:
    want = [c.strip() for c in a.changes.split(',') if c.strip()]
    bad = [c for c in want if c not in dict(jobs)]
    if bad or not want:
        sys.exit(f'--changes: unknown {", ".join(bad) or "(empty)"}; pick from palette, subject, composition, mood')
    jobs = [j for j in jobs if j[0] in want]
else:
    jobs = jobs[:a.n]
jobs = [(i, c, t) for i, (c, t) in enumerate(jobs, 1)]
if a.only:   # resume: make only these, with the numbers they had in the first run
    only = {x.strip() for x in a.only.split(',') if x.strip()}
    jobs = [j for j in jobs if f'{j[0]}-{j[1]}' in only]
    if not jobs:
        sys.exit(f'--only: none of {", ".join(sorted(only))} is in this run')
print(f'batch: {batch}')
if a.dry_run:
    for _, change, text in jobs:
        print(f'- {change}: {text}')
    if a.note:
        print(f'- every image: {a.note}')
    sys.exit(0)
batch.mkdir(parents=True, exist_ok=True)
if seed != (batch / f'seed{seed.suffix.lower()}').resolve():
    shutil.copy2(seed, batch / f'seed{seed.suffix.lower()}')
sys.path.insert(0, str(ROOT / 'scripts'))
from progress import Progress, CHILD_ENV  # noqa: E402
prog = Progress(batch, [f'{i}-{c}' for i, c, _ in jobs], 'variations')
failed = 0
for i, change, text in jobs:
    must = f' In every image, and above the style notes: {a.note.rstrip(".")}.' if a.note else ''
    prompt = f'Wide 16:9 desktop wallpaper. {text}{must} Style notes (follow them where the change leaves room): {s["prompt"]}'
    prog.begin(f'{i}-{change}', change)
    r = subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'codex_run.py'), 'gen', '--out', str(batch),
                        '--name', f'{i}-{change}', '--prompt', prompt, '--ref', str(seed), '--style', style,
                        '--mode', 'variations', '--change', change], env=CHILD_ENV)
    if r.returncode:
        prog.fail(f'{i}-{change}')
        failed += 1
        if failed == 2:
            print('two failures: stopping the batch, report and do not retry', file=sys.stderr)
            prog.line('STOPPED: two failures')
            break
    else:
        prog.ok(f'{i}-{change}')
prog.end('done')
subprocess.run([PY, '-I', str(ROOT / 'scripts' / 'sheet.py'), str(batch)])
print(f'rate with: .venv/Scripts/python -I scripts/rate.py {batch.name} 1=keep 2=almost:why 3=no:why')
