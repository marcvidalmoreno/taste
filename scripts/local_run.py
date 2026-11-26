"""The "local" route (25 Nov 2026): one image with an open model on this laptop through ComfyUI, no tokens, no
daily limit, only laptop time. Grew out of scripts/local_test.py (the 24 Nov comparison); docs/local-route.md.

Models (ComfyUI on the Intel Arc 130V, %USERPROFILE%\\ComfyUI, http://127.0.0.1:8188):
  klein       FLUX local: FLUX.2 [klein] 4B, 4 steps; with a seed it edits it (ReferenceLatent)
  zimage      Z-Image Turbo 6B, 9 steps, weights loaded as fp8 (bf16 ran out of memory); text only
  playground  Playground v2.5 (SDXL family), 30 steps, cfg 3, the avoid list as negative prompt; with a seed:
              img2img from it (denoise 0.55)
  dreamshaper, juggernaut, zavychroma, animagine: SDXL community fine-tunes (26 Nov 2026, from the 25 Nov test),
              each with its creator's steps / cfg / sampler (SDXL below); prompts and seeds as Playground
All of them decode with VAEDecodeTiled (512 tiles): a full 1024 px decode ran out of shared memory.

Not run alone for images: codex_run.py gen --route local --model <m> calls make() (the web app sets TASTE_ROUTE=local
and TASTE_MODEL for its runs), so styles, mixes, batches, remixes and variations work unchanged.
ComfyUI starts by itself, hidden, when it isn't running (ensure_running). free() unloads its models; the web app
calls it after a local run and before a local text job, so ComfyUI and Ollama never hold memory at once.

  .venv/Scripts/python -I scripts/local_run.py speed     # seconds per image, per model, from runs.csv
  .venv/Scripts/python -I scripts/local_run.py free      # unload ComfyUI's models now
  .venv/Scripts/python -I scripts/local_run.py start     # start ComfyUI hidden if it isn't running
"""
import csv, json, os, re, statistics, subprocess, sys, time, urllib.parse, urllib.request, uuid, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = 'http://127.0.0.1:8188'
COMFY = Path.home() / 'ComfyUI'
LOG = ROOT / 'generated' / 'codex' / 'runs.csv'
MODELS = {   # key -> what the app shows (badge, full name) and what the model can do with a seed image
    'klein': {'badge': 'FLUX local', 'name': 'FLUX.2 klein 4B in ComfyUI', 'seed': 'edit'},
    'zimage': {'badge': 'Z-Image', 'name': 'Z-Image Turbo 6B', 'seed': 'prompt'},
    'playground': {'badge': 'Playground', 'name': 'Playground v2.5', 'seed': 'img2img'},
    'dreamshaper': {'badge': 'DreamShaper', 'name': 'DreamShaper XL Lightning', 'seed': 'img2img'},
    'juggernaut': {'badge': 'Juggernaut', 'name': 'Juggernaut XL Lightning', 'seed': 'img2img'},
    'zavychroma': {'badge': 'ZavyChroma', 'name': 'ZavyChroma XL v10', 'seed': 'img2img'},
    'animagine': {'badge': 'Animagine', 'name': 'Animagine XL 4.0', 'seed': 'img2img'},
}
# SDXL checkpoints in models/checkpoints: file, steps, cfg, sampler, scheduler (the creators' recommended settings).
SDXL = {
    'dreamshaper': ('DreamShaperXL_Lightning.safetensors', 6, 2.0, 'dpmpp_sde', 'karras'),
    'juggernaut': ('Juggernaut_RunDiffusionPhoto2_Lightning_4Steps.safetensors', 5, 1.5, 'dpmpp_sde', 'karras'),
    'zavychroma': ('zavychromaxl_v100.safetensors', 30, 5.0, 'dpmpp_2m', 'karras'),
    'animagine': ('animagine-xl-4.0-opt.safetensors', 28, 5.0, 'euler_ancestral', 'normal'),
}
CLIP_MODELS = ('playground',) + tuple(SDXL)   # CLIP text encoder: short prompt, avoid list as negative
SIZES = {'wide': (1024, 576), 'portrait': (832, 1024), 'square': (1024, 1024)}
DENOISE = 0.55        # Playground from a seed: keeps its layout and palette, redraws the rest
ADULTS = ' Every figure is an adult.'   # erotic style on a local model: limits in docs/local-route.md
TILED = {'tile_size': 512, 'overlap': 64, 'temporal_size': 64, 'temporal_overlap': 8}


