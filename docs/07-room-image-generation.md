# 07 — Room Image Generation

**Status:** M4 built — recipe **v2** (`render3d/recipe.py`): room-crop grounding render +
product-photo grounding + a **programmatic layout→text spatial brief** (`render3d/describe.py`),
content-hash caching, `furnisher render room` CLI, `/room` chat command, 📷 buttons in the web
app, feedback re-roll, and the whole-apartment isometric cutaway (`generate_apartment_image`,
🏠 button). Verified live: MALM bed / PAX wardrobe / MALM nightstand rendered recognizably as
the actual products in planned positions; feedback re-roll changed the mood while keeping the
products. Recipe v2 markedly improved **positional fidelity** — a live living-room render placed
both far-wall windows, the TV bench on the far wall, the armchair on the left wall, and the
sofa/coffee-table in the foreground exactly as the brief stated. Observed fidelity: products,
style, materials, and now placement/window-count faithful; generic-catalog items (no photos)
render from their text descriptions.
**Depends on:** 01, 03 (product photos), 05 (placements), 06 (room-crop render), 04 (`furnisher/llm/`)
**Code home:** `src/furnisher/render3d/` (name reserved for the stretch goal; this is "2.5D")

## Purpose

Generate a photorealistic image per room that is **grounded in reality**: the actual chosen
catalog products, in approximately their planned positions, in a room of the right shape. This is the
"wow" output — and the grounding is what separates it from generic AI interior art.

## Model

Nano Banana = **`gemini-2.5-flash-image`** via the same `furnisher/llm/` wrapper as 04. It accepts
multiple input images + a text prompt and composes them — exactly the mechanism we need.

## Composition recipe (v2)

Inputs per room:

1. **Room-crop plan render** (06 mode 3): numbered footprints + camera marker.
2. **Product photos** from cache (03): 1–2 best images per item (prefer straight-on studio shots),
   each preceded in the prompt by its legend number and name.
3. **Text prompt** built from a template: room type + dimensions, ceiling height, style profile
   (04) for walls/floor/lighting mood, camera description, the instruction that furniture must
   match the reference product images exactly — and, as of v2, a **programmatic spatial brief**
   (`render3d/describe.py`, see below) that the schematic alone couldn't convey.

### Programmatic layout→text (`render3d/describe.py`) — why v2 is faithful

The schematic image alone let the model "reinterpret" the plan (wrong window counts, furniture
drifting to other walls). The fix is deterministic, pure-geometry text generated from the same
plan + placements and fed alongside the image, told to be the ground truth on any disagreement:

- **Walls & openings** — one line per wall (compass name + length) listing its windows/doors, so
  "two windows on the north wall" is stated, not inferred from bars in a drawing.
- **Camera** — `room_camera()` reproduces the same viewpoint the crop render marks (just inside
  the first door, looking in), so schematic and text agree.
- **Per-item placement** — for each piece (biggest first): which wall/corner it's against, where
  it falls in the *camera frame* (left/centre/right × foreground/mid/far, computed by projecting
  the item onto the camera's forward/right axes), and which way it faces (compass + relative to
  camera). "Do not rearrange, add, or drop furniture."

`describe_apartment_layout()` does the analogous thing for the 🏠 dollhouse: room quadrant +
adjacency (from openings) + per-room furniture list, so rooms and their contents don't get
shuffled or merged.

Practical limits: keep total input images modest (≤ ~10) — prioritize the biggest items; small
decor can be described in text. One generation call per room; a "re-roll with feedback" path
where the user's complaint ("the sofa is wrong color") is appended and the image regenerated.

## Honesty about fidelity

The room image is a *faithful visualization*, not a blueprint — the floor plan (06) remains the
source of truth for exact scale/placement. That said, recipe v2's spatial brief closed most of
the gap: wall assignment, window counts, and camera framing now come out right in practice. If
positional fidelity is ever too poor, the escalation path is a crude 3D mockup render as an
additional grounding image — the bridge to 10 (2D→3D).

## Evaluation (manual, cheap)

A `furnisher render room living-room` CLI that dumps: the composed prompt, the input images, and
the output — side by side in an HTML file. Iterating on the recipe *is* the work; make the loop
fast. Keep every experiment's inputs/outputs under `experiments/room-renders/` (gitignored except
notes) and record recipe learnings in this doc.

## Cost note

Image generation bills per image on the personal key; cache outputs in the project dir keyed by a
hash of (placements, style, recipe version) so unchanged rooms never regenerate.

## Tasks

- [x] `generate_image` support in `furnisher/llm/` (multi-image input)
- [x] Prompt template + input-image selection logic (biggest items get photos, ≤5)
- [x] Output caching by content hash (placements + style + recipe version + feedback)
- [x] `furnisher render room <project> <room>` CLI; prompt + grounding plan dumped next to
      each output for inspection
- [x] Recipe v2: programmatic layout→text spatial brief (`render3d/describe.py`) for walls,
      camera framing, and per-item placement — fixed the "approximate positions / wrong window
      count" weakness of v1; RECIPE_VERSION bumped so old caches regenerate
- [x] Apartment view says SINGLE-STORY explicitly (v1) + gets a room-arrangement brief (v2)
- [x] Re-roll-with-feedback path (`--feedback`, changes the cache key)
- [ ] Still open: plan text labels can leak into the render as wall art — a label-free
      grounding variant of `render_plan` would fix that

## Open questions

- Multiple camera angles per room? Start with one good default per room type.
- Consistency across rooms (same wall color/flooring)? Include shared "apartment finish" text in
  every prompt from the style profile.
