"""Text jobs for Codex CLI (ChatGPT plan, no API key): fresh subjects for a style, or a rewritten image prompt.

Usage (from the project root):
  .venv/Scripts/python -I scripts/codex_text.py subjects --style <style> [--n 4] [--hint "winter, at night"] [--wild]
  .venv/Scripts/python -I scripts/codex_text.py rewrite --prompt "<old prompt>" --change "<what should change>"
        [--keep subject,palette,composition,light]
  .venv/Scripts/python -I scripts/codex_text.py rewrite --image <file> --change "<what should change>" [--style <style>]
        # no prompt on record: Codex looks at the image and writes a prompt for it with the change made (23 Nov 2026)
  .venv/Scripts/python -I scripts/codex_text.py style --style <style> --change "<what should change>"
  .venv/Scripts/python -I scripts/codex_text.py distil --style <style> --ratings <ratings.json>
        # ratings.json: [{"rating": "keep"|"no", "why": "...", "change": "...", "prompt": "..."}], the ratings of this
        # style since the last distil; answers like style (a proposal), or {"changes": {}} when nothing should change
  .venv/Scripts/python -I scripts/codex_text.py new --images ref-1.jpg [ref-2.jpg ...] [--name "..."] [--notes "..."]
        # a whole new style from 1-4 reference images (Codex looks at them); answers {"style": {...}, "summary": "..."}
  .venv/Scripts/python -I scripts/codex_text.py fork --style <style> --change "<what should differ>" [--name "..."]
        # a variant of a style (24 Nov 2026): answers {"style": {...whole style, parent's shape...}, "summary": "..."}
  .venv/Scripts/python -I scripts/codex_text.py compose --text "<what Marc wants>" --palette "#112233,#aabbcc" --ratio "<sentence>"
        # palette only, no style (24 Nov 2026): Codex writes the whole prompt from Marc's text and the palette
  add --dry-run to any of them: no Codex call, a stand-in answer at once (for trying the web app)
  add --local to subjects, rewrite (with --prompt) or compose: a local Ollama model writes it instead of Codex, no
        tokens (the web app's "Local only", 25 Nov 2026). ComfyUI's models are unloaded first and Ollama is called with
        keep_alive 0, so the two never hold the laptop's shared memory at once. Model: TASTE_TEXT_MODEL, else the
        first of LOCAL_TEXT_MODELS that Ollama has.

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
OLLAMA = 'http://127.0.0.1:11434'
LOCAL_TEXT_MODELS = ['qwen3:8b', 'qwen2.5-coder:7b', 'qwen2.5-coder:14b']   # first one installed wins
LOCAL = [False]   # --local: ask() goes to Ollama

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

# Experimental runs (23 Nov 2026): subjects pushed a bit to the extreme, still recognisably this style.
WILD = ('This is an experimental run: push each subject a bit to the extreme. Unusual places, odd scales, surprising '
        'pairings, strange weather or times, a touch of the surreal; still something this style could paint. '
        'Make them clearly bolder than the examples and the subjects used before.\n')

REWRITE = """You edit one image prompt. Do not run commands, do not read or write files. Answer with JSON only.

Old prompt:
{prompt}

What Marc wants changed: {change}
Keep as it is: {keep}

Rewrite the prompt so it makes that change and nothing else. Keep its structure (first the ratio sentence, then
"Subject: ...", then the style notes) and keep every part that the change does not touch word for word.
If the change contradicts a style note, change that note too. No text, logos or real named people.
Answer exactly: {{"prompt": "<the new prompt>", "summary": "<what you changed, under 15 words>"}}"""

DESCRIBE = """You write one image prompt. Do not run commands, do not read or write files. Answer with JSON only.