def graph(model, prompt, negative, seed, w, h, ref=None, prefix='taste'):
    """The ComfyUI graph for one image. ref: an uploaded image name (klein edits it, playground starts from it)."""
    if model == 'klein':
        g = {
            '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'flux-2-klein-4b.safetensors', 'weight_dtype': 'default'}},
            '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen_3_4b.safetensors', 'type': 'flux2', 'device': 'default'}},
            '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'flux2-vae.safetensors'}},
            '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
            '5': {'class_type': 'EmptyFlux2LatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}},
            '6': {'class_type': 'Flux2Scheduler', 'inputs': {'steps': 4, 'width': w, 'height': h}},
            '7': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
            '8': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': seed}},
            '9': {'class_type': 'BasicGuider', 'inputs': {'model': ['1', 0], 'conditioning': ['4', 0]}},
            '10': {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['8', 0], 'guider': ['9', 0], 'sampler': ['7', 0],
                                                                    'sigmas': ['6', 0], 'latent_image': ['5', 0]}},
            '11': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['10', 0], 'vae': ['3', 0], **TILED}},
            '12': {'class_type': 'SaveImage', 'inputs': {'images': ['11', 0], 'filename_prefix': prefix}}}
        if ref:   # edit: the seed goes in as a reference latent on the conditioning
            g['20'] = {'class_type': 'LoadImage', 'inputs': {'image': ref}}
            g['21'] = {'class_type': 'ImageScale', 'inputs': {'image': ['20', 0], 'upscale_method': 'lanczos', 'width': w, 'height': h, 'crop': 'center'}}
            g['22'] = {'class_type': 'VAEEncodeTiled', 'inputs': {'pixels': ['21', 0], 'vae': ['3', 0], **TILED}}
            g['23'] = {'class_type': 'ReferenceLatent', 'inputs': {'conditioning': ['4', 0], 'latent': ['22', 0]}}
            g['9']['inputs']['conditioning'] = ['23', 0]
        return g
    if model == 'zimage':
        return {
            '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'z_image_turbo_bf16.safetensors', 'weight_dtype': 'fp8_e4m3fn'}},
            '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen_3_4b.safetensors', 'type': 'lumina2', 'device': 'default'}},
            '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'ae.safetensors'}},
            '4': {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': ['1', 0], 'shift': 3.0}},
            '5': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
            '6': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['5', 0]}},
            '7': {'class_type': 'EmptySD3LatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}},
            '8': {'class_type': 'KSampler', 'inputs': {'model': ['4', 0], 'seed': seed, 'steps': 9, 'cfg': 1.0,
                                                       'sampler_name': 'res_multistep', 'scheduler': 'simple', 'denoise': 1.0,
                                                       'positive': ['5', 0], 'negative': ['6', 0], 'latent_image': ['7', 0]}},
            '9': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['8', 0], 'vae': ['3', 0], **TILED}},
            '10': {'class_type': 'SaveImage', 'inputs': {'images': ['9', 0], 'filename_prefix': prefix}}}
    if model in SDXL:
        ckpt, steps, cfg, sampler, scheduler = SDXL[model]
        g = {
            '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': ckpt}},
            '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['1', 1]}},
            '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': negative, 'clip': ['1', 1]}},
            '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}},
            '6': {'class_type': 'KSampler', 'inputs': {'model': ['1', 0], 'seed': seed, 'steps': steps, 'cfg': cfg,
                                                       'sampler_name': sampler, 'scheduler': scheduler, 'denoise': 1.0,
                                                       'positive': ['3', 0], 'negative': ['4', 0], 'latent_image': ['5', 0]}},
            '7': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['6', 0], 'vae': ['1', 2], **TILED}},
            '8': {'class_type': 'SaveImage', 'inputs': {'images': ['7', 0], 'filename_prefix': prefix}}}
    else:
        g = {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'playground-v2.5-1024px-aesthetic.fp16.safetensors'}},
        '2': {'class_type': 'ModelSamplingContinuousEDM', 'inputs': {'model': ['1', 0], 'sampling': 'edm_playground_v2.5',
                                                                     'sigma_max': 120.0, 'sigma_min': 0.002}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['1', 1]}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': negative, 'clip': ['1', 1]}},
        '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}},
        '6': {'class_type': 'KSampler', 'inputs': {'model': ['2', 0], 'seed': seed, 'steps': 30, 'cfg': 3.0,
                                                   'sampler_name': 'dpmpp_2m', 'scheduler': 'karras', 'denoise': 1.0,
                                                   'positive': ['3', 0], 'negative': ['4', 0], 'latent_image': ['5', 0]}},
        '7': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['6', 0], 'vae': ['1', 2], **TILED}},
        '8': {'class_type': 'SaveImage', 'inputs': {'images': ['7', 0], 'filename_prefix': prefix}}}
    if ref:   # img2img: start from the seed instead of noise
        g['20'] = {'class_type': 'LoadImage', 'inputs': {'image': ref}}
        g['21'] = {'class_type': 'ImageScale', 'inputs': {'image': ['20', 0], 'upscale_method': 'lanczos', 'width': w, 'height': h, 'crop': 'center'}}
        g['22'] = {'class_type': 'VAEEncodeTiled', 'inputs': {'pixels': ['21', 0], 'vae': ['1', 2], **TILED}}
        g['6']['inputs'].update(latent_image=['22', 0], denoise=DENOISE)
    return g


