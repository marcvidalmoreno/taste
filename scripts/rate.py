"""Record Marc's ratings for one batch: keep / almost / no, optional word why.

Usage (from the project root):
  .venv/Scripts/python -I scripts/rate.py <batch> 1=keep 2=almost:too-busy 3=no:dark
  .venv/Scripts/python -I scripts/rate.py status
Numbers are the contact-sheet numbers (1 = first generated image). Appends to generated/codex/ratings.csv
(git-ignored), with style, mode, change and prompt copied from runs.csv so the distil step has them.
`status` says how many ratings since the last distil; at 20 or more it says a distil is due.

The web app (scripts/app.py) writes through the same function, `append_ratings`, so ratings.csv has one
writer and one format whichever way Marc rates.
"""
import csv, datetime, json, glob, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'generated' / 'codex'
RATINGS, RUNS, STATE = BASE / 'ratings.csv', BASE / 'runs.csv', BASE / 'distil-state.json'
HEADER = ['date', 'batch', 'number', 'name', 'style', 'mode', 'change', 'rating', 'why', 'prompt']
RATINGS_ALLOWED = ('keep', 'almost', 'no')
DUE = 20


def since_last():
    if not RATINGS.exists():
        return []
    done = json.load(open(STATE))['rows'] if STATE.exists() else 0
    return list(csv.DictReader(open(RATINGS, encoding='utf-8')))[done:]


def batch_images(batch):
    """Image names (no .png) of one batch in rating order: sorted, the seed left out.
    Position + 1 is the number on the contact sheet and in ratings.csv."""
    return sorted(os.path.basename(p)[:-4] for p in glob.glob(str(BASE / batch / '*.png'))
                  if not os.path.basename(p).startswith('seed.'))


def batch_runs(batch):
    """runs.csv rows of one batch, by image name."""
    if not RUNS.exists():
        return {}
    return {r['name']: r for r in csv.DictReader(open(RUNS, encoding='utf-8')) if r['batch'] == batch}


def append_ratings(batch, marks):
    """Append ratings to ratings.csv. marks: [(name, rating, why), ...]. Returns the rows written.
    Checks everything first, so a bad mark writes nothing."""
    names, runs = batch_images(batch), batch_runs(batch)
    rows = []
    for name, rating, why in marks:
        if rating not in RATINGS_ALLOWED:
            raise ValueError(f'bad rating "{rating}" for {name}: use keep, almost or no')
        if name not in names:
            raise ValueError(f'no image "{name}" in batch {batch}')
        run = runs.get(name, {})
        why = ' '.join((why or '').split())  # one line, single spaces
        rows.append([datetime.date.today().isoformat(), batch, str(names.index(name) + 1), name,
                     run.get('style', ''), run.get('mode', ''), run.get('change', ''), rating, why,
                     run.get('prompt', '')])
    new = not RATINGS.exists()
    with open(RATINGS, 'a', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(HEADER)
        w.writerows(rows)
    return rows


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == 'status':
        n = len(since_last())
        print(f'{n} ratings since the last distil' + ('  -> distil due (scripts/distil.py)' if n >= DUE else f' ({DUE - n} to go)'))
        return

    # Command line: turn "2=almost:too-busy" into (name, rating, why), then use the shared writer.
    batch = sys.argv[1]
    names = batch_images(batch)
    marks = []
    for item in sys.argv[2:]:
        num, _, rest = item.partition('=')
        rating, _, why = rest.partition(':')
        if rating not in RATINGS_ALLOWED or not num.isdigit() or not 1 <= int(num) <= len(names):
            sys.exit(f'bad rating "{item}": use N=keep|almost|no[:why], N from 1 to {len(names)}')
        marks.append((names[int(num) - 1], rating, why.replace('-', ' ')))
    rows = append_ratings(batch, marks)
    for r in rows:
        print(f'{r[2]} {r[3]}: {r[7]}{" - " + r[8] if r[8] else ""}')
    n = len(since_last())
    print(f'{n} ratings since the last distil' + ('  -> distil due' if n >= DUE else ''))


if __name__ == '__main__':
    main()
