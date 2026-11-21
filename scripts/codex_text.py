"""Text jobs for Codex CLI (ChatGPT plan, no API key): fresh subjects for a style, or a rewritten image prompt.

Usage (from the project root):
  .venv/Scripts/python -I scripts/codex_text.py subjects --style <style> [--n 4] [--hint "winter, at night"]
  .venv/Scripts/python -I scripts/codex_text.py rewrite --prompt "<old prompt>" --change "<what should change>"
        [--keep subject,palette,composition,light]
  .venv/Scripts/python -I scripts/codex_text.py style --style <style> --change "<what should change>"
  .venv/Scripts/python -I scripts/codex_text.py distil --style <style> --ratings <ratings.json>
        # ratings.json: [{"rating": "keep"|"no", "why": "...", "change": "...", "prompt": "..."}], the ratings of this
        # style since the last distil; answers like style (a proposal), or {"changes": {}} when nothing should change
  add --dry-run to any of them: no Codex call, a stand-in answer at once (for trying the web app)

Prints one JSON object on stdout: {"subjects": [...]}, {"prompt": "...", "summary": "..."} or, for style,
{"changes": {<field>: <new value>}, "summary": "..."}: a proposal only. This script never writes the style; the web
app shows the proposal and applies it after Marc's OK (21 Nov 2026).

Added 21 Nov 2026 (Marc chose "Codex text + queue"): Codex may write subjects and prompts, never style files.
The taste stays with Claude Code: these jobs read taste/styles/*.json and taste/taste.json, write nothing there.
One fresh `codex exec` per job, read-only sandbox, in an empty folder (generated/codex/.text/), low reasoning:
about 10-30 s. One line per job goes to generated/codex/text-runs.csv (git-ignored).
"""
import argparse, csv, datetime, json, random, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'generated' / 'codex'
WORK = BASE / '.text'
LOG = BASE / 'text-runs.csv'

SUBJECTS = """You write subjects for image prompts. Do not run commands, do not read or write files. Answer with JSON only.

Style: {name}
What it is: {description}
Medium: {medium}
Subjects that fit (examples, do not repeat them): {examples}
Never: {avoid}
Already used recently (do not repeat or closely echo): {recent}
Marc rated these up (go further in their direction, new scenes, not copies): {liked}
Marc rated these down (steer away from what they have in common): {disliked}
{hint}
Write {n} new subjects for this style. Each one: a concrete scene in 8-20 words, different from the others in place,
scale and main shape. No text, letters, logos, brands, real named people or characters from films, games or comics.
Answer exactly: {{"subjects": ["...", "..."]}}"""

REWRITE = """You edit one image prompt. Do not run commands, do not read or write files. Answer with JSON only.

Old prompt:
{prompt}

What Marc wants changed: {change}
Keep as it is: {keep}

Rewrite the prompt so it makes that change and nothing else. Keep its structure (first the ratio sentence, then
"Subject: ...", then the style notes) and keep every part that the change does not touch word for word.
If the change contradicts a style note, change that note too. No text, logos or real named people.
Answer exactly: {{"prompt": "<the new prompt>", "summary": "<what you changed, under 15 words>"}}"""


STYLE = """You edit the written description of one visual style that an image model follows. Do not run commands,
do not read or write files. Answer with JSON only.

The style now (JSON):
{style}

What Marc wants changed, after looking at images made with it: {change}

Change only the fields that need it, with the smallest edit that makes the change felt in every image (the
model reads description, light, composition, medium, mood, detail, prefer and avoid; light, composition and mood
are lists of alternatives, one picked per image, so a change meant for every image may need each item, or a
line in "prefer" or "avoid"). Keep each field's type (a list stays a list of short phrases). Keep the language
plain and concrete. Never add text, logos, real named people or named artists.
Answer exactly: {{"changes": {{"<field>": <new value>, ...}}, "summary": "<what you changed, under 20 words>"}}"""

EDITABLE = ('description', 'light', 'composition', 'camera_or_medium', 'mood', 'texture_detail', 'prefer', 'avoid',
            'subjects')


def style_info(key):
    p = ROOT / 'taste' / 'styles' / f'{key}.json'
    if not p.exists():
        sys.exit(f'unknown style "{key}"')
    return json.load(open(p, encoding='utf-8'))


def recent_subjects(style, limit=40):
    """Subjects already used for this style, newest first (from the 'Subject: ...' part of logged prompts)."""
    runs = BASE / 'runs.csv'
    if not runs.exists():
        return []
    out = []
    for r in csv.DictReader(open(runs, encoding='utf-8')):
        if r.get('style') == style:
            m = re.search(r'Subject: (.+?)\.(?: |$)', r.get('prompt') or '')
            if m:
                out.append(m.group(1))
    return list(dict.fromkeys(reversed(out)))[:limit]


