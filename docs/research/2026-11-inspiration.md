# Inspiration for taste: public features of Midjourney, Lummi and four taste tools

Written 21 Nov 2026. Research only: nothing in `app/` or `scripts/` changed. Marc picks what to build; each pick gets
its own plan.

**Method and limits.** Public pages only, no sign-in, no downloads. Wording is summarised, images are never saved.
`docs.midjourney.com` answered every direct fetch with HTTP 403, so the Midjourney rows come from web-search
summaries of the official pages (linked) plus third-party guides where marked. Midjourney's own site (`/explore`)
was not opened. Features change fast; treat details as "as of Nov 2026, second-hand where marked". Lummi's home page
and docs were read directly. Krea, Cosmos, Recraft and Whisk/Mixboard are a lighter pass from search summaries.

## What taste already does (page by page)

Source: `app/guide.html`, `app/about.html`, README. Nothing in this list may come back as a "new" idea.

| Page | Already there |
|---|---|
| Header | Batches, Overview, Gallery, Taste, Guide, About, New run; run chip (progress, Log, queue); "N style suggestions" chip |
| Batches (home) | Now / Just finished card with Stop and Log; queue with Remove; search by name or style; kind filter; "only with images to rate"; rows grouped by day with thumbnail strips |
| A batch | Filters To rate / Rated / Ignored; Up / Down per tile; keyboard grid (arrows, U, D, I, Enter); placeholder tiles while making; Retry once / Copy prompt on failures; "Made from" and "How it was made"; New run with this style; Change the style; Open folder |
| Large view | Thumbs plus a why; Remix (R); Variations (V); Change the style (E); Note for Claude (C); Ignore; Fit / 1:1; hold S to flick back to the seed; details, palette, exact prompt with Copy |
| Rating | Thumb up/down saved at once, same thumb takes it back, optional why, Ignore with Undo; the panel says what the thumb moved |
| New run | Batch (styles, 1–8 per style, shape Mixed/Wide/Portrait/Square, wildcard, subjects written by you or Codex, direction hint, free prompt preview) and One image; cost block; Ctrl+Enter |
| Remix | What should change + quick picks, "must stay the same" ticks, reference on/off, Codex rewrites the prompt with a visible diff |
| Variations | Style guess (top 3), then one image each for palette, subject, composition, mood; extra add/remove text |
| Gallery | Justified rows of every image; filters Rating, Style, Batch (in the address); large view with thumbs, why, links to style and batch |
| Taste | Style cards with description, palette, light, composition, medium, mood, Avoid, Good for; "How new runs lean" (option odds from thumbs); Evidence (up to 8 Up, 4 Down with whys); "Changed from the app" with Undo |
| Change a style | Codex proposes the smallest edit, field-by-field diff with untick, Apply, Undo; or "add my words as they are" (Lean towards / Avoid) |
| Suggestions | Auto-distil every 20 ratings; per-style cards with the rated images, Codex's reading and edit; Apply / Skip; "Fine as they are" folded |
| Notes for Claude | Free notes from large view or Taste card; answered on Overview |
| Overview | Rating meter to next suggestion round, notes with answers, per-style up/down bars |
| Allowance | Cost block everywhere something spends; 5-hour and weekly meters; budget about 200 images a week |
| Guide / About | Everything above, 14 use cases, why the project exists |

**Known gap named in the Guide:** no button to keep one exact image as a reference example for its style.
**Not there:** compare two images side by side, free-form tags or folders, "more like this" by look, search by
colour, trying one subject across several styles at once, a pairwise "which one?" rating mode.

## Midjourney

