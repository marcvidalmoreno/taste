"""Generate one image with Codex CLI (Marc's ChatGPT plan, no API key) and log the run.

Usage (from the project root):
  .venv/Scripts/python -I scripts/codex_run.py gen --out generated/codex/<batch> --name <name> --prompt "<text>"
        [--ref <seed image>] [--ref <more> --refs-kept] [--style <style>] [--mode variations|text|test] [--change "<what this one changes>"]
  .venv/Scripts/python -I scripts/codex_run.py gen --out ... --name ... --style <style> --subject "<scene>"
        [--ratio wide|square|portrait] [--look N]   # prompt from taste/taste.json; N picks one of the style's looks
        [--mix SEED] [--extreme light|framing|palette|scale|detail|mood]
        # --mix: light, framing, mood and palette each picked on their own (seeded, so repeatable);
        # --extreme: push one dimension to an extreme, the rest of the style unchanged. Both go in "change".
  .venv/Scripts/python -I scripts/codex_run.py read      # usage now, from the newest Codex session log
  gen --route cloudflare (or TASTE_ROUTE=cloudflare): the same prompt made by FLUX on Cloudflare (scripts/cf_run.py);
        the "route" column of runs.csv says which; for cloudflare, "tokens" holds the estimated neurons.
  gen --route local --model klein|zimage|playground|dreamshaper|juggernaut|zavychroma|animagine (or TASTE_ROUTE=local TASTE_MODEL=...): the same prompt made by
        an open model on this laptop through ComfyUI (scripts/local_run.py); session "local:<model>", no tokens.

One fresh `codex exec` per image. Codex only generates and copies the PNG into --out; it never views the
result and never touches the taste files. Afterwards this script reads tokens and the five-hour / weekly
allowance from Codex's own session log (~/.codex/sessions) and the PNG's real pixel size, and appends
one row to generated/codex/runs.csv (git-ignored). Numbers are never typed by hand.
One recovery only: if the PNG is not in --out, copy it from ~/.codex/generated_images/<session>/.
Otherwise the run is logged as failed; stop and report, do not loop.
"""
import argparse, csv, datetime, json, os, random, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from progress import Progress, is_child  # noqa: E402
LOG = ROOT / 'generated' / 'codex' / 'runs.csv'
CODEX = Path.home() / '.codex'
HEADER = ['date', 'time', 'batch', 'name', 'mode', 'style', 'change', 'seed', 'ok', 'width', 'height',
          'tokens', 'five_hour_first', 'five_hour_last', 'weekly_first', 'weekly_last', 'seconds', 'session', 'prompt', 'route']
ROUTES = ['codex', 'cloudflare', 'local']   # cloudflare: scripts/cf_run.py, FLUX on Workers AI's free allowance (23 Nov 2026)
LOCAL_MODELS = ['klein', 'zimage', 'playground', 'dreamshaper', 'juggernaut', 'zavychroma', 'animagine']   # local: scripts/local_run.py, open models in ComfyUI (25 Nov 2026)

JOB = """Image job. Use the image_gen tool exactly once. Do not write code to draw, do not view, open or describe the result, and do not create or edit any other file.
{ref}Image prompt: {prompt}
When it is done, copy the generated PNG to {name}.png in the current directory. Reply with the file name only."""
REF = ('The attached image ({path}) is the seed: pass it to image_gen as referenced_image_paths. '
       'Keep its overall look unless the prompt says what to change; make a new image, not a copy.\n')
REF_KEPT = ('The attached images ({paths}) are examples of the look wanted: pass them to image_gen as '
            "referenced_image_paths. Match their palette, light and feel; make a new image of the prompt's subject, not a copy.\n")


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


