# How a folder of images becomes a style

How this repo turns a folder of images I like into written styles, and what the machine did versus what a
person (or Claude, looking) did. Written for me and for anyone who forks the repo.

```
folder of images
   │
   ▼
thumbnails (64×64 px) ──► numbers per image (colour, brightness, layout, busyness)
   │                            │
   │                            ├─► 8 Nov: k-means clusters (cluster0..4)   ← colour, not meaning
   │                            └─► 14 Nov: triage "fits <style>" / "new"   ← a hint only
   ▼
contact sheets (48 thumbnails, ~150 px each)
   │
   ▼
tagging by eye (subject, medium, mood, light) ──► styles, approved one by one
   │
   ▼
numbers again: palette (5 base colours + 2 accents) and 8 exemplars per style
   │
   ▼
taste/styles/*.json ──► scripts/build_taste.py ──► taste/taste.json
```

## 1. Numbers from pixels (8 Nov 2026)
Every image is shrunk to a 64×64 thumbnail and described by a short list of numbers
([`scripts/features.py`](../scripts/features.py)): how bright it is and how much that varies, how saturated, a
12-bin hue histogram (how much of each colour), a 4×4 brightness grid (a rough map of where the light is, so
composition), edge density (how busy it is), aspect ratio and the share of grey pixels.

Think of it as peripheral vision: what you'd notice from across the room, before you know what the picture shows.

**Duplicates** ([`build/inventory.py`](../scripts/build/inventory.py), [`build/dupes.py`](../scripts/build/dupes.py)):
each image gets a perceptual hash, a 64-bit fingerprint of its rough light-and-dark shape. Two images 6 bits or
fewer apart are the same picture, even resized or recompressed. The largest file is kept.

## 2. Clusters: grouping by similarity (8 Nov)
[`build/cluster.py`](../scripts/build/cluster.py) puts all images on the same scale (standardising), squeezes
the numbers down to the 12 directions that vary most (PCA, a way to drop redundant measures), then runs
**k-means**: pick *k* centres, give each image to the nearest one, move each centre to the middle of its group,
repeat until nothing moves. I tried k = 4, 5 and 6 and kept 5.

`taste/data/contact-sheets/cluster0.jpg … cluster4.jpg` ([`build/sheets.py`](../scripts/build/sheets.py)) are a
random 48 members of each group, 8 × 6 thumbnails.

**The limit:** this is Gestalt similarity by colour and layout only. `cluster0` is "dark, magenta-blue neon"
whether it shows a city, a face or a planet. It never knew what anything was.

**Exemplars** ([`build/exemplars.py`](../scripts/build/exemplars.py)): the 8 members closest to a group's centre
(the most typical, the prototype in perception terms), keeping only large landscape files and at most 3 per
sub-folder. The old sheets `exemplars-neon-dusk.jpg`, `-deep-space-dark`, `-warm-interiors-japan`,
`-bright-airy-minimal`, `-retro-sci-fi-painting` are these 8 Nov ones.

## 3. Rebuild: tagging by eye (13 Nov)
Colour groups made poor styles, so the taste was rebuilt. Claude looked at every wallpaper on contact sheets and
tagged subject, medium, mood and light; I approved each style one by one. The numbers now do only two jobs
([`build/restyle.py`](../scripts/build/restyle.py)):
- **Palette:** k-means on the pixels of all members: 5 base colours (sorted dark to light) plus 2 vivid accents.
- **Exemplars:** the 8 members closest to the style's average, large files first.

How weak colour alone is, measured: [`scripts/nearest.py`](../scripts/nearest.py) guesses a style from pixels and
is right 36 % of the time as first choice, 63 % within its top 3. So every guess is shown as a top 3 and confirmed
by eye.

## 4. Adding a collection (14–15 Nov, the ART folder)
[`scripts/ingest.py`](../scripts/ingest.py) does inventory, dedupe and a colour **triage**: images close to an
existing style land on "fits <style>" sheets, the rest on "new" sheets. On ART the triage was wrong (Dubuffet,
Escher, Léger and Asterix landed under japanese-print by colour), so Claude made sheets sorted by folder and tagged
all 798 images by eye. The tags stay local (`taste/data/collections/art/tags.json`);
[`build/collection_styles.py`](../scripts/build/collection_styles.py) measured palettes and exemplars, and 8 style
files were written.

## Did Claude actually see the images?
Yes, but small. Claude saw **thumbnails of about 150 px**, 48 to a contact sheet, through image reading, never
the full-resolution files. It identified content from three things:
1. what it could see at that size,
2. the **folder names** (artist names such as MICHEL GOYON, HOKUSAI, MOEBIUS),
3. its **own training knowledge** of those artists and styles.

**No web search and no reverse-image lookup** were used.

What that means:
- Small details (text, faces, fine linework) can be missed at 150 px.
- Recognising an artist leans on the folder name more than on the picture.
- An image filed in the wrong folder can get the wrong tag.

Cheap check: open a few `taste/data/contact-sheets/exemplars-<style>.jpg` and see whether the 8 look like the style.

## Words used here
- **Feature vector:** the list of numbers that stands in for an image.
- **k-means:** grouping by repeatedly moving *k* centres to the middle of their nearest points.
- **PCA:** keeping the few combinations of numbers that vary most, dropping the redundant rest.
- **Perceptual hash:** a fingerprint of an image's coarse shape that survives resizing.
- **Exemplar:** a member close to the group's average, the most typical one.
