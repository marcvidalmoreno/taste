# taste

My visual taste, written so an image model can use it. I'm Marc, a UX designer, and I use it to make
images for my posts with Google's Nano Banana (Gemini image generation).

## What's here
- [`taste/styles/`](taste/styles/): five sub-styles found in about 1,100 wallpapers I've saved over the years,
  each with a palette, light, composition, medium, mood and an **avoid** list.
- [`taste/gem-instructions.md`](taste/gem-instructions.md): instructions for a Gemini Gem that uses the styles.
- [`scripts/`](scripts/): `pack.py` builds a prompt pack for a post, `inbox.py` sorts newly liked images into
  the closest style, `build/` is how the styles were found (colour and composition clustering, k-means).
- [`generated/`](generated/): images **I** generated with these styles, with the prompts used.

## What's not here, on purpose
The wallpapers themselves and every reference image belong to their creators. They stay on my laptop
(git-ignored) and are never published. Only the derived descriptions and my own generated images are public.

## How it works
1. For a post, Claude Code picks the styles that fit, writes one subject per style and runs
   `scripts/pack.py`, which writes `generated/<date>-<slug>/PROMPTS.md` plus three style references per style.
2. I paste each prompt into the Gemini app with its references (free with my Google AI plan; the Gemini API has
   no free tier for image models) and save the result next to the prompts.
3. Images I like later go into `inbox/`; `scripts/inbox.py` files them under the closest style and the style
   descriptions get updated.