def ask(task, text, effort='low'):
    """One codex exec, read-only, empty folder. Returns (answer text, seconds)."""
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f'answer-{int(time.time() * 1000)}.txt'
    cmd = [shutil.which('codex') or 'codex', 'exec', '--skip-git-repo-check', '-s', 'read-only',
           '-c', f'model_reasoning_effort="{effort}"', '-o', str(out)]
    start = time.time()
    res = subprocess.run(cmd, input=text, cwd=WORK, capture_output=True, text=True, encoding='utf-8',
                         errors='replace', timeout=300)
    secs = round(time.time() - start)
    answer = out.read_text(encoding='utf-8') if out.exists() else ''
    out.unlink(missing_ok=True)
    log(task, secs, bool(answer.strip()))
    if not answer.strip():
        tail = (res.stderr or res.stdout or '').strip().splitlines()[-1:] or ['no answer']
        sys.exit(f'Codex gave no answer (exit {res.returncode}): {tail[0][:200]}')
    return answer, secs


def log(task, secs, ok):
    new = not LOG.exists()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(['date', 'time', 'task', 'seconds', 'ok'])
        now = datetime.datetime.now()
        w.writerow([now.date().isoformat(), now.strftime('%H:%M'), task, secs, 'yes' if ok else 'no'])


def parse_json(answer):
    m = re.search(r'\{.*\}', answer, re.S)
    if not m:
        sys.exit('Codex answered without JSON: ' + answer.strip()[:200])
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        sys.exit('Codex answered with broken JSON: ' + answer.strip()[:200])


def clean(s, n=300):
    return ' '.join(str(s).split())[:n]


def subjects(a):
    s = style_info(a.style)
    if a.dry_run:
        pool = list(s.get('subjects') or ['a quiet scene that suits the style'])
        random.shuffle(pool)
        return {'subjects': [f'{pool[i % len(pool)]} (dry run)' for i in range(a.n)], 'seconds': 0, 'dry_run': True}
    try:   # what Marc's thumbs said about earlier subjects of this style (scripts/leaning.py)
        sys.path.insert(0, str(ROOT / 'scripts'))
        from leaning import leaning
        lean = leaning(a.style)
    except Exception:
        lean = {}
    text = SUBJECTS.format(name=s.get('name', a.style), description=s.get('description', ''),
                           medium=s.get('camera_or_medium', ''), examples='; '.join(s.get('subjects') or []),
                           avoid='; '.join(s.get('avoid') or []) or 'nothing listed',
                           recent='; '.join(recent_subjects(a.style)) or 'none yet',
                           liked='; '.join(lean.get('liked_subjects') or []) or 'none yet',
                           disliked='; '.join(lean.get('disliked_subjects') or []) or 'none yet',
                           hint=f'Marc asks for: {a.hint}\n' if a.hint else '', n=a.n)
    answer, secs = ask(f'subjects:{a.style}', text)
    got = [clean(x, 200) for x in parse_json(answer).get('subjects', []) if str(x).strip()]
    if not got:
        sys.exit('Codex returned no subjects')
    return {'subjects': got[:a.n], 'seconds': secs}


def rewrite(a):
    keep = a.keep or 'everything the change does not touch'
    if a.dry_run:
        return {'prompt': f'{a.prompt} Change: {a.change}.', 'summary': f'dry run: added "{a.change}"', 'seconds': 0,
                'dry_run': True}
    answer, secs = ask('rewrite', REWRITE.format(prompt=a.prompt, change=a.change, keep=keep))
    d = parse_json(answer)
    prompt = clean(d.get('prompt', ''), 3000)
    if not prompt:
        sys.exit('Codex returned an empty prompt')
    return {'prompt': prompt, 'summary': clean(d.get('summary', ''), 160), 'seconds': secs}


DISTIL = """You keep the written description of one visual style that an image model follows. Do not run commands,
do not read or write files. Answer with JSON only.

The style now (JSON):
{style}

Marc rated {n} images made with it since the last review ({ups} up, {downs} down). Each line: his thumb, his words
if any, what was picked for that image ("mix l2 c0 m3 p1" = option numbers of light, composition, mood, palette;
"x:" = one part pushed to an extreme; "lean" = picked by earlier ratings), and the prompt:
{ratings}

Find what the ups share and what the downs share. Propose the smallest edits to the style that would give more of
the first and less of the second in every future image: sharpen or replace an option that keeps getting thumbs down,
add a "prefer" line for what the ups share, an "avoid" line for what the downs share. Keep each field's type (lists
stay lists of short phrases), plain concrete language, no text, logos, real named people or named artists. If the
ratings are too few or too mixed to say anything, change nothing.
Answer exactly: {{"changes": {{"<field>": <new value>, ...}}, "summary": "<what the ratings say and what you changed, under 30 words>"}}"""


