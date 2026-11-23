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

One fresh `codex exec` per image. Codex only generates and copies the PNG into --out; it never views the
result and never touches the taste files. Afterwards this script reads tokens and the five-hour / weekly
allowance from Codex's own session log (~/.codex/sessions) and the PNG's real pixel size, and appends
one row to generated/codex/runs.csv (git-ignored). Numbers are never typed by hand.
One recovery only: if the PNG is not in --out, copy it from ~/.codex/generated_images/<session>/.
Otherwise the run is logged as failed; stop and report, do not loop.
"""
import argparse, csv, datetime, json, os, random, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from progress import Progress, is_child  # noqa: E402
LOG = ROOT / 'generated' / 'codex' / 'runs.csv'
CODEX = Path.home() / '.codex'
HEADER = ['date', 'time', 'batch', 'name', 'mode', 'style', 'change', 'seed', 'ok', 'width', 'height',
          'tokens', 'five_hour_first', 'five_hour_last', 'weekly_first', 'weekly_last', 'seconds', 'session', 'prompt', 'route']
ROUTES = ['codex', 'cloudflare']   # cloudflare: scripts/cf_run.py, FLUX on Workers AI's free allowance (23 Nov 2026)

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
        if slot:  # the wildcard replaces its own axis, so the prompt never asks for two lights at once
            fill[slot], wild = wild, ''
            pick.pop(slot)
        block = st['template'].format(**fill)
        tags = (['mix'] if rnd else []) + (['lean'] if leaned else []) + [f'{k[0]}{i}' for k, i in pick.items()]  # l(ight) c(omposition) m(ood) p(alette)
    else:
        looks = st.get('looks') or [st['prompt']]
        block = looks[a.look % len(looks)] if a.look is not None else st['prompt']
        tags = []
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
        res = subprocess.CompletedProcess(cmd, 124, tail(e.stdout), tail(e.stderr) + '
TIMED OUT: codex exec ran over 900 s and was stopped')
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
        text = LOG.read_text(encoding='utf-8')
        head, _, rest = text.partition('
')
        if head.strip() and 'route' not in head.strip().split(','):
            LOG.write_text(head.rstrip('') + ',route
' + rest, encoding='utf-8', newline='')
    new = not LOG.exists()
    with open(LOG, 'a', encoding='utf-8', newline='') as fh:
        wr = csv.writer(fh)
        if new:
            wr.writerow(HEADER)
        wr.writerow(row)


def gen_cloudflare(a, out, refs, ref):
    """The same prompt on FLUX (scripts/cf_run.py). Logged like a Codex run; the allowance columns stay empty."""
    import cf_run
    prog = None
    if not is_child():
        prog = Progress(out, [a.name], a.mode)
        prog.begin(a.name, a.subject or a.change)
    start = time.time()
    png = out / f'{a.name}.png'
    ok, spent, text, why = cf_run.make(a.prompt, a.ratio, refs, png)
    secs = round(time.time() - start)
    (out / f'{a.name}.codex.log').write_text(text + '
', encoding='utf-8')
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


def read_now():
    files = sorted((CODEX / 'sessions').rglob('rollout-*.jsonl'), key=lambda p: p.stat().st_mtime)
    for p in reversed(files):
        r = readings(p)
        if r:
            print(json.dumps({'five_hour': r[-1][1], 'weekly': r[-1][2], 'session_log': p.name,
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
    g.add_argument('--no-lean', action='store_true', help='pick options evenly, ignoring the ratings (scripts/leaning.py)')
    g.add_argument('--ref', action='append', default=[], help='reference image; repeat for several')
    g.add_argument('--refs-kept', action='store_true', help='the --ref images are kept examples of the style (not a seed)')
    g.add_argument('--style', default='')
    g.add_argument('--mode', default='test')
    g.add_argument('--change', default='')
    g.add_argument('--route', default=os.environ.get('TASTE_ROUTE') or 'codex', choices=ROUTES,
                   help='codex (default) or cloudflare (FLUX on the free daily allowance, scripts/cf_run.py)')
    sub.add_parser('read')
    a = ap.parse_args()
    gen(a) if a.cmd == 'gen' else read_now()
