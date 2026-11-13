"""Distil step: summarise ratings since the last distil so Claude can propose style-profile edits.

Usage (from the project root):
  .venv/Scripts/python -I scripts/distil.py          # print the summary, change nothing
  .venv/Scripts/python -I scripts/distil.py --mark   # after Marc approved (or declined) the proposal
Prints per style: counts keep/almost/no, counts per change type, the "why" words, and the prompts of
kept images. Claude turns that into a short proposal (prefer/avoid entries, subjects, wording that worked)
for taste/styles/<style>.json, applies only what Marc approves, reruns build_taste.py, then --mark.
"""
import csv, collections, datetime, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'generated' / 'codex'
STATE = BASE / 'distil-state.json'
sys.path.insert(0, str(ROOT / 'scripts'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

if '--mark' in sys.argv:
    rows = list(csv.DictReader(open(BASE / 'ratings.csv', encoding='utf-8')))
    json.dump({'rows': len(rows), 'marked': datetime.date.today().isoformat()}, open(STATE, 'w'))
    print(f'marked: the next distil starts after rating {len(rows)}')
    sys.exit(0)

from rate import since_last
rows = since_last()
if not rows:
    sys.exit('no ratings since the last distil')
by = collections.defaultdict(list)
for r in rows:
    by[r['style'] or '(no style)'].append(r)
print(f'{len(rows)} ratings since the last distil\n')
for style, rs in sorted(by.items()):
    c = collections.Counter(r['rating'] for r in rs)
    print(f'## {style}: keep {c["keep"]}, almost {c["almost"]}, no {c["no"]}')
    ch = collections.defaultdict(collections.Counter)
    for r in rs:
        ch[r['change'] or '-'][r['rating']] += 1
    for k, v in sorted(ch.items()):
        print(f'  change {k}: keep {v["keep"]}, almost {v["almost"]}, no {v["no"]}')
    for rating in ('keep', 'almost', 'no'):
        whys = [r['why'] for r in rs if r['rating'] == rating and r['why']]
        if whys:
            print(f'  why ({rating}): {"; ".join(whys)}')
    for r in rs:
        if r['rating'] == 'keep':
            print(f'  kept prompt ({r["name"]}): {r["prompt"][:220]}')
    print()
