"""Local model test (24 Nov 2026): the same prompts on three open models running on this laptop through ComfyUI,
so Marc can compare them in the app before we decide whether a local route goes in. Test only, not a route yet.

Models (ComfyUI on Intel Arc, C:\\Users\\mvidalmoreno\\ComfyUI, http://127.0.0.1:8188):
  klein      FLUX.2 [klein] 4B (Apache 2.0), 4 steps            - the model the Cloudflare route uses
  zimage     Z-Image Turbo 6B (Apache 2.0), 9 steps, weights loaded as fp8 (bf16 crashed the server: out of memory)
  playground Playground v2.5 (SDXL family, Playground licence), 30 steps, avoid list as negative prompt

Per model, one batch generated/codex/<date>-local-<model>/: 2 images for every style (subjects 1 and 2 of the
style) plus subjects 3 and 4 for the --match styles, so those get 4 matching prompts each (12 in all).
Same seed per style and subject on every model. Rows go to runs.csv with route "local" and session
"local:<model>"; "seconds" is wall time (the first image of a model includes loading it).
--blind copies the matching images of all models into <date>-local-blind with shuffled names; which model made
which is in generated/codex/local-blind-key.json (git-ignored), read only after Marc has rated.

  .venv/Scripts/python -I scripts/local_test.py run --model klein [--only STYLE ...] [--match a b c] [--skip STYLE ...] [--limit N]
  .venv/Scripts/python -I scripts/local_test.py blind --match a b c
  .venv/Scripts/python -I scripts/local_test.py speed          # seconds per image, per model, from runs.csv
"""
import argparse, csv, datetime, json, random, re, shutil, statistics, sys, time, urllib.parse, urllib.request, uuid, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from codex_run import HEADER, LOG, RATIOS, log_row  # noqa: E402
from progress import Progress  # noqa: E402

API = 'http://127.0.0.1:8188'
W = H = 1024
# Tiled VAE decode (24 Nov 2026): a full 1024px decode ran out of the Arc 130V's shared memory.
MODELS = ('klein', 'zimage', 'playground')
DAY = datetime.date.today().isoformat()
KEY = ROOT / 'generated' / 'codex' / 'local-blind-key.json'
ADULTS = ' Every figure is an adult.'   # erotic style on a local model: limits in docs/local-route.md


def graph(model, prompt, negative, seed, prefix):
    if model == 'klein':
        return {
            '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'flux-2-klein-4b.safetensors', 'weight_dtype': 'default'}},
            '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen_3_4b.safetensors', 'type': 'flux2', 'device': 'default'}},
            '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'flux2-vae.safetensors'}},
            '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
            '5': {'class_type': 'EmptyFlux2LatentImage', 'inputs': {'width': W, 'height': H, 'batch_size': 1}},
            '6': {'class_type': 'Flux2Scheduler', 'inputs': {'steps': 4, 'width': W, 'height': H}},
            '7': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
            '8': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': seed}},
            '9': {'class_type': 'BasicGuider', 'inputs': {'model': ['1', 0], 'conditioning': ['4', 0]}},
            '10': {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['8', 0], 'guider': ['9', 0], 'sampler': ['7', 0],
                                                                    'sigmas': ['6', 0], 'latent_image': ['5', 0]}},
            '11': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['10', 0], 'vae': ['3', 0], 'tile_size': 512, 'overlap': 64, 'temporal_size': 64, 'temporal_overlap': 8}},
            '12': {'class_type': 'SaveImage', 'inputs': {'images': ['11', 0], 'filename_prefix': prefix}}}
    if model == 'zimage':
        return {
            '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'z_image_turbo_bf16.safetensors', 'weight_dtype': 'fp8_e4m3fn'}},
            '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen_3_4b.safetensors', 'type': 'lumina2', 'device': 'default'}},
            '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'ae.safetensors'}},
            '4': {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': ['1', 0], 'shift': 3.0}},
            '5': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
            '6': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['5', 0]}},
            '7': {'class_type': 'EmptySD3LatentImage', 'inputs': {'width': W, 'height': H, 'batch_size': 1}},
            '8': {'class_type': 'KSampler', 'inputs': {'model': ['4', 0], 'seed': seed, 'steps': 9, 'cfg': 1.0,
                                                       'sampler_name': 'res_multistep', 'scheduler': 'simple', 'denoise': 1.0,
                                                       'positive': ['5', 0], 'negative': ['6', 0], 'latent_image': ['7', 0]}},
            '9': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['8', 0], 'vae': ['3', 0], 'tile_size': 512, 'overlap': 64, 'temporal_size': 64, 'temporal_overlap': 8}},
            '10': {'class_type': 'SaveImage', 'inputs': {'images': ['9', 0], 'filename_prefix': prefix}}}
    return {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'playground-v2.5-1024px-aesthetic.fp16.safetensors'}},
        '2': {'class_type': 'ModelSamplingContinuousEDM', 'inputs': {'model': ['1', 0], 'sampling': 'edm_playground_v2.5',
                                                                     'sigma_max': 120.0, 'sigma_min': 0.002}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['1', 1]}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': negative, 'clip': ['1', 1]}},
        '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': W, 'height': H, 'batch_size': 1}},
        '6': {'class_type': 'KSampler', 'inputs': {'model': ['2', 0], 'seed': seed, 'steps': 30, 'cfg': 3.0,
                                                   'sampler_name': 'dpmpp_2m', 'scheduler': 'karras', 'denoise': 1.0,
                                                   'positive': ['3', 0], 'negative': ['4', 0], 'latent_image': ['5', 0]}},
        '7': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['6', 0], 'vae': ['1', 2], 'tile_size': 512, 'overlap': 64, 'temporal_size': 64, 'temporal_overlap': 8}},
        '8': {'class_type': 'SaveImage', 'inputs': {'images': ['7', 0], 'filename_prefix': prefix}}}