def validated(now, d):
    """Only real, well-typed edits of the editable fields."""
    out = {}
    for k, v in (d.get('changes') or {}).items():
        if k not in EDITABLE:
            continue
        if isinstance(v, list):
            v = [clean(x, 300) for x in v if clean(x, 300)]
            if not v or (k in now and isinstance(now[k], str) and k != 'texture_detail'):
                continue
        elif isinstance(v, str):
            v = clean(v, 1200)
            if not v or (k in now and isinstance(now[k], list)):
                continue
        else:
            continue
        if v != now.get(k):
            out[k] = v
    return out


def distil(a):
    s = style_info(a.style)
    now = {k: s[k] for k in EDITABLE if k in s}
    rows = json.load(open(a.ratings, encoding='utf-8'))
    ups = sum(1 for r in rows if r.get('rating') == 'keep')
    downs = sum(1 for r in rows if r.get('rating') == 'no')
    if a.dry_run:
        return {'changes': {'prefer': list(s.get('prefer') or []) + [f'dry run: {ups} up, {downs} down']},
                'summary': f'dry run: {ups} up, {downs} down; a stand-in line added to lean towards', 'seconds': 0, 'dry_run': True}
    lines = '\n'.join(f"- {'UP' if r.get('rating') == 'keep' else 'DOWN'}"
                      + (f" ({clean(r.get('why'), 200)})" if r.get('why') else '')
                      + f" [{clean(r.get('change'), 80) or '-'}] {clean(r.get('prompt'), 900)}" for r in rows[-24:])
    answer, secs = ask(f'distil:{a.style}', DISTIL.format(style=json.dumps(now, indent=1, ensure_ascii=False), n=len(rows),
                                                         ups=ups, downs=downs, ratings=lines), effort='medium')
    d = parse_json(answer)
    return {'changes': validated(now, d), 'summary': clean(d.get('summary', ''), 300), 'seconds': secs}


def style_edit(a):
    s = style_info(a.style)
    now = {k: s[k] for k in EDITABLE if k in s}
    if a.dry_run:
        return {'changes': {'prefer': list(s.get('prefer') or []) + [a.change]},
                'summary': f'dry run: added "{a.change}" to lean towards', 'seconds': 0, 'dry_run': True}
    answer, secs = ask(f'style:{a.style}', STYLE.format(style=json.dumps(now, indent=1, ensure_ascii=False), change=a.change))
    d = parse_json(answer)
    out = {}
    for k, v in (d.get('changes') or {}).items():   # keep only real, well-typed edits
        if k not in EDITABLE:
            continue
        if isinstance(v, list):
            v = [clean(x, 300) for x in v if clean(x, 300)]
            if not v or (k in now and isinstance(now[k], str) and k != 'texture_detail'):
                continue
        elif isinstance(v, str):
            v = clean(v, 1200)
            if not v or (k in now and isinstance(now[k], list)):
                continue
        else:
            continue
        if v != now.get(k):
            out[k] = v
    if not out:
        sys.exit('Codex proposed no change to the style')
    return {'changes': out, 'summary': clean(d.get('summary', ''), 200), 'seconds': secs}


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('subjects')
    s.add_argument('--style', required=True)
    s.add_argument('--n', type=int, default=4)
    s.add_argument('--hint', default='')
    s.add_argument('--dry-run', action='store_true')
    r = sub.add_parser('rewrite')
    r.add_argument('--prompt', required=True)
    r.add_argument('--change', required=True)
    r.add_argument('--keep', default='')
    r.add_argument('--dry-run', action='store_true')
    e = sub.add_parser('style')
    e.add_argument('--style', required=True)
    e.add_argument('--change', required=True)
    e.add_argument('--dry-run', action='store_true')
    t = sub.add_parser('distil')
    t.add_argument('--style', required=True)
    t.add_argument('--ratings', required=True)
    t.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    a.n = max(1, min(12, getattr(a, 'n', 4)))
    run = {'subjects': subjects, 'rewrite': rewrite, 'style': style_edit, 'distil': distil}[a.cmd]
    print(json.dumps(run(a), ensure_ascii=False))