# One dimension pushed to an extreme (a wildcard image). Several concrete options per dimension; the seed picks one.
EXTREMES = {
    'light': ['a single hard light from very low on one side, long deep shadows',
              'deep night, the scene lit only by one small source',
              'strong backlight, the main shapes almost in silhouette against the glow',
              'blinding high-key light, everything pale and washed out'],
    'framing': ['an extreme close-up, the main shape cropped by the edges',
                'the main shape tiny, lost in a vast empty space',
                "a steep bird's-eye view straight down",
                "a low worm's-eye view looking up"],
    'palette': ['only two colours of the palette plus black or white',
                'near-monochrome: one hue of the palette in many shades',
                'the palette at full saturation, every colour at its loudest',
                'the palette faded almost to grey, one colour kept bright'],
    'scale': ['something enormous next to something tiny',
              'one element blown up to fill the whole frame',
              'a crowd of very many small repeated elements'],
    'detail': ['extremely dense and intricate, every part filled',
               'stripped to the barest minimum, a few shapes on a plain ground'],
    'mood': ['the mood pushed to its most intense version',
             'the opposite mood to the usual one for this style, kept in the same medium'],
}


# Experimental runs (23 Nov 2026): a palette the style never uses, in place of its own. The seed picks one per image.
NEW_PALETTES = [
    'deep indigo, saffron yellow, coral and bone white',
    'acid lime, plum, charcoal and pale pink',
    'burnt orange, teal, cream and ink black',
    'cobalt blue, vermilion red and warm off-white only',
    'mint green, lilac, butter yellow and soft grey',
    'oxblood, mustard, olive and parchment',
    'electric magenta, cyan and near-black',
    'sage, terracotta, sand and dusty blue',
    'emerald, gold leaf, black lacquer and ivory',
    'peach, cornflower blue, chocolate brown and white',
    'fluorescent orange, slate grey and icy blue',
    'rust, petrol blue, pale ochre and chalk',
]


AXIS = {'light': 'light', 'framing': 'composition', 'palette': 'palette', 'mood': 'mood'}  # extreme -> template slot


def lean_weights(style, taste):
    try:
        from leaning import weights
        return weights(style, taste)
    except Exception:   # no ratings file yet, or a bad row: pick evenly rather than fail the run
        return {}


def spread(rnd, w, length):
    """A sequence of option numbers: weighted picks, each pick cutting that option's weight to a third, so a batch
    still varies (with even weights: nearly every option once before a repeat) while liked options come up more."""
    w, out = list(w), []
    for _ in range(length):
        i = rnd.choices(range(len(w)), weights=w)[0] if len(w) > 1 else 0
        out.append(i)
        w[i] /= 3
    return out


def new_palette(a, rnd):
    a.new_palette_i = (rnd or random.Random()).randrange(len(NEW_PALETTES))
    return f'Palette: {NEW_PALETTES[a.new_palette_i]} (a new palette for this style, used boldly).'


def compose(a):
    """Short prompt: ratio + subject + one style block from the generated taste file.
    With --mix or --extreme, a.change records what was picked (e.g. "mix l2 c0 m3 p1 x:light1")."""
    taste = json.load(open(ROOT / 'taste' / 'taste.json', encoding='utf-8'))['styles']
    if a.style not in taste:
        sys.exit(f'unknown style "{a.style}"; pick one of: {", ".join(taste)}')
    st = taste[a.style]
    rnd = random.Random(f'{a.mix}-{a.style}-{a.name}') if a.mix is not None else None
    wild = ''
    if a.extreme:
        opts = EXTREMES[a.extreme]
        i = (rnd or random.Random()).randrange(len(opts))
        wild = f'Wildcard: push the {a.extreme} to an extreme: {opts[i]}. Keep everything else in this style.'
    leaned = False
    if st.get('axes') and (rnd or a.extreme):
        # Leaning (21 Nov 2026): options Marc rated up weigh more, rated down less (scripts/leaning.py).
        w = {} if a.no_lean else lean_weights(a.style, taste)
        leaned = any(abs(x - 1) > 1e-9 for ws in w.values() for x in ws if len(ws) > 1)
        if rnd and a.slot is not None:
            # spread: one order per axis for the whole style (same seed); image K takes entry K of each. Each pick
            # halves that option's weight for the next, so a batch still varies, but liked options come up more
            # often and disliked ones less (with no ratings: every option once before any repeats, as before).
            srnd = random.Random(f'{a.mix}-{a.style}')
            order = {k: spread(srnd, w.get(k) or [1.0] * len(v), a.slot + 1) for k, v in st['axes'].items()}
            pick = {k: order[k][a.slot] for k in order}
        else:
            pick = {k: (rnd.choices(range(len(v)), weights=(w.get(k) or [1.0] * len(v)))[0] if rnd else (a.look or 0) % len(v))
                    for k, v in st['axes'].items()}
        fill = {k: st['axes'][k][i] for k, i in pick.items()}
        slot = AXIS.get(a.extreme)
        if a.new_palette and 'palette' in fill:
            fill['palette'] = new_palette(a, rnd)
            pick.pop('palette', None)
        if slot:  # the wildcard replaces its own axis, so the prompt never asks for two lights at once
            fill[slot], wild = wild, ''
            pick.pop(slot)
        block = st['template'].format(**fill)
        tags = (['mix'] if rnd else []) + (['lean'] if leaned else []) + [f'{k[0]}{i}' for k, i in pick.items()]  # l(ight) c(omposition) m(ood) p(alette)
    else:
        looks = st.get('looks') or [st['prompt']]
        block = looks[a.look % len(looks)] if a.look is not None else st['prompt']
        tags = []
    if a.new_palette and not (st.get('axes') and (rnd or a.extreme) and 'palette' in st['axes']):
        block += ' ' + new_palette(a, rnd)
    if a.new_palette:
        tags.insert(0, f'newpal{a.new_palette_i}')
    if wild:
        block += ' ' + wild
    if a.extreme:
        tags.append(f'x:{a.extreme}{i}')
    if tags:
        a.change = ' '.join(tags + ([a.change] if a.change else []))
    return f"{RATIOS[a.ratio]} Subject: {a.subject}. {block}"