def prompts(model, style_key, st, subject):
    """(prompt, negative). FLUX and Z-Image get the same prompt as Codex; SDXL gets the style without the avoid
    list and hex palette (CLIP can't read either) and the avoid list as its negative prompt."""
    text = st['prompt'] + (ADULTS if style_key == 'erotic' else '')
    if model != 'playground':
        return f"{RATIOS['square']} Subject: {subject}. {text}", ''
    avoid = re.search(r'Avoid:(.*?)(?:No text, no logos, no watermark\.|$)', text, re.S)
    pos = re.sub(r'Avoid:.*?(?=No text|$)', '', text, flags=re.S)
    pos = re.sub(r'Palette:[^.]*\.', '', pos)
    neg = (avoid.group(1).strip() if avoid else '') + '; text, logo, watermark, blurry, deformed hands'
    if style_key == 'erotic':
        neg += ', child, minor, explicit sex'
    return f'{subject}. {pos.strip()}', neg


def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def make(model, prompt, negative, seed, png):
    """One image through ComfyUI. Returns (ok, why)."""
    pid = json.loads(call('/prompt', {'prompt': graph(model, prompt, negative, seed, 'taste-test'),
                                      'client_id': str(uuid.uuid4())}))['prompt_id']
    start = time.time()
    while time.time() - start < 1800:
        time.sleep(2)
        hist = json.loads(call(f'/history/{pid}')).get(pid)
        if not hist:
            continue
        status = hist.get('status', {})
        if status.get('status_str') == 'error':
            msgs = [m for m in status.get('messages', []) if m[0] == 'execution_error']
            return False, (msgs[0][1].get('exception_message', 'error') if msgs else 'error').strip()[:300]
        for out in hist.get('outputs', {}).values():
            for im in out.get('images', []):
                q = urllib.parse.urlencode({'filename': im['filename'], 'subfolder': im['subfolder'], 'type': im['type']})
                png.write_bytes(call(f'/view?{q}'))
                return True, ''
    return False, 'timed out after 30 min'


def jobs(taste, only, match, skip=()):
    for key, st in taste.items():
        if (only and key not in only) or key in skip:
            continue
        n = 4 if key in match else 2
        for i, subject in enumerate(st.get('subjects', [])[:n]):
            yield key, st, i + 1, subject


