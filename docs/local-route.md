# Local route (this laptop)

A second way to make images, next to Codex: open image models running offline on this laptop through ComfyUI,
with no tokens and no daily limit. Same styles, same rating app. Decided 21 Nov 2026 for a personal PC only;
changed 25 Nov 2026 (Marc): it runs on this laptop.

## Why
- Codex blocks the sensual end of the `erotic` style (Manara-like European comics: robe off a shoulder passes,
  a bare back, lingerie or a bath are blocked). A local model can do artistic adult nudes in that tradition.
- No allowance: images cost only electricity and time.

## Limits (fixed, not up for change)
- Adults only, always. No minors in any image, ever, and nothing sexual involving real or named people.
- Sensual and artistic nudes yes; explicit sex scenes no.
- `kalahari-documentary` stays documentary: no nudity, no children (see its avoid list).
- Model files come only from sources Marc picks and downloads himself.

## How it runs (25 Nov 2026)
- ComfyUI in `%USERPROFILE%\ComfyUI` (Intel Arc), API at `http://127.0.0.1:8188`. It starts by itself, hidden,
  when a local run needs it, and lets go of the memory after the run.
- Seven models, each with a badge in the app: FLUX local (FLUX.2 klein 4B), Z-Image (Z-Image Turbo 6B),
  Playground (Playground v2.5) and, since 26 Nov 2026, four SDXL community fine-tunes: DreamShaper XL Lightning,
  Juggernaut XL Lightning, ZavyChroma XL v10 and Animagine XL 4.0 (CreativeML Open RAIL++-M; settings in
  `local_run.SDXL`). The Models page compares them and sets each style's default.
- `scripts/local_run.py` makes one image; `codex_run.py gen --route local --model <m>` calls it, so batches,
  remixes, variations, contact sheets and ratings work unchanged. Runs log to `generated/codex/runs.csv` with
  route `local` and session `local:<model>`.
- Local only (Models page): only these models run, and Ollama writes subjects and prompt rewrites
  (`codex_text.py --local`). ComfyUI and Ollama never hold memory at once.