def gen(a):
    if not a.prompt:
        if not (a.style and a.subject):
            sys.exit('give --prompt, or --style and --subject')
        a.prompt = compose(a)
    if a.print:
        print(json.dumps({'name': a.name, 'change': a.change, 'prompt': a.prompt,
                          'refs': [Path(r).name for r in a.ref] if a.refs_kept else []}, ensure_ascii=False))
        return
    out = (ROOT / a.out).resolve() if not os.path.isabs(a.out) else Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    refs = [Path(r).resolve() for r in a.ref]
    ref = refs[0] if refs else None
    if a.refs_kept and refs:
        note = REF_KEPT.format(paths=', '.join(str(r) for r in refs))
    else:
        note = REF.format(path=ref) if ref else ''
    if a.route == 'cloudflare':
        return gen_cloudflare(a, out, refs, ref)
    if a.route == 'local':
        return gen_local(a, out, refs, ref)
    job = JOB.format(ref=note, prompt=a.prompt, name=a.name)
    cmd = [shutil.which('codex') or 'codex', 'exec', '--skip-git-repo-check', '-s', 'workspace-write']
    for r in refs:
        cmd += ['-i', str(r)]
    prog = None
    if not is_child():  # run alone from chat: show it in the web app (batch.py / variations.py do it otherwise)
        prog = Progress(out, [a.name], a.mode)
        prog.begin(a.name, a.subject or a.change)
    start = time.time()
    try:
        res = subprocess.run(cmd, input=job, cwd=out, capture_output=True, text=True, encoding='utf-8',
                             errors='replace', timeout=900)
    except subprocess.TimeoutExpired as e:   # say so in the log and runs.csv, so the web app can tell (23 Nov 2026)
        tail = lambda x: (x.decode('utf-8', 'replace') if isinstance(x, bytes) else x or '')  # noqa: E731
        res = subprocess.CompletedProcess(cmd, 124, tail(e.stdout), tail(e.stderr) + '\nTIMED OUT: codex exec ran over 900 s and was stopped')
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
           ('kept ' + ' + '.join(r.name for r in refs)) if (a.refs_kept and refs) else ref.name if ref else '', 'yes' if png.exists() else 'no', w, h, last[0] if last[0] is not None else '',
           first[1], last[1], first[2], last[2], secs, sid, a.prompt, 'codex']
    log_row(row)
    print(json.dumps(dict(zip(HEADER[:18], row[:18]))))
    if prog:
        prog.ok(a.name) if png.exists() else prog.fail(a.name, f'Codex exit code {res.returncode}')
        prog.end()
    if not png.exists():
        print(f'FAILED: no image. Codex exit code {res.returncode}; see {a.name}.codex.log', file=sys.stderr)
        sys.exit(2)


