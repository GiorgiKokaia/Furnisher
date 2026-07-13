# 07 — Room Image Generation

**Status:** M4 built — recipe v1 (`render3d/recipe.py`): room-crop grounding render +
product-photo grounding, content-hash caching, `furnisher render room` CLI, `/room` chat
command, 📷 buttons in the web app, feedback re-roll, and the whole-apartment isometric
cutaway (`generate_apartment_image`, 🏠 button). Verified live: MALM bed / PAX wardrobe /
MALM nightstand rendered recognizably as the actual products in planned positions; feedback
re-roll changed the mood while keeping the products. Observed fidelity: products, style,
and materials excellent; positions approximate; generic-catalog items (no photos) render
from their text descriptions.
**Depends on:** 01, 03 (product photos), 05 (placements), 06 (room-crop render), 04 (`furnisher/llm/`)
**Code home:** `src/furnisher/render3d/` (name reserved for the stretch goal; this is "2.5D")

## Purpose

Generate a photorealistic image per room that is **grounded in reality**: the actual chosen
catalog products, in approximately their planned positions, in a room of the right shape. This is the
"wow" output — and the grounding is what separates it from generic AI interior art.

## Model

Nano Banana = **`gemini-2.5-flash-image`** via the same `furnisher/llm/` wrapper as 04. It accepts
multiple input images + a text prompt and composes them — exactly the mechanism we need.

## Composition recipe (v0 — expect to iterate here more than anywhere else)

Inputs per room:

1. **Room-crop plan render** (06 mode 3): numbered footprints + camera marker.
2. **Product photos** from cache (03): 1–2 best images per item (prefer straight-on studio shots),
   each preceded in the prompt by its legend number and name.
3. **Text prompt** built from a template: room type + dimensions, ceiling height, window/door
   positions in words ("window on the left wall, door behind camera"), style profile (04) for
   walls/floor/lighting mood, camera description ("eye-level from the doorway, wide angle"), and
   the instruction that furniture must match the reference product images exactly and sit where
   the plan shows.

Practical limits: keep total input images modest (≤ ~10) — prioritize the biggest items; small
decor can be described in text. One generation call per room; a "re-roll with feedback" path
where the user's complaint ("the sofa is wrong color") is appended and the image regenerated.

## Honesty about fidelity

The model will approximate positions, not obey them exactly. The floor plan (06) remains the
source of truth for scale/placement; the room image is a *faithful visualization*, not a blueprint.
Say so in the UI. If positional fidelity is too poor in practice, the escalation path is a crude
3D mockup render as an additional grounding image — that's the bridge to 10 (2D→3D).

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
- [ ] Recipe iteration: v1 is strong on products/style, approximate on exact positions and
      window shapes; iterate when it matters. Apartment view: must say SINGLE-STORY
      explicitly or the model stacks a vertical plan into floors; plan text labels
      sometimes leak into the render as wall art — a label-free grounding variant of
      render_plan would fix that
- [x] Re-roll-with-feedback path (`--feedback`, changes the cache key)

## Open questions

- Multiple camera angles per room? Start with one good default per room type.
- Consistency across rooms (same wall color/flooring)? Include shared "apartment finish" text in
  every prompt from the style profile.
