"""The "cloudflare" route (23 Nov 2026): one image with FLUX.2 [klein] 4B on Cloudflare Workers AI, on its free
daily allowance (10,000 neurons, ~95 images, ~80 with the 3 style examples codex_run adds). Plan and limits: docs/cloudflare-route.md.

Not run alone for images: codex_run.py gen --route cloudflare calls make() (the web app sets TASTE_ROUTE=cloudflare
for its runs), so styles, mixes, wildcards, leaning, batches, remixes and variations work unchanged.
  .venv/Scripts/python -I scripts/cf_run.py today    # neurons used today (estimated from runs.csv), images left

Credentials: %USERPROFILE%\\.taste\\cloudflare.json {"account_id", "token"}, written by the web app's Connect
Cloudflare card; never in the repo, never printed. Neurons are estimated from Cloudflare's published price
(the reply doesn't report them). Cloudflare says the allowance resets at 00:00 UTC, but on 24 Nov 2026 it came
back around 17:30 UTC, so nothing here promises a time: a used-up allowance is remembered in
%USERPROFILE%\\.taste\\cloudflare-limit.json, and while it lasts today() checks once an hour (in the background)
with one tiny 256x256 image (~26 neurons; a refused call costs nothing) and marks FLUX back when one goes through.
One attempt and one retry (network or server error only); a used-up allowance writes "usage limit" to
<name>.codex.log, so the app's Resume works.
"""
import base64, datetime, io, json, math, os, sys, threading, time, urllib.error, urllib.request, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRED = Path.home() / '.taste' / 'cloudflare.json'
LIMIT = Path.home() / '.taste' / 'cloudflare-limit.json'   # {"hit", "checked"} while used up; {"back"} after
CHECK_EVERY = 3600                     # seconds between free checks while the allowance is used up
MODEL = 'flux-2-klein-4b'
API = 'https://api.cloudflare.com/client/v4'
DAILY = 10_000                         # free neurons a day (Workers Free plan)
OUT_TILE, IN_TILE = 26.05, 5.37        # neurons per 512x512 tile, Cloudflare pricing page, 23 Nov 2026
SIZES = {'wide': (1024, 576), 'portrait': (816, 1024), 'square': (1024, 1024)}   # 4 output tiles each
CHECK_SIZE = (256, 256)                # the hourly "is it back?" image: 1 tile
REF_MAX = 496                          # reference images must be smaller than 512x512


def creds():
    try:
        c = json.loads(CRED.read_text(encoding='utf-8'))
        return c if c.get('account_id') and c.get('token') else None
    except (OSError, ValueError):
        return None


def save_creds(account_id, token):
    CRED.parent.mkdir(parents=True, exist_ok=True)
    CRED.write_text(json.dumps({'account_id': account_id, 'token': token}), encoding='utf-8')


def forget_creds():
    CRED.unlink(missing_ok=True)


def neurons(w, h, n_refs):
    return round(OUT_TILE * math.ceil(w / 512) * math.ceil(h / 512) + IN_TILE * n_refs, 1)


PER_IMAGE = neurons(*SIZES['wide'], 0)


def _call(req, timeout=120):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get('Content-Type', ''), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type', ''), e.read()


def verify(account_id, token):
    """True if the token is active (Cloudflare's free verify call: no neurons). Tries user, then account tokens."""
    for url in (f'{API}/user/tokens/verify', f'{API}/accounts/{account_id}/tokens/verify'):
        try:
            code, _, body = _call(urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'}), 30)
        except OSError as e:
            return False, f'Could not reach Cloudflare: {e}'
        try:
            res = json.loads(body)
        except ValueError:
            continue
        if code == 200 and (res.get('result') or {}).get('status') == 'active':
            return True, ''
    return False, 'Cloudflare did not accept this token. Check that it is copied whole and has the Workers AI permission.'


def _small(path):
    from PIL import Image
    im = Image.open(path).convert('RGB')
    im.thumbnail((REF_MAX, REF_MAX))
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()


def _multipart(fields, files):
    b = uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
    for k, data in files.items():
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{k}.png"\r\n'
                  f'Content-Type: image/png\r\n\r\n'.encode('utf-8') + data + b'\r\n')
    out.write(f'--{b}--\r\n'.encode('utf-8'))
    return out.getvalue(), f'multipart/form-data; boundary={b}'