def log_row(row):
    """Append one row to runs.csv. Adds the "route" column to an older header once (old rows read as codex)."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if LOG.exists():
        with open(LOG, encoding='utf-8', newline='') as fh:
            head, rest = fh.readline(), fh.read()
        if head.strip() and 'route' not in head.strip().split(','):
            with open(LOG, 'w', encoding='utf-8', newline='') as fh:
                fh.write(head.rstrip('\r\n') + ',route\r\n' + rest)
    new = not LOG.exists()
    with open(LOG, 'a', encoding='utf-8', newline='') as fh:
        wr = csv.writer(fh)
        if new:
            wr.writerow(HEADER)
        wr.writerow(row)


FLUX_REFS, FLUX_POOL = 3, 12   # examples per FLUX image; how many recent ones it turns through
FLUX_STYLE_ONLY = ('The attached images show only the style to match: palette, linework, texture and light. '
                   'Make one new, single scene from the description below. Do not copy the attached images, '
                   'do not combine them and do not place them side by side. ')   # 23 Nov 2026: 2 of 18 came out stitched
# A FLUX remix of one image: FLUX edits the seed, so it gets Marc's change as a short edit instruction, not the
# full scene prompt (with it, 4 of 4 came out as copies and the change was lost; 23 Nov 2026).
FLUX_EDIT = ('Edit the attached image. Make this change, clearly visible: {}. '
             'Keep everything else as it is: the same person, pose, setting, palette and drawing style.')


# People on FLUX (23 Nov 2026): klein 4B merged feet and bent bodies, copied a flawed seed's anatomy, and got
# "Avoid: people in frame" from rooms styles while drawing a person. When the image has a person: that Avoid
# item goes, a positive anatomy line is added (FLUX has no negative prompt), and a subject change that names
# a body part becomes an edit that may re-pose the body instead of "keep the composition of the seed".
PERSON = re.compile(r'\b(woman|women|man|men|person|people|girl|boy|lady|figure|model|she|he|her|his|nude|body|'
                    r'bodies|torso|feet|foot|toes|legs?|arms?|hands?|fingers|portrait|lying|reclin\w*|sitting|posing)\b', re.I)
BODY_PART = re.compile(r'\b(feet|foot|toes?|legs?|knees?|hands?|fingers?|arms?|body|anatomy|pose|limbs?|neck|torso)\b', re.I)
FLUX_ANATOMY = (' Anatomy: natural human proportions; each hand has five fingers and each foot five toes; '
                'both feet are clearly separate; arms and legs join the body naturally; a believable, relaxed pose.')
FLUX_FIX = ('Edit the attached image. Fix the body so it looks natural: {}. You may change the pose of the arms, '
            'legs and feet to get there. Keep the same person, face, hair, clothes, setting, light, palette and style.'
            + FLUX_ANATOMY)


def _drop_people_avoid(prompt):
    """Removes Avoid items about people ("people in frame") from the prompt's Avoid list."""
    def keep(m):
        items = [i for i in m.group(2).split(';') if not re.search(r'\b(people|person|figures?|humans?)\b', i, re.I)]
        return m.group(1) + ';'.join(items).strip() + '.' if items else ''
    return re.sub(r'(Avoid:\s*)([^.]*)\.', keep, prompt, count=1)


def _seed_prompt(ref):
    return ' '.join(_seed_prompts(ref))


def _seed_prompts(ref):
    """The prompts behind the seed image, back along its chain of variations (runs.csv + each batch's run.json
    source, up to 6 steps), joined; '' if unknown. A variation's own prompt often says only "keep the subject"."""
    if not ref:
        return []
    base = ROOT / 'generated' / 'codex'
    try:
        prompts = {(r.get('batch'), r.get('name')): r.get('prompt', '')
                   for r in csv.DictReader(open(base / 'runs.csv', encoding='utf-8'))}
    except OSError:
        return []
    out, batch, name = [], ref.parent.name, ref.stem
    for _ in range(6):
        out.append(prompts.get((batch, name), ''))
        try:
            run = json.load(open(base / batch / 'run.json', encoding='utf-8'))
        except (OSError, ValueError):
            break
        out.append(run.get('subject', '') if isinstance(run.get('subject'), str) else '')
        src = run.get('source') or {}
        if not (src.get('batch') and src.get('file')):
            break
        batch, name = src['batch'], Path(src['file']).stem
    return [p for p in out if p]


