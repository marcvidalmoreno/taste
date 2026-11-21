"""Style leanings: what Marc's thumbs say about each part of a style's prompt (21 Nov 2026).

Each style has options per axis (light, composition, mood, palette, sometimes detail; taste.json "axes"). An image's
prompt holds one option of each. A thumbs up adds to the options its prompt used, a thumbs down takes away. New runs
(codex_run.py --mix) pick options by these weights, so the style drifts toward what Marc liked while every option
keeps a chance: weight = 2 ** ((up - down) / 2), between 0.25 and 4. Options are matched by their text in the
logged prompt, so a style edit that rewrites an option starts it fresh. Liked and disliked subjects steer the
subjects Codex writes (codex_text.py subjects).

Usage: .venv/Scripts/python -I scripts/leaning.py <style>      # prints the leaning as JSON
Reads generated/codex/ratings.csv (latest mark per image wins) and taste/taste.json; writes nothing.
"""
import csv, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RATINGS = ROOT / 'generated' / 'codex' / 'ratings.csv'
TASTE = ROOT / 'taste' / 'taste.json'


def latest_marks():
    """ratings.csv, latest row per image, cleared marks dropped, in the order of each image's latest row."""
    if not RATINGS.exists():
        return []
    last = {}
    for i, r in enumerate(csv.DictReader(open(RATINGS, encoding='utf-8'))):
        last[(r['batch'], r['name'])] = (i, r)
    return [r for _, r in sorted(last.values(), key=lambda x: x[0]) if r['rating'] != 'cleared']


def subject_of(prompt):
    m = re.search(r'Subject: (.+?)\.(?: |$)', prompt or '')
    return m.group(1) if m else ''


def weight(up, down):
    return max(0.25, min(4.0, 2 ** ((up - down) / 2)))


def leaning(style, taste=None, marks=None):
    taste = taste or json.load(open(TASTE, encoding='utf-8'))['styles']
    st = taste.get(style) or {}
    marks = [r for r in (marks if marks is not None else latest_marks()) if r['style'] == style and r['rating'] in ('keep', 'no')]
    axes = {}
    for axis, opts in (st.get('axes') or {}).items():
        rows = []
        for text in opts:
            up = sum(1 for r in marks if r['rating'] == 'keep' and text in (r['prompt'] or ''))
            down = sum(1 for r in marks if r['rating'] == 'no' and text in (r['prompt'] or ''))
            rows.append({'text': text, 'up': up, 'down': down, 'weight': weight(up, down)})
        axes[axis] = rows
    liked = [s for s in (subject_of(r['prompt']) for r in marks if r['rating'] == 'keep') if s]
    disliked = [s for s in (subject_of(r['prompt']) for r in marks if r['rating'] == 'no') if s]
    return {'style': style, 'ratings': len(marks), 'axes': axes,
            'liked_subjects': list(dict.fromkeys(reversed(liked)))[:8],
            'disliked_subjects': list(dict.fromkeys(reversed(disliked)))[:8]}


def weights(style, taste=None):
    """{axis: [weight per option]} for codex_run.py; all 1.0 when there is nothing to go on."""
    return {axis: [o['weight'] for o in rows] for axis, rows in leaning(style, taste)['axes'].items()}


def matched_axes(style, prompt, taste=None):
    """Which axes of the style this prompt used an option of (what a mark on it moves)."""
    taste = taste or json.load(open(TASTE, encoding='utf-8'))['styles']
    return [axis for axis, opts in ((taste.get(style) or {}).get('axes') or {}).items() if any(t in (prompt or '') for t in opts)]


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps(leaning(sys.argv[1]), indent=1, ensure_ascii=False))