The attached image has no prompt on record. Write a prompt that would make an image like it, with this change made:
{change}
Keep as it is: {keep}
{style}
Structure: first one sentence with the ratio and use (e.g. "Wide 16:9 desktop wallpaper." or "Tall 9:16 phone
wallpaper.", matching the image's shape), then "Subject: ..." (what the image shows, with the change made), then
"Style notes: ..." (medium, light, composition, palette, mood, as the image shows them). Plain, concrete words.
Never name artists, studios, brands or real people. No text or logos.
Answer exactly: {{"prompt": "<the prompt>", "summary": "<what you changed against the image, under 15 words>"}}"""


# Palette only (24 Nov 2026): no style, Marc writes what he wants in his own words and picks a palette in New run.
COMPOSE = """You write one image prompt from a short text. Do not run commands, do not read or write files. Answer with JSON only.

What Marc wants: {text}
Palette (use these colours and nothing far from them): {palette}

Write the prompt an image model will follow. Structure: first exactly this sentence: "{ratio}", then
"Subject: ..." (what the image shows, concrete, from Marc's text), then "Style notes: ..." (medium, light,
composition, mood and texture that suit the text; then "Palette: " with the colours above, as hex codes, and how
they are used). Keep everything Marc asked for; add only what the text leaves open. Plain, concrete words, under
120 words. Never name artists, studios, brands or real people. End with "No text, no logos, no watermark."
Answer exactly: {{"prompt": "<the prompt>", "summary": "<what you added to the text, under 15 words>"}}"""


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


def example_style(key='quiet-landscapes'):
    """The worked example shown to Codex for a new style. It still works when that style is archived or deleted
    (25 Nov 2026: archiving quiet-landscapes broke "Propose the style")."""
    styles = ROOT / 'taste' / 'styles'
    for p in (styles / f'{key}.json', styles / 'archived' / f'{key}.json', *sorted(styles.glob('*.json'))):
        if p.exists():
            return json.load(open(p, encoding='utf-8'))
    sys.exit('no style to show Codex as an example')


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


def ollama(path, body=None, timeout=10):
    import urllib.request
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def local_model():
    """The Ollama model for text jobs; starts Ollama hidden if it isn't running."""
    try:
        have = [m['name'] for m in ollama('/api/tags')['models']]
    except OSError:
        subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x08000000 if sys.platform == 'win32' else 0)
        for _ in range(20):
            time.sleep(1)
            try:
                have = [m['name'] for m in ollama('/api/tags')['models']]
                break
            except OSError:
                continue
        else:
            sys.exit('Ollama is not running and did not start')
    import os
    want = os.environ.get('TASTE_TEXT_MODEL')
    for m in ([want] if want else []) + LOCAL_TEXT_MODELS:
        if m in have:
            return m
    sys.exit('no local text model in Ollama (wanted one of: ' + ', '.join(LOCAL_TEXT_MODELS) + ')')


def ask_local(task, text):
    """One Ollama call, JSON answer, keep_alive 0 (unloads right after). ComfyUI's models are unloaded first."""
    try:
        sys.path.insert(0, str(ROOT / 'scripts'))
        import local_run
        local_run.free(quiet=True)
    except Exception:
        pass
    model = local_model()
    start = time.time()
    try:
        d = ollama('/api/generate', {'model': model, 'prompt': text, 'stream': False, 'format': 'json',
                                     'keep_alive': 0, 'think': False, 'options': {'temperature': 0.8}}, timeout=300)
    except OSError as e:
        log(f'{task} (local)', round(time.time() - start), False)
        sys.exit(f'the local model ({model}) gave no answer: {e}')
    secs = round(time.time() - start)
    answer = d.get('response', '')
    log(f'{task} (local {model})', secs, bool(answer.strip()))
    if not answer.strip():
        sys.exit(f'the local model ({model}) gave no answer')
    return answer, secs


def ask(task, text, effort='low', images=()):
    """One codex exec, read-only, empty folder, images attached if any. Returns (answer text, seconds).
    With --local (text only): the local Ollama model instead."""
    if LOCAL[0]:
        if images:
            sys.exit('looking at an image uses ChatGPT tokens – turn off Local only')
        return ask_local(task, text)
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f'answer-{int(time.time() * 1000)}.txt'
    cmd = [shutil.which('codex') or 'codex', 'exec', '--skip-git-repo-check', '-s', 'read-only',
           '-c', f'model_reasoning_effort="{effort}"', '-o', str(out)]
    for img in images:
        cmd += ['-i', img]
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
    answer, secs = ask(f'subjects{"-wild" if a.wild else ""}:{a.style}', text)
    got = [clean(x, 200) for x in parse_json(answer).get('subjects', []) if str(x).strip()]
    if not got:
        sys.exit('Codex returned no subjects')
    return {'subjects': got[:a.n], 'seconds': secs}