def has_person(prompt, ref=None):
    """True if the prompt (minus its Avoid list) or the seed's own prompt shows a person."""
    strip = lambda p: re.sub(r'Avoid:[^.]*\.', '', p)  # noqa: E731
    return bool(PERSON.search(strip(prompt)) or PERSON.search(strip(_seed_prompt(ref))))


def flux_people(a, prompt, refs, style_only):
    """The FLUX prompt adjusted for people (see PERSON above); returns (prompt, note for the log) or (prompt, '')."""
    seed = refs[0] if refs and not style_only else None
    if not has_person(prompt, seed):
        return prompt, ''
    wish = (a.subject or '').strip()
    if seed and a.mode == 'variations' and a.change == 'subject' and BODY_PART.search(wish):
        return FLUX_FIX.format(wish), 'person: body fix sent as an edit that may re-pose (FLUX_FIX)'
    return _drop_people_avoid(prompt) + FLUX_ANATOMY, 'person: anatomy line added, people dropped from Avoid'


def flux_examples(style, name, out):
    """FLUX's default look references (A/B test, 23 Nov 2026): with words only FLUX drifts to its own look, with
    3 of Marc's images of the style it stays close. Kept examples of the style first (kept.json), then his newest
    thumbs-up images made by ChatGPT; never this run's own folder. Turns through the pool by image number, so a
    batch doesn't lean on the same three. TASTE_FLUX_REFS=0 turns it off (for A/B tests)."""
    if not style or os.environ.get('TASTE_FLUX_REFS') == '0':
        return []
    base = ROOT / 'generated' / 'codex'
    ok = lambda b, n: b != out.name and (base / b / f'{n}.png').is_file() and ',' not in f'{b}{n}'  # noqa: E731
    pool = []
    try:
        for k in json.load(open(base / 'kept.json', encoding='utf-8')):
            if isinstance(k, dict) and k.get('style') == style and ok(k.get('batch', ''), k.get('name', '')):
                pool.append((k['batch'], k['name']))
    except (OSError, ValueError):
        pass
    try:
        import rate
        rows = list(csv.DictReader(open(base / 'runs.csv', encoding='utf-8')))
        made = {(r['batch'], r['name']): r for r in rows}
        liked = [r for _, r in rate.latest(list(csv.DictReader(open(base / 'ratings.csv', encoding='utf-8'))))
                 if r['rating'] == 'keep' and r['style'] == style]
        for r in reversed(liked):   # newest first
            m = made.get((r['batch'], r['name']), {})
            if (m.get('route') or 'codex') == 'codex' and ok(r['batch'], r['name']) and (r['batch'], r['name']) not in pool:
                pool.append((r['batch'], r['name']))
    except (OSError, KeyError, ImportError):
        pass
    pool = pool[:FLUX_POOL]
    if not pool:
        return []
    tail = name.rsplit('-', 1)[-1]
    i = int(tail) - 1 if tail.isdigit() else random.randrange(len(pool))
    n = min(FLUX_REFS, len(pool))
    return [(base / b / f'{nm}.png').resolve() for b, nm in (pool[(i * n + k) % len(pool)] for k in range(n))]