| Feature | What it does | How you use it | Source |
|---|---|---|---|
| Personalization profile | Learns your aesthetic from images you pick; applied with a profile code; `--s` sets how strongly. Old flow was ranking image pairs; official docs now say pair ranking is replaced by picking from a grid (the Tasks-page "Rank Image Aesthetics" still feeds the global profile) | Pick images on the Personalize page, add `--p` to a prompt | [Personalization](https://docs.midjourney.com/hc/en-us/articles/32433330574221-Personalization) |
| Several profiles | Extra profiles for one look or project, each with an ID | "New Profile", copy the ID into a prompt | same page |
| Moodboards | A style built from images you choose (upload, links, or your own gallery); each gets a code | "New Moodboard", name it, add images; community guides say 40+ images give consistency (not official) | [Moodboards](https://docs.midjourney.com/hc/en-us/articles/39193335040013-Moodboards) |
| Style reference codes (`--sref`) | A code stands for a look; `--sref random` gives a surprise; `--sw` sets strength; several can be mixed | Add the code to a prompt | [Style Reference](https://docs.midjourney.com/hc/en-us/articles/32180011136653-Style-Reference) |
| Style Explorer | Browse style codes visually, sort Random or Popular, "Try style" re-runs your prompt with it, "Search similar styles", like to save | Website only | [Website Overview](https://docs.midjourney.com/hc/en-us/articles/33329460426765-Website-Overview) |
| Style Creator | You pick images from a grid, what you pick and skip builds a new reusable style code | Website only | [Style Creator](https://docs.midjourney.com/hc/en-us/articles/41308374558221-Style-Creator) |
| Explore feed | Community images with creator, prompt, settings; views For You (driven by your profile), Random, Hot, Top; hover shortcuts: reuse prompt, find similar, like; Likes tab | Website | [Website Overview](https://docs.midjourney.com/hc/en-us/articles/33329460426765-Website-Overview) |
| Organize | Folders (an image can be in several), timeline bar, search by keyword, date, reference image or parameter, bulk download, generate inside a folder; smart folders per third-party guides | Website | [Website Overview](https://docs.midjourney.com/hc/en-us/articles/33329460426765-Website-Overview); [guide](https://geekycuriosity.substack.com/p/midjourney-organizing-your-images) (third party) |
| Editor and Retexture | Pan, zoom out, vary a region; Retexture re-skins an image's surfaces from a prompt plus a style; works on outside images too | Editor on the website | [Modifying Your Creations](https://docs.midjourney.com/hc/en-us/articles/33329329805581-Modifying-Your-Creations) |
| Omni reference (`--oref`, `--ow`) | Carries a subject or character from a reference image into new images; newer models fold this into an "edit" model | Add the image and a weight | [guide](https://www.aiarty.com/midjourney-guide/midjourney-omni-reference.htm) (third party) |
| Vary Subtle / Strong | Same image with small or larger changes | Buttons under an image | [Variations](https://docs.midjourney.com/hc/en-us/articles/32692978437005-Variations) |
| Describe | Turns an image into four prompt suggestions, a guide not a copy; "Use prompt" or "Run all four" | Drop an image on the panel, or right-click an image | [Describe](https://docs.midjourney.com/hc/en-us/articles/32497889043981-Describe) |

## Lummi

| Feature | What it does | How you use it | Source |
|---|---|---|---|
| Three-way library | AI-made photos, illustrations and 3D in separate sections; creator profile on each image; "Daily picks" | Home page | [lummi.ai](https://www.lummi.ai) |
| Search with colour | Text search plus a colour picker or hex code | Palette icon in the search bar | [Getting started](https://docs.lummi.ai/about-lummi/welcome-to-lummi-ai/getting-started) |
| Filters | Orientation (square, vertical, horizontal), number of people, lighting (bright, dark, neutral) | Search tools menu | [Updates](https://www.lummi.ai/updates) |
| Similar images | On any image, "Similar images" by Subject or by Vibes | Scroll below the image | [Getting started](https://docs.lummi.ai/about-lummi/welcome-to-lummi-ai/getting-started) |
| Collections | Curated collections to browse; save favourites into your own | Collections page | [Docs home](https://docs.lummi.ai/) |
| Create Similar | Up to three new versions of an image, keeping its colours, textures and composition; optional prompt; reference from library or upload | "Use to create" on an image | [Create Similar](https://docs.lummi.ai/about-lummi/pro-features/create-similar) |
| Styles (Pro beta) | Nine one-click transformations such as pixel art, comic, sketch | Create tool | [Updates](https://www.lummi.ai/updates) |
| Edit tools | Reframe, retouch (edit an area by prompt), upscale, background removal | Tools on an image | [Docs home](https://docs.lummi.ai/) |
| Trending | Currently popular images for ideas | Home | [Docs home](https://docs.lummi.ai/) |

Presentation note: Lummi shows AI images as a calm, curated stock library: big grid, few controls, the
creator behind each image, and everything one click from "more like this". It does not foreground prompts.

## Krea (lighter)

| Feature | What it does | Source |
|---|---|---|
| Style references | Up to 4 reference images, a strength slider each | [Krea 2 guide](https://www.krea.ai/docs/user-guide/features/krea-2) |
| Moodboards | A saved set of images read for palette, mood and concept; one strength slider per use; a gallery of curated moodboards | [Krea vs Midjourney](https://www.krea.ai/blog/krea-2-vs-midjourney) |
| Trained styles (LoRA) | Train a style from a small image set, private by default, stack several with strengths | [Krea 2](https://www.krea.ai/krea-2) |
| Guidance: when to use which | References for precise matching, moodboards for a longer-lived aesthetic | [Krea 2 guide](https://www.krea.ai/docs/user-guide/features/krea-2) |

## Cosmos.so (lighter)

| Feature | What it does | Source |
|---|---|---|
| Clusters | Themed collections, private or shared, flexible rather than strict boards | [creativity.sh](https://www.creativity.sh/notes/what-is-cosmos) |
| Search by colour, image or text | One search box, three ways in | [Wix Studio review](https://www.wix.com/studio/blog/cosmos-app) |
| Auto-tags | Colour, mood and style detected on everything you save | [UI breakdown](https://screensdesign.com/showcase/cosmos-curated-inspiration) |
| Related discovery | Results lead to endless related images you can add to a cluster | [UI breakdown](https://screensdesign.com/showcase/cosmos-curated-inspiration) |
| Quick capture | Right-click or extension saves an image in one step | [creativity.sh](https://www.creativity.sh/notes/what-is-cosmos) |

## Recraft (lighter)

| Feature | What it does | Source |
|---|---|---|
| Custom styles | Style from up to 10 reference images; guide advises one reference when unsure because mixed worlds collide | [Recraft review](https://promer.ai/blog/recraft-ai-review) |
| Palette control | Exact hex palettes, extract a palette from any image, save and reuse | [Recraft overview](https://www.eesel.ai/blog/recraft-ai) |
| Image sets | Up to 6 prompts sharing one style, palette and ratio; regenerate one frame only | [Recraft blog](https://www.recraft.ai/blog/how-to-create-image-sets) |

## Google Whisk and Mixboard (lighter)

| Feature | What it does | Source |
|---|---|---|
| Whisk: subject + scene + style slots | Three image inputs instead of a long prompt; swap one and re-run; dice fills an empty slot | [Google blog](https://blog.google/innovation-and-ai/models-and-research/google-labs/whisk/) |
| Mixboard: concept board | Start from text, a template or your images; edit by plain request ("more autumn"); "Regenerate" and "more like this" on any item | [VP Land](https://www.vp-land.com/stories/google-s-mixboard-takes-aim-at-creative-concepting-with-ai-powered-mood-boards) |
| Mixboard: board-aware text | Titles and palette drafted from what is on the board | [Yahoo/Tech](https://tech.yahoo.com/ai/gemini/articles/google-mixboard-turns-ai-mood-130849910.html) |

## Ideas

Effort: S = a day or less, M = a few days, L = a week or more. "Fit" is against the app's limits (local only, Codex
allowance about 200 images a week, plain HTML/CSS/JS plus Python standard library and Pillow, calm UI, one-click
decisions).

| # | Idea | Where | What it looks like | Why it helps | Effort | Fit | From |
|---|---|---|---|---|---|---|---|
| 1 | **Keep as reference** | Large view, Gallery large view, Taste card | A "Keep as example" button next to the thumbs; kept images show first in the style's Evidence and are sent along as references in new runs | Closes the gap the Guide names. Recognition over description: one click instead of writing it | S–M | No allowance cost, local file only | Midjourney moodboards, Krea moodboards, Recraft custom styles |
| 2 | **More like this (by look)** | Large view, Gallery | "More like this" row of the nearest existing images, from the colour and composition numbers `nearest.py` already computes | Browsing by resemblance is faster than filtering; Gestalt similarity does the work. Costs no images | S–M | Local, reuses existing code | Lummi Similar images, Midjourney hover "find similar", Cosmos |
| 3 | **Search by colour** | Gallery | A palette swatch in the filter bar; pick a colour or click a swatch from any style palette; rows reorder by closeness | Colour is perceived before anything else; one gesture instead of text | S | Pillow is enough | Lummi colour search, Cosmos |
| 4 | **Which one? (pair rating)** | Batches / Gallery | A calm full-screen "A or B?" for images of one style, keys ← →; each choice becomes an Up for one, Down for the other | Comparing is faster and more reliable than judging alone, and gives many ratings quickly toward the 20-rating suggestion round | M | No allowance cost; reuses `PUT /api/mark` | Midjourney personalization ranking |
| 5 | **Try this subject in other styles** | Large view | One tick: same subject, 2–3 chosen styles, one batch (a Variations option beyond palette/subject/composition/mood) | Direct side-by-side of styles on one subject; one change, one lesson | M | Spends images, cost block shows it first; fits the queue | Whisk slots, Midjourney Try Style, Recraft image sets |
| 6 | **Compare two** | Gallery, batch | Select two images, flick between them in place (the "hold S" idea generalised) | Flicking in place shows differences better than side by side | S | Local | Existing hold-S pattern; Midjourney Organize |
| 7 | **Style strength slider on a run** | New run | "How strongly the style leans" with three steps (loose, normal, strict) | Gives control without words; shows the trade-off before spending | M | Needs prompt-builder change; no extra cost | Midjourney `--s` / `--sw`, Krea strength sliders |
| 8 | **Image to subject ideas (describe)** | New run, Taste card | Drop or pick an image; Codex (read-only text job) suggests 4 subjects and what the style should keep | Turns "I know it when I see it" into words without typing | M | Text job, no images spent | Midjourney Describe |
| 9 | **Style surprise** | New run | A "Surprise me" button picks a style you rated least recently and a subject Codex writes | Reduces choice load when you just want something | S | Spends images, cost shown | Midjourney `--sref random`, Whisk dice |
| 10 | **Collections inside the app** | Gallery, Taste | Name a set of images ("for LinkedIn"); any image can be in several; one-click filter | Groups what works for a purpose; cuts search | M | Local file; avoid duplicating style cards | Lummi collections, Cosmos clusters, Midjourney folders |
| 11 | **Palette from an image** | Change a style | "Take the palette from this image" adds the measured colours as a proposal (diff, Apply, Undo) | Colour is measured, so no guessing; one click | S–M | Pillow already used for palettes | Recraft palette extraction |
| 12 | **Timeline / date scrub in Gallery** | Gallery | A thin bar to jump by week | Orientation in 1,000 images; less scrolling | S | Local | Midjourney Organize timeline |
| 13 | **Reframe an image** | Large view | One-click other shape (wide / portrait) of the same image | Reuse for posts and wallpapers | M | Spends images; may duplicate Remix | Lummi Reframe |

## Shortlist (best first)

1. **Keep as reference** (idea 1). Why first: it is the one gap the Guide admits, costs no allowance, and
   turns every thumb-up into lasting evidence in one click. Page: Large view, Gallery, Taste. Effort: S–M.
   Source features: Midjourney moodboards, Krea moodboards.
2. **More like this (by look)** (idea 2). Why: free, fast, makes the Gallery explorable by resemblance, and reuses
   `nearest.py`. Page: Large view and Gallery. Effort: S–M. Source: Lummi Similar images, Midjourney find similar.
3. **Which one? pair rating** (idea 4). Why: the fastest way to get the 20 ratings that drive suggestions, and
   comparing is easier on attention than absolute judging. Page: Batches / Gallery. Effort: M. Source: Midjourney
   personalization ranking.
4. **Search by colour** (idea 3). Why: smallest effort with the clearest perceptual win; a small addition to a page
   Marc already uses. Page: Gallery. Effort: S. Source: Lummi colour search, Cosmos.
5. **Try this subject in other styles** (idea 5). Why: answers "which style suits this?" directly, and
   fits "one change, one lesson". Page: Large view. Effort: M. Source: Whisk, Midjourney Try Style, Recraft sets.
6. **Style strength on a run** (idea 7). Why: one calm control that makes a hidden knob visible before it spends.
   Page: New run. Effort: M. Source: Midjourney `--s`/`--sw`, Krea sliders.
7. **Image to subject ideas** (idea 8). Why: converts a liked image into words, the project's core translation,
   with no images spent. Page: New run, Taste card. Effort: M. Source: Midjourney Describe.
8. **Collections** (idea 10). Why: lets finished work be grouped by purpose; last because it adds structure
   to maintain. Page: Gallery. Effort: M. Source: Lummi, Cosmos, Midjourney folders.

## Rejected and why

| Idea | Why not |
|---|---|
| Community Explore feed, public sharing, likes by others (Midjourney, Lummi, Cosmos) | The app is local, single-user and private; others' images are not Marc's evidence |
| Accounts, credits, plans, Pro tiers (Lummi, Midjourney, Krea) | No accounts; images run on the ChatGPT plan with a fixed weekly budget |
| Training custom models / LoRA (Krea, Recraft) | Codex CLI has no fine-tuning; styles stay written text, which is the point of the project |
| Sref-style numeric codes or `--p` parameters in a prompt | Tech steps on Marc's side; the app's thumbs and style cards already do this without codes |
| Omni-reference character locking (Midjourney) | Characters are not a goal; "Send this image as a reference" in Remix already covers the need |
| Video generation (Lummi) | Out of scope; Codex route makes images |
| Background removal, upscaling, retouch regions (Lummi, Midjourney editor) | Not about taste; image editors do these better; heavy to build |
| Stock-library browsing of other creators' images | Wallpapers belong to their creators and stay private (README) |
| Vector/SVG output (Recraft) | Not available through Codex images |
| Mixboard-style infinite canvas | A large build for a calm, simple UI; Gallery plus collections covers most of it |
| Third-party smart folders (auto-grouped by search) | Overlaps with "More like this" and saved filters already in the address |
| Trending / daily picks | No audience; replaced by "Surprise me" at best (idea 9, not shortlisted) |

Ideas 6, 9, 11, 12 and 13 stay in the ideas table unranked: small or overlapping with the shortlist.