RATIO_LINE = re.compile(r'^(Wide 16:9 desktop wallpaper\.|Square 1:1 image for a LinkedIn post\.|Portrait 4:5 image for a LinkedIn post\.)\s*')


def prompts(model, style, prompt):
    """(prompt, negative) for a full app prompt. FLUX and Z-Image get it as ChatGPT does; Playground (CLIP, 77
    tokens) gets it without the ratio line, the hex palette and the avoid list, and the avoid list as its negative."""
    text = prompt + (ADULTS if style == 'erotic' else '')
    if model not in CLIP_MODELS:
        return text, ''
    avoid = re.search(r'Avoid:(.*?)(?:No text, no logos, no watermark\.|$)', text, re.S)
    pos = re.sub(r'Avoid:.*?(?=No text|$)', '', text, flags=re.S)
    pos = re.sub(r'Palette:[^.]*\.', '', pos)
    pos = RATIO_LINE.sub('', pos).replace('Subject: ', '', 1)
    neg = (avoid.group(1).strip() if avoid else '') + '; text, logo, watermark, blurry, deformed hands'
    if style == 'erotic':
        neg += ', child, minor, explicit sex'
    if model == 'animagine':   # its model card: quality tags at the end, its own negative tags first
        return ' '.join(pos.split()) + ' masterpiece, high score, great score, absurdres',             'lowres, bad anatomy, bad hands, worst quality, low quality, ' + neg
    return ' '.join(pos.split()), neg


def call(path, body=None, timeout=60, raw=None, ctype='application/json'):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API + path, data=data, headers={'Content-Type': ctype})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def running():
    try:
        call('/system_stats', timeout=3)
        return True
    except OSError:
        return False


def ensure_running(wait=300):
    """Start ComfyUI hidden (no window) if it isn't up, and wait for it. Returns '' or why it couldn't."""
    if running():
        return ''
    py = COMFY / '.venv' / 'Scripts' / 'python.exe'
    if not py.is_file():
        return f'ComfyUI is not installed at {COMFY}'
    flags = 0x08000000 | 0x00000008 | 0x00000200   # CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(COMFY / 'comfy-taste.log', 'ab') as log:
        subprocess.Popen([str(py), str(COMFY / 'main.py'), '--port', '8188'], cwd=COMFY, stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, creationflags=flags if os.name == 'nt' else 0, close_fds=True)
    start = time.time()
    while time.time() - start < wait:
        time.sleep(3)
        if running():
            return ''
    return f'ComfyUI did not start within {wait} s (see {COMFY / "comfy-taste.log"})'