def gen_cloudflare(a, out, refs, ref):
    """The same prompt on FLUX (scripts/cf_run.py). Logged like a Codex run; the allowance columns stay empty.
    With no image given, flux_examples() adds up to 3 of Marc's images of the style (not logged as a seed, so a
    retry picks them again rather than reusing one as a seed)."""
    import cf_run
    examples = [] if refs else flux_examples(a.style, a.name, out)
    prog = None
    if not is_child():
        prog = Progress(out, [a.name], a.mode)
        prog.begin(a.name, a.subject or a.change)
    start = time.time()
    png = out / f'{a.name}.png'
    style_only = bool(examples) or (a.refs_kept and bool(refs))   # examples of a look, not a seed to edit
    sent = (FLUX_STYLE_ONLY if style_only else '') + a.prompt
    wish = (a.change or '').removeprefix('remix:').strip()
    people = ''
    if a.mode == 'remix' and refs and not style_only and wish and wish != 'prompt edited':
        sent = FLUX_EDIT.format(wish)   # 23 Nov 2026: with the long prompt FLUX copied the seed and ignored the change
        if has_person(wish, refs[0]):
            sent += FLUX_ANATOMY
    else:
        sent, people = flux_people(a, sent, refs, style_only)
    ok, spent, text, why = cf_run.make(sent, a.ratio, refs or examples, png)
    if sent != (FLUX_STYLE_ONLY if style_only else '') + a.prompt:
        text = f'sent as {people or "an edit (FLUX_EDIT)"}: {sent}\n' + text
    secs = round(time.time() - start)
    if style_only:
        text = 'prompt starts with the style-only line (FLUX_STYLE_ONLY)\n' + text
    if examples:
        text = 'style examples (FLUX default): ' + ', '.join(f'{p.parent.name}/{p.name}' for p in examples) + '\n' + text
    (out / f'{a.name}.codex.log').write_text(text + '\n', encoding='utf-8')
    w = h = ''
    if ok:
        from PIL import Image
        w, h = Image.open(png).size
    now = datetime.datetime.now()
    row = [now.date().isoformat(), now.strftime('%H:%M'), out.name, a.name, a.mode, a.style, a.change,
           ('kept ' + ' + '.join(r.name for r in refs)) if (a.refs_kept and refs) else ref.name if ref else '',
           'yes' if ok else 'no', w, h, spent if ok else '', '', '', '', '', secs, f'cloudflare:{cf_run.MODEL}', a.prompt, 'cloudflare']
    log_row(row)
    print(json.dumps(dict(zip(HEADER[:18], row[:18]))))
    if prog:
        prog.ok(a.name) if ok else prog.fail(a.name, why)
        prog.end()
    if not ok:
        print(f'FAILED: no image. Cloudflare: {why}; see {a.name}.codex.log', file=sys.stderr)
        sys.exit(2)


def gen_local(a, out, refs, ref):
    """The same prompt on an open model in ComfyUI (scripts/local_run.py). Logged like a Codex run, no tokens.
    Kept examples (--refs-kept) are not sent: the local graphs take one seed image at most. With a seed: FLUX local
    edits it (a remix gets Marc's change as an edit, as on Cloudflare), Playground and the SDXL fine-tunes start from it, Z-Image can't take
    an image, so it gets the seed's own prompt plus what this image changes."""
    import local_run
    model = a.model
    prog = None
    if not is_child():
        prog = Progress(out, [a.name], a.mode)
        prog.begin(a.name, a.subject or a.change)
    seed = refs[0] if refs and not a.refs_kept else None
    sent, note = a.prompt, ''
    wish = (a.change or '').removeprefix('remix:').strip()
    if model == 'klein' and not seed and has_person(sent):
        # 25 Nov 2026: 8-image test, FLUX local drew an extra arm or hand in 2 of 4 people images, Z-Image in none.
        # New images with a person go to Z-Image; seeded edits stay on FLUX local (Z-Image can't take an image).
        sent = _drop_people_avoid(sent)
        model, note = 'zimage', 'person in a new image: made with Z-Image instead of FLUX local (better bodies)'
    if seed and model == 'klein' and a.mode == 'remix' and wish and wish != 'prompt edited':
        sent, note = FLUX_EDIT.format(wish), 'sent as an edit of the seed (FLUX_EDIT)'
    elif seed and model == 'zimage':
        found = _seed_prompts(seed)
        base = max([p for p in found if 'Subject:' in p] or found, key=len, default='')
        if a.mode == 'variations':   # "keep ... of the seed" means nothing without the image: give the seed's prompt
            sent = f'{base} Change for this image: {a.prompt.split("Style notes")[0].strip()}' if base else a.prompt
            note = "Z-Image takes no image: sent the seed's prompt plus the change"
        seed = None
    if model == 'klein':   # people on FLUX local, with or without a seed (25 Nov 2026: new images had no guard)
        if note:   # a remix sent as FLUX_EDIT
            if has_person(wish, seed):
                sent += FLUX_ANATOMY
        else:
            sent, people = flux_people(a, sent, [seed] if seed else [], False)
            note = f'sent as {people}' if people else note
    start = time.time()
    png = out / f'{a.name}.png'
    ok, why, text = local_run.make(model, sent, a.style, a.ratio, png, ref=seed)
    secs = round(time.time() - start)
    if a.refs_kept and refs:
        text = 'kept examples not sent (local models take one seed image at most)\n' + text
    (out / f'{a.name}.codex.log').write_text('\n'.join(x for x in (note, text, why) if x) + '\n', encoding='utf-8')
    w = h = ''
    if ok:
        from PIL import Image
        w, h = Image.open(png).size
    now = datetime.datetime.now()
    row = [now.date().isoformat(), now.strftime('%H:%M'), out.name, a.name, a.mode, a.style, a.change,
           ('kept ' + ' + '.join(r.name for r in refs)) if (a.refs_kept and refs) else ref.name if ref else '',
           'yes' if ok else 'no', w, h, '', '', '', '', '', secs, f'local:{model}', a.prompt, 'local']
    log_row(row)
    print(json.dumps(dict(zip(HEADER[:18], row[:18]))))
    if prog:
        prog.ok(a.name) if ok else prog.fail(a.name, why)
        prog.end()
    if not ok:
        print(f'FAILED: no image. ComfyUI ({model}): {why}; see {a.name}.codex.log', file=sys.stderr)
        sys.exit(2)