def rewrite(a):
    keep = a.keep or 'everything the change does not touch'
    if not a.prompt and not a.image:
        sys.exit('give --prompt or --image')
    if a.dry_run:
        old = a.prompt or 'Wide 16:9 desktop wallpaper. Subject: what the image shows (dry run).'
        return {'prompt': f'{old} Change: {a.change}.', 'summary': f'dry run: added "{a.change}"', 'seconds': 0,
                'dry_run': True}
    if a.prompt:
        answer, secs = ask('rewrite', REWRITE.format(prompt=a.prompt, change=a.change, keep=keep))
    else:   # no prompt on record: Codex looks at the image and writes one with the change made
        style = ''
        if a.style:
            s = style_info(a.style)
            style = (f'It was made in this style, use it for the style notes: {s.get("description", "")} '
                     f'Medium: {s.get("camera_or_medium", "")}\n')
        answer, secs = ask('describe', DESCRIBE.format(change=a.change, keep=keep, style=style),
                           images=[str(Path(a.image).resolve())])
    d = parse_json(answer)
    prompt = clean(d.get('prompt', ''), 3000)
    if not prompt:
        sys.exit('Codex returned an empty prompt')
    return {'prompt': prompt, 'summary': clean(d.get('summary', ''), 160), 'seconds': secs}


def compose(a):
    palette = ', '.join(c for c in a.palette.split(',') if re.fullmatch(r'#[0-9a-fA-F]{6}', c.strip()))
    if not palette:
        sys.exit('give --palette as hex codes, e.g. #112233,#aabbcc,#ffffff')
    if a.dry_run:
        return {'prompt': f'{a.ratio} Subject: {a.text} (dry run). Style notes: Palette: {palette}. No text, no logos, no watermark.',
                'summary': 'dry run stand-in', 'seconds': 0, 'dry_run': True}
    answer, secs = ask('compose', COMPOSE.format(text=a.text, palette=palette, ratio=a.ratio))
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


NEW = """You describe one visual style in words, so that an image model can reproduce the look. The attached
images are references Marc collected because they share a look he likes. Do not run commands, do not read or write
files. Answer with JSON only.

Marc's name for it: {name}
What draws Marc to them: {notes}

Describe the look itself (medium, line and edge, light, colour, composition, mood, texture), not just what the
images show, so the style works for any subject. Never name artists, illustrators, photographers, studios, brands,
real people, films or the source of the images, and never write "in the style of". Plain, concrete words.
- name: Marc's name if he gave one, else a short plain name (2-4 words)
- description: one or two sentences, what the style is
- palette: 5-7 hex colours seen in the references, dark to light
- light, composition, mood: 4 alternatives each, every one true to the references, each clearly different
- camera_or_medium, texture_detail: one short phrase each
- prefer: 2-4 lines for what most defines the look
- avoid: 3-6 things that would break the look; always include "text and logos"
- subjects: 5 concrete scenes of 8-20 words that suit the style and are not copies of the references
- use: from "desktop", "teams", "phone", "post", the ones the look suits
Another style, for the form only:
{example}
Answer exactly: {{"style": {{"name": "...", "description": "...", "palette": ["#..."], "light": ["..."],
"composition": ["..."], "camera_or_medium": "...", "mood": ["..."], "texture_detail": "...", "prefer": ["..."],
"avoid": ["..."], "subjects": ["..."], "use": ["..."]}}, "summary": "<what the references share, under 25 words>"}}"""

NEW_LISTS = ('light', 'composition', 'mood', 'prefer', 'avoid', 'subjects')
NEW_TEXTS = ('name', 'description', 'camera_or_medium', 'texture_detail')
USES = ('desktop', 'teams', 'phone', 'post')