def upload(path):
    """Copy an image into ComfyUI's input folder through its API; returns the name LoadImage takes."""
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.open(path).convert('RGB').save(buf, 'PNG')
    b, name = uuid.uuid4().hex, f'taste-{uuid.uuid4().hex[:12]}.png'
    body = (f'--{b}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'
            ).encode() + buf.getvalue() + f'\r\n--{b}--\r\n'.encode()
    return json.loads(call('/upload/image', raw=body, ctype=f'multipart/form-data; boundary={b}'))['name']


def make(model, prompt, style, ratio, png, ref=None, seed=None):
    """One image into png. ref: a seed image path (klein edits it, playground starts from it, zimage ignores it).
    Returns (ok, why, log text)."""
    if model not in MODELS:
        return False, f'unknown local model "{model}"', ''
    why = ensure_running()
    if why:
        return False, why, why
    w, h = SIZES.get(ratio, SIZES['wide'])
    seed = seed if seed is not None else zlib.crc32(f'{png.parent.name}/{png.stem}'.encode())
    pos, neg = prompts(model, style, prompt)
    use_ref = ref if ref and MODELS[model]['seed'] in ('edit', 'img2img') else None
    log = [f'model: {model} ({MODELS[model]["name"]})', f'seed: {seed}', f'size: {w}x{h}',
           f'seed image: {Path(use_ref).name} ({MODELS[model]["seed"]})' if use_ref else 'seed image: none',
           f'prompt sent: {pos}'] + ([f'negative: {neg}'] if neg else [])
    try:
        name = upload(use_ref) if use_ref else None
        pid = json.loads(call('/prompt', {'prompt': graph(model, pos, neg, seed, w, h, name),
                                          'client_id': str(uuid.uuid4())}))['prompt_id']
    except Exception as e:   # bad graph, server gone
        detail = getattr(e, 'read', lambda: b'')()[:500].decode('utf-8', 'replace')
        return False, f'{type(e).__name__}: {e} {detail}'.strip()[:300], '\n'.join(log)
    start = time.time()
    while time.time() - start < 1800:
        time.sleep(2)
        try:
            hist = json.loads(call(f'/history/{pid}')).get(pid)
        except OSError:
            continue
        if not hist:
            continue
        status = hist.get('status', {})
        if status.get('status_str') == 'error':
            msgs = [m for m in status.get('messages', []) if m[0] == 'execution_error']
            why = (msgs[0][1].get('exception_message', 'error') if msgs else 'error').strip()[:300]
            return False, why, '\n'.join(log + [f'ComfyUI error: {why}'])
        for out in hist.get('outputs', {}).values():
            for im in out.get('images', []):
                q = urllib.parse.urlencode({'filename': im['filename'], 'subfolder': im['subfolder'], 'type': im['type']})
                png.write_bytes(call(f'/view?{q}'))
                return True, '', '\n'.join(log)
    return False, 'TIMED OUT after 30 min', '\n'.join(log + ['TIMED OUT after 30 min'])


def free(quiet=False):
    """Ask ComfyUI to drop its loaded models, so it stops holding ~12-28 GB of shared memory."""
    if not running():
        return True
    try:
        call('/free', {'unload_models': True, 'free_memory': True}, timeout=300)
        quiet or print('ComfyUI models unloaded')
        return True
    except Exception as e:
        quiet or print(f'could not unload ComfyUI models: {e}', file=sys.stderr)
        return False


def speed():
    """{model: {'n', 'median'}} from runs.csv: seconds per image, the first image of a run (loading) left out."""
    by = {}
    if LOG.exists():
        for r in csv.DictReader(open(LOG, encoding='utf-8')):
            if r.get('route') == 'local' and r['ok'] == 'yes' and r['session'].startswith('local:') and r['seconds']:
                by.setdefault(r['session'][6:], []).append(int(r['seconds']))
    return {m: {'n': len(s), 'median': round(statistics.median(s[1:] or s))} for m, s in by.items() if m in MODELS}


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'speed':
        for m, s in speed().items():
            print(f'{m}: {s["n"]} images, median {s["median"]} s')
    elif cmd == 'free':
        free()
    elif cmd == 'start':
        print(ensure_running() or 'ComfyUI is running')
    else:
        sys.exit(__doc__)
