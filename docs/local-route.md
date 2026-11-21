# Local route (personal PC)

A second way to make images, next to Codex: an image model running offline on Marc's personal PC, with no
content filter. Same styles, same rating app. Decided 21 Nov 2026: personal PC only, never the work laptop.

## Why
- Codex blocks the sensual end of the `erotic` style (Manara-like European comics: robe off a shoulder passes,
  a bare back, lingerie or a bath are blocked). A local model can do artistic adult nudes in that tradition.
- No allowance: images cost only electricity and time.

## Limits (fixed, not up for change)
- Adults only, always. No minors in any image, ever, and nothing sexual involving real or named people.
- Sensual and artistic nudes yes; explicit sex scenes no.
- `kalahari-documentary` stays documentary: no nudity, no children (see its avoid list).
- Model files come only from sources Marc picks and downloads himself.

## Set-up on the personal PC (Marc, once)
1. Clone this repo and open it in Claude Code (desktop app, Code tab).
2. Install the image app that fits the PC's graphics card:
   - NVIDIA: ComfyUI (portable build) – https://github.com/comfyanonymous/ComfyUI
   - Intel Arc: Intel AI Playground – https://github.com/intel/AI-Playground/releases
   - AMD: ask Claude Code first (support differs by card).
3. Download one SDXL-based model (about 7 GB) from a source you trust and put it in the app's models folder.
4. In Claude Code on that PC say: "set up the local route from docs/local-route.md".

## What Claude Code builds then
- `scripts/local_run.py`: same interface as `codex_run.py gen` (`--style`, `--subject`, `--mix`, `--slot`,
  `--extreme`, `--ratio`), sending the prompt to the local app's API (ComfyUI: `http://127.0.0.1:8188/prompt`)
  instead of Codex, and logging to the same `generated/codex/runs.csv` with `mode` = `local`.
- `batch.py --route local`, so batches, contact sheets and the rating app work unchanged.
- Prompt shape for SDXL: shorter than the Codex blocks (keywords first, under ~75 tokens per chunk), the
  style's avoid list as the negative prompt.
- First test: 4 `erotic` images with subjects one step beyond what Codex allows, then 4 `kalahari-documentary`
  to compare with Codex.