def new_fields(d):
    """A whole style from Codex's answer, typed like the files in taste/styles (lists stay lists)."""
    out = {}
    for k in NEW_TEXTS:
        v = d.get(k)
        out[k] = clean(' '.join(v) if isinstance(v, list) else v or '', 80 if k == 'name' else 1200)
    for k in NEW_LISTS:
        v = d.get(k) or []
        out[k] = [clean(x, 300) for x in (v if isinstance(v, list) else [v]) if clean(x, 300)][:8]
    out['palette'] = [x.lower() for x in (d.get('palette') or []) if re.fullmatch(r'#[0-9a-fA-F]{6}', str(x))][:7]
    out['use'] = [u for u in (d.get('use') or []) if u in USES] or ['desktop']
    if not any('text' in a.lower() for a in out['avoid']):
        out['avoid'].append('text and logos')
    return out


def new_style(a):
    images = [str(Path(p).resolve()) for p in a.images][:4]
    if a.dry_run:
        name = a.name or 'New style (dry run)'
        return {'style': new_fields({
            'name': name, 'description': f'Dry run stand-in for {len(images)} reference image(s). {a.notes}'.strip(),
            'palette': ['#1d1c22', '#4a4652', '#8a7f8c', '#c9b8a8', '#efe6dc'],
            'light': ['soft dusk light', 'flat overcast light', 'low warm sun', 'cool moonlight'],
            'composition': ['one subject, wide empty space', 'low horizon', 'close crop', 'high viewpoint'],
            'camera_or_medium': 'flat digital illustration', 'mood': ['calm', 'wistful', 'quiet', 'hopeful'],
            'texture_detail': 'clean flat shapes, faint grain', 'prefer': ['few elements'],
            'avoid': ['busy detail'], 'subjects': ['a lighthouse on a quiet headland at dusk (dry run)'],
            'use': ['desktop']}), 'summary': 'dry run: a stand-in style, Codex was not asked', 'seconds': 0, 'dry_run': True}
    example = json.dumps({k: v for k, v in example_style().items() if k != 'palettes'}, indent=1,
                         ensure_ascii=False)
    text = NEW.format(name=a.name or 'none given', notes=a.notes or 'not said', example=example)
    answer, secs = ask('new', text, effort='medium', images=images)
    d = parse_json(answer)
    st = new_fields(d.get('style') or d)
    missing = [k for k in ('description', 'light', 'composition', 'mood', 'camera_or_medium') if not st[k]]
    if missing:
        sys.exit('Codex left out ' + ', '.join(missing))
    return {'style': st, 'summary': clean(d.get('summary', ''), 300), 'seconds': secs}


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


FORK = """You write a variant of one visual style that an image model follows. Do not run commands, do not read or
write files. Answer with JSON only.

The style now (JSON, the parent):
{style}

The variant is called: {name}
What Marc wants to be different in the variant: {change}

Write the whole variant. Keep everything the change does not touch word for word. Make the change felt in every
field it touches: the description, light, composition, mood, detail, prefer and avoid (light, composition and mood
are lists of alternatives, one picked per image, so a change meant for every image may need each item). Change
the colours only if the change asks for it (a new "palette" of 5-7 hex colours, and "palettes" with it if the
parent has them, the first one equal to "palette"). Keep each field's type (a list stays a list of short phrases).
Plain, concrete words. Never add text, logos, real named people or named artists. Give the variant a "name" (short).
Answer exactly: {{"style": {{<every field of the parent, with the variant's values>}}, "summary": "<what differs from the parent, under 25 words>"}}"""

FORK_TEXTS = ('description', 'camera_or_medium')