def make(prompt, ratio, refs, png):
    """One image into png. Returns (ok, neurons, log text, why). why: '' | 'usage limit' | 'blocked' | other."""
    c = creds()
    if not c:
        return False, 0, 'Cloudflare is not connected: open New run in the web app and press Connect Cloudflare.', 'not connected'
    w, h = CHECK_SIZE if ratio == 'check' else SIZES.get(ratio, SIZES['wide'])
    refs = refs[:4]
    body, ctype = _multipart({'prompt': prompt[:2048], 'width': w, 'height': h},
                             {f'input_image_{i}': _small(r) for i, r in enumerate(refs)})
    url = f'{API}/accounts/{c["account_id"]}/ai/run/@cf/black-forest-labs/{MODEL}'
    log = []
    for attempt in (1, 2):
        req = urllib.request.Request(url, data=body, method='POST',
                                     headers={'Authorization': f'Bearer {c["token"]}', 'Content-Type': ctype})
        try:
            code, rtype, raw = _call(req)
        except OSError as e:
            log.append(f'attempt {attempt}: network error {e}')
            time.sleep(5)
            continue
        if code == 200 and rtype.startswith('image/'):
            img = raw
        else:
            try:
                res = json.loads(raw)
            except ValueError:
                res = {}
            img = base64.b64decode(res['result']['image']) if code == 200 and (res.get('result') or {}).get('image') else None
            if img is None:
                errs = res.get('errors') or [{'message': raw[:300].decode('utf-8', 'replace')}]
                text = '; '.join(f'{e.get("code", "")} {e.get("message", "")}'.strip() for e in errs)
                log.append(f'attempt {attempt}: HTTP {code}: {text}')
                low = text.lower()
                if code == 429 or '4006' in text or 'daily free allocation' in low or 'neurons' in low:
                    _limit(True)
                    return False, 0, '\n'.join(log + ["Cloudflare: the free daily allowance is used up. The web app checks once an hour and shows when FLUX is back."]), 'usage limit'
                if '3030' in text or 'nsfw' in low or 'safety' in low or 'moderat' in low:
                    return False, 0, '\n'.join(log + ['Blocked by the safety filter (moderation_blocked).']), 'blocked'
                if code < 500:
                    return False, 0, '\n'.join(log), f'HTTP {code}'
                time.sleep(5)
                continue
        from PIL import Image
        Image.open(io.BytesIO(img)).save(png, 'PNG')
        log.append(f'attempt {attempt}: ok, {w}x{h}, {len(refs)} reference(s), model {MODEL}')
        _limit(False)
        return True, neurons(w, h, len(refs)), '\n'.join(log), ''
    return False, 0, '\n'.join(log), 'failed twice'


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def _state():
    try:
        return json.loads(LIMIT.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _limit(hit):
    """Remember a used-up allowance (hit=True: first refusal kept, check time updated), or that FLUX works again."""
    st = _state()
    if hit:
        new = {'hit': st.get('hit') or _now(), 'checked': _now()}
    elif st.get('hit'):
        new = {'back': _now()}
    else:
        return
    LIMIT.parent.mkdir(parents=True, exist_ok=True)
    LIMIT.write_text(json.dumps(new), encoding='utf-8')


_probing = threading.Lock()


def _probe():
    """One tiny image (256x256, ~26 neurons) to see if the allowance is back. make() records the answer."""
    if not _probing.acquire(blocking=False):
        return
    try:
        import tempfile
        png = Path(tempfile.gettempdir()) / 'taste-cf-check.png'
        ok, _, _, why = make('a plain light grey square', 'check', [], png)
        if not ok and why != 'usage limit':
            _limit(True)          # network trouble etc.: try again next hour
        png.unlink(missing_ok=True)
    finally:
        _probing.release()


def today():
    """FLUX's day for the app. While the allowance is used up: when it ran out and when it was last checked (a free
    check runs in the background once an hour). Otherwise an estimate of neurons used since FLUX last came back
    (or since 00:00 UTC), from this laptop's runs; other use of the account is not seen."""
    import csv
    runs = ROOT / 'generated' / 'codex' / 'runs.csv'
    st = _state()
    if st.get('hit') and creds():
        checked = datetime.datetime.fromisoformat(st['checked'])
        if (datetime.datetime.now().astimezone() - checked).total_seconds() >= CHECK_EVERY:
            threading.Thread(target=_probe, daemon=True).start()
        hm = lambda t: datetime.datetime.fromisoformat(t).strftime('%a %H:%M')
        return {'connected': True, 'model': MODEL, 'used_up': True, 'used_up_since': hm(st['hit']),
                'checked_at': hm(st['checked']), 'images_today': 0, 'neurons_used': DAILY, 'daily': DAILY,
                'per_image': PER_IMAGE, 'images_left': 0}
    start = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if st.get('back'):
        start = max(start, datetime.datetime.fromisoformat(st['back']).astimezone(datetime.timezone.utc))
    used = made = 0
    if runs.exists():
        for r in csv.DictReader(open(runs, encoding='utf-8')):
            if r.get('route') != 'cloudflare' or r.get('ok') != 'yes':
                continue
            try:
                at = datetime.datetime.fromisoformat(f'{r["date"]}T{r["time"]}').astimezone(datetime.timezone.utc)
            except ValueError:
                continue
            if at >= start:
                made += 1
                used += float(r.get('tokens') or 0)
    left = max(0, DAILY - used)
    return {'connected': bool(creds()), 'model': MODEL, 'used_up': False, 'images_today': made,
            'neurons_used': round(used), 'daily': DAILY, 'per_image': PER_IMAGE, 'images_left': int(left // PER_IMAGE)}


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'today':
        print(json.dumps(today()))
    else:
        sys.exit(__doc__)
