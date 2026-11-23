# Cloudflare route (plan, 23 Nov 2026)

A third way to make images, next to Codex and the [local route](local-route.md): open FLUX models on Cloudflare
Workers AI, on its free daily allowance. Same styles, same subjects, same rating app. Status: **built 23 Nov
2026**; waiting for Marc to connect Cloudflare, then the first comparison batch.

## Why
- Free: 10,000 "neurons" a day, no card. Past the limit calls fail instead of billing (Workers Free plan).
- Has an API, so it runs behind the scenes like Codex; images are private (FLUX schnell is listed as zero data
  retention), unlike Leonardo's or Pollinations' free tiers, which publish every image and prompt.
- Spare capacity for volume and first drafts when Codex's weekly allowance is needed for other work.
- Not a replacement: ChatGPT's images are stronger on complex scenes and close style matching.

## Which model (prices from Cloudflare's pricing page, 23 Nov 2026)

| Model | Cost of one ~1 MP image | Free images a day | Ratios | References |
|---|---|---|---|---|
| `flux-2-klein-4b` (**used**) | ~104 neurons (4 output tiles); ~115 with 2 references | **~95**, ~87 with references | yes, 256–1920 px a side | yes, up to 4, each under 512 px |
| `flux-1-schnell` (fallback) | ~58 neurons (4 tiles, 4 steps) | **~170** | square only (no size option documented) | no |
| `flux-2-klein-9b`, `flux-2-dev`, `lucid-origin` (Leonardo), `phoenix-1.0` | 1,300–3,000+ | 3–7 | – | some |

The big models cost too much for the free allowance; they are out. Cloudflare's changelog for `klein-4b`
(15 Jan 2026) settled the size and reference questions, so no probe was needed: fixed 4 steps, `width` /
`height`, `input_image_0..3` (each under 512 × 512), multipart form. Sizes used (4 output tiles each): wide
1024 × 576, portrait 816 × 1024, square 1024 × 1024. References are shrunk to 496 px.

## What was built
1. (Probe dropped: the docs answered it. The first real images are the check.)
2. **`scripts/cf_run.py`**: the Cloudflare call (`POST https://api.cloudflare.com/client/v4/accounts/<id>/ai/run/@cf/black-forest-labs/<model>`),
   JPEG → PNG, same file names as Codex. One attempt and one retry; "allowance used up" (HTTP 429 / 4006) stops
   the run with "Free images for today are used up; they come back at 01:00".
3. **`codex_run.py gen --route codex|cloudflare`** (default `codex`, or the `TASTE_ROUTE` environment variable):
   same prompt from `compose()`, so styles, looks, mixes, wildcards and leaning work unchanged; the Codex-only job
   text (image_gen, copy the PNG) is not sent. The web app sets `TASTE_ROUTE` for its run, and `batch.py`,
   `run_list.py` and `variations.py` pass their environment on, so they needed no change. From chat:
   `TASTE_ROUTE=cloudflare .venv/Scripts/python -I scripts/batch.py ...`.
4. **Run log**: a `route` column at the end of `generated/codex/runs.csv` (the header is rewritten once; old rows
   read as `codex`). Neurons per image go in `tokens`, computed from the documented price, labelled as an
   estimate (Cloudflare's run reply doesn't report them).
5. **Web app**
   - **Connect Cloudflare** (once): a small card with a link to Cloudflare's API-token page, two fields (account
     ID, token) and **Save**. Saved outside the repo in `%USERPROFILE%\.taste\cloudflare.json`; never logged or
     shown again.
   - **New run, One image, Remix, Variations**: a calm "Made with" choice, *ChatGPT* (default) or *FLUX, free*,
     with "~62 left today" next to it. Variations that need the seed as a reference offer FLUX only if the
     probe shows reference images work.
   - The cost block shows FLUX images made today, about how many are left and when more come.
   - "How it was made" on a batch shows the route. (Not built yet: a header chip and an Insights filter by route;
     worth adding once there are FLUX ratings to compare.)
6. **Guide** (`app/guide.html`): Connect Cloudflare, the "Made with" choice, the daily limit. README changelog.

## Ratings and leaning
Thumbs on FLUX images count for leaning like any other: leaning steers light, framing, mood and palette options,
which are the same on both routes. Open point for later: if FLUX images get many more thumbs down overall, the
model, not the option, is to blame; then leaning would count each route on its own. Insights' route filter shows it.

## Marc's part
1. Make a free Cloudflare account (Workers Free plan) and an API token with the *Workers AI* permission, then
   paste the account ID and token into **Connect Cloudflare** in the web app. About 5 minutes, once.
2. Rate the first comparison batch: 2 styles × 4 images on each route, same subjects.

## Limits
- The free allowance is per Cloudflare account and resets at 00:00 UTC (01:00 in Spain in winter, 02:00 in
  summer).
- Cloudflare applies its own content rules; the `erotic` style's sensual end stays with the local route.
- Prompts go to Cloudflare (not published). Nothing else leaves the laptop: no ratings, no style files.

## Size of the build
One Claude Code session, about 6 files touched (`cf_run.py` new; `codex_run.py`, `batch.py`, `run_list.py`,
`variations.py`, `app.py` plus the page and guide). No Codex allowance used; Cloudflare probe ~400 neurons.