def fork_fields(parent, d, name=''):
    """The parent's file, whole, with Codex's values where they have the same type; the parent's shape stays."""
    hexes = lambda v: [x.lower() for x in (v if isinstance(v, list) else []) if re.fullmatch(r'#[0-9a-fA-F]{6}', str(x))][:7]  # noqa: E731
    out = {}
    for k, v in parent.items():
        n = d.get(k)
        if k == 'name':
            out[k] = clean(name or n or v, 80)
        elif k == 'palette':
            out[k] = hexes(n) if len(hexes(n)) >= 3 else v
        elif k == 'palettes':
            ps = [hexes(p) for p in n] if isinstance(n, list) and all(isinstance(p, list) for p in n) else []
            out[k] = [p for p in ps if len(p) >= 3] or v
        elif k == 'use':
            out[k] = [u for u in (n if isinstance(n, list) else []) if u in USES] or v
        elif isinstance(v, list):
            lst = [clean(x, 300) for x in (n if isinstance(n, list) else []) if clean(x, 300)][:8]
            out[k] = lst or v
        elif isinstance(v, str):
            out[k] = clean(n, 1200) if isinstance(n, str) and clean(n, 1200) else v
        else:
            out[k] = v
    if out.get('palettes') and out.get('palette') and out['palettes'][0] != out['palette']:
        out['palettes'] = [out['palette']] + out['palettes'][1:]   # palette is always palettes[0]
    return out


def fork_style(a):
    parent = style_info(a.style)
    name = clean(a.name, 80) or f"{parent.get('name', a.style)} (fork)"
    if a.dry_run:
        st = fork_fields(parent, {'description': f"{parent.get('description', '')} (dry run: {a.change})"}, name)
        return {'style': st, 'summary': f'dry run: the description carries "{a.change}"; Codex was not asked',
                'seconds': 0, 'dry_run': True}
    answer, secs = ask(f'fork:{a.style}', FORK.format(style=json.dumps(parent, indent=1, ensure_ascii=False), name=name,
                                                     change=a.change), effort='medium')
    d = parse_json(answer)
    st = fork_fields(parent, d.get('style') or d, name)
    if st == {**parent, 'name': name}:
        sys.exit('Codex proposed no difference from the parent')
    return {'style': st, 'summary': clean(d.get('summary', ''), 300), 'seconds': secs}


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('subjects')
    s.add_argument('--style', required=True)
    s.add_argument('--n', type=int, default=4)
    s.add_argument('--hint', default='')
    s.add_argument('--wild', action='store_true', help='experimental: subjects pushed a bit to the extreme')
    s.add_argument('--dry-run', action='store_true')
    r = sub.add_parser('rewrite')
    r.add_argument('--prompt', default='')
    r.add_argument('--image', default='')
    r.add_argument('--style', default='')
    r.add_argument('--change', required=True)
    r.add_argument('--keep', default='')
    r.add_argument('--dry-run', action='store_true')
    c = sub.add_parser('compose')
    c.add_argument('--text', required=True)
    c.add_argument('--palette', required=True, help='hex codes, comma-separated')
    c.add_argument('--ratio', required=True, help='the ratio sentence the prompt starts with')
    c.add_argument('--dry-run', action='store_true')
    e = sub.add_parser('style')
    e.add_argument('--style', required=True)
    e.add_argument('--change', required=True)
    e.add_argument('--dry-run', action='store_true')
    t = sub.add_parser('distil')
    t.add_argument('--style', required=True)
    t.add_argument('--ratings', required=True)
    t.add_argument('--dry-run', action='store_true')
    w = sub.add_parser('new')
    w.add_argument('--images', nargs='+', required=True)
    w.add_argument('--name', default='')
    w.add_argument('--notes', default='')
    w.add_argument('--dry-run', action='store_true')
    f = sub.add_parser('fork')
    f.add_argument('--style', required=True)
    f.add_argument('--change', required=True)
    f.add_argument('--name', default='')
    f.add_argument('--dry-run', action='store_true')
    for sp in (s, r, c):
        sp.add_argument('--local', action='store_true', help='a local Ollama model writes it (no tokens)')
    a = ap.parse_args()
    LOCAL[0] = bool(getattr(a, 'local', False))
    a.n = max(1, min(24, getattr(a, 'n', 4)))
    run = {'subjects': subjects, 'rewrite': rewrite, 'compose': compose, 'style': style_edit, 'distil': distil, 'new': new_style, 'fork': fork_style}[a.cmd]
    print(json.dumps(run(a), ensure_ascii=False))