def weekly_resets(path):
    """When Codex's weekly window resets (local time, ISO), from the last reading in a session log; None if absent.
    The web app counts "this Codex week" from it (23 Nov 2026)."""
    last = None
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            if '"resets_at"' in line:
                last = line
    try:
        sec = json.loads(last)['payload']['rate_limits']['secondary']
        return datetime.datetime.fromtimestamp(sec['resets_at']).isoformat(timespec='minutes')
    except (TypeError, KeyError, ValueError):
        return None


def read_now():
    files = sorted((CODEX / 'sessions').rglob('rollout-*.jsonl'), key=lambda p: p.stat().st_mtime)
    for p in reversed(files):
        r = readings(p)
        if r:
            print(json.dumps({'five_hour': r[-1][1], 'weekly': r[-1][2], 'weekly_resets': weekly_resets(p),
                              'session_log': p.name,
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
    g.add_argument('--look', type=int, help='which look of the style (light, framing, mood, palette); 0 = default')
    g.add_argument('--slot', type=int, help='with --mix: image K of the style in this batch; spreads the options')
    g.add_argument('--mix', help='seed: pick light, framing, mood and palette each on their own')
    g.add_argument('--extreme', choices=list(EXTREMES), help='wildcard: push one dimension to an extreme')
    g.add_argument('--print', action='store_true', help='only print the prompt and change; no Codex run')
    g.add_argument('--new-palette', action='store_true', help='experimental: a palette the style never uses, in place of its own')
    g.add_argument('--no-lean', action='store_true', help='pick options evenly, ignoring the ratings (scripts/leaning.py)')
    g.add_argument('--ref', action='append', default=[], help='reference image; repeat for several')
    g.add_argument('--refs-kept', action='store_true', help='the --ref images are kept examples of the style (not a seed)')
    g.add_argument('--style', default='')
    g.add_argument('--mode', default='test')
    g.add_argument('--change', default='')
    g.add_argument('--route', default=os.environ.get('TASTE_ROUTE') or 'codex', choices=ROUTES,
                   help='codex (default), cloudflare (FLUX on the free daily allowance, scripts/cf_run.py) or local (ComfyUI)')
    g.add_argument('--model', default=os.environ.get('TASTE_MODEL') or 'klein', choices=LOCAL_MODELS,
                   help='with --route local: klein (FLUX local), zimage (Z-Image Turbo), playground (Playground v2.5) or an SDXL fine-tune (dreamshaper, juggernaut, zavychroma, animagine)')
    sub.add_parser('read')
    a = ap.parse_args()
    gen(a) if a.cmd == 'gen' else read_now()