def run(a):
    taste = json.load(open(ROOT / 'taste' / 'taste.json', encoding='utf-8'))['styles']
    todo = list(jobs(taste, a.only, a.match, a.skip or ()))[:a.limit or None]
    out = ROOT / 'generated' / 'codex' / f'{DAY}-local-{a.model}'
    out.mkdir(parents=True, exist_ok=True)
    names = [f'{k}-{i}' for k, _, i, _ in todo]
    prog = Progress(out, names, 'local test')
    fails = 0
    for (key, st, i, subject), name in zip(todo, names):
        png = out / f'{name}.png'
        if png.exists():
            continue
        prompt, neg = prompts(a.model, key, st, subject)
        seed = zlib.crc32(f'{key}-{i}'.encode())
        prog.begin(name, subject)
        t0 = time.time()
        try:
            ok, why = make(a.model, prompt, neg, seed, png)
        except Exception as e:  # server down, bad graph
            ok, why = False, f'{type(e).__name__}: {e}'
        secs = round(time.time() - t0)
        (out / f'{name}.codex.log').write_text(f'model: {a.model}\nseed: {seed}\nnegative: {neg}\n{why}\n', encoding='utf-8')
        now = datetime.datetime.now()
        log_row([now.date().isoformat(), now.strftime('%H:%M'), out.name, name, 'local-test', key, f'local {a.model}', seed,
                 'yes' if ok else 'no', W if ok else '', H if ok else '', '', '', '', '', '', secs, f'local:{a.model}', prompt, 'local'])
        print(f'{name}: {"ok" if ok else "FAILED " + why} in {secs}s', flush=True)
        if ok:
            prog.ok(name)
            fails = 0
        else:
            prog.fail(name, why)
            fails += 1
            if fails >= 2:   # one attempt and one recovery, then stop and report
                print('two failures in a row: stopping', file=sys.stderr)
                break
    prog.end()


def blind(a):
    rnd = random.Random(DAY)
    items = [(m, f'{k}-{i}') for m in MODELS for k in a.match for i in range(1, 5)]
    items = [(m, n) for m, n in items if (ROOT / 'generated' / 'codex' / f'{DAY}-local-{m}' / f'{n}.png').exists()]
    rnd.shuffle(items)
    out = ROOT / 'generated' / 'codex' / f'{DAY}-local-blind'
    out.mkdir(parents=True, exist_ok=True)
    rows = {(r['batch'], r['name']): r for r in csv.DictReader(open(LOG, encoding='utf-8'))}
    key = {}
    for j, (m, n) in enumerate(items, 1):
        new = f'{n.rsplit("-", 1)[0]}-{j:02d}'
        shutil.copy2(ROOT / 'generated' / 'codex' / f'{DAY}-local-{m}' / f'{n}.png', out / f'{new}.png')
        key[new] = {'model': m, 'image': n}
        src = rows.get((f'{DAY}-local-{m}', n), {})
        now = datetime.datetime.now()
        log_row([now.date().isoformat(), now.strftime('%H:%M'), out.name, new, 'local-test', src.get('style', ''),
                 'local blind', src.get('seed', ''), 'yes', W, H, '', '', '', '', '', '', 'local:hidden', src.get('prompt', ''), 'local'])
    KEY.write_text(json.dumps(key, indent=1), encoding='utf-8')
    print(f'{len(items)} images in {out}')


def speed(_a):
    by = {}
    for r in csv.DictReader(open(LOG, encoding='utf-8')):
        if r.get('route') == 'local' and r['ok'] == 'yes' and r['session'].startswith('local:') and r['seconds']:
            by.setdefault(r['session'][6:], []).append(int(r['seconds']))
    for m, s in by.items():
        if m != 'hidden':
            print(f'{m}: {len(s)} images, first {s[0]} s (includes loading), median {statistics.median(s[1:] or s):.0f} s')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--model', choices=MODELS, required=True)
    r.add_argument('--only', nargs='*')
    r.add_argument('--match', nargs='*', default=['erotic', 'retro-future-rooms', 'dubuffet'])
    r.add_argument('--limit', type=int)
    r.add_argument('--skip', nargs='*')
    b = sub.add_parser('blind')
    b.add_argument('--match', nargs='*', default=['erotic', 'retro-future-rooms', 'dubuffet'])
    sub.add_parser('speed')
    a = p.parse_args()
    {'run': run, 'blind': blind, 'speed': speed}[a.cmd](a)
