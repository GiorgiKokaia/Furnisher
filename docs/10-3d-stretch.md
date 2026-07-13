# 10 — 2D→3D (Stretch Goal)

**Status:** parked — do not build; this doc exists so earlier decisions don't paint us into a corner

## The idea

From the same project state (plan + placements + catalog items), produce an explorable 3D scene —
or at minimum, 3D-rendered views that replace/augment the Nano Banana images with geometrically
exact ones.

## Why the current design already supports it

- The schema (01) is fully 3D-capable in the ways that matter: heights everywhere (ceiling, door,
  window + sill), footprints + item heights, real meters.
- Extruding room polygons into wall meshes + cutting openings is straightforward geometry.
- Catalog items have bounding boxes; IKEA 3D models exist in the wild (many products have `.glb`
  assets on product pages / third-party mirrors) — the catalog `raw` payload (03) is kept
  precisely so we can mine it later for model URLs.

## Likely path, when the time comes

1. **Level 0:** extrude plan to walls/floor + items as labeled boxes → export `.glb`
   (`trimesh` does all of this). Viewable in any glTF viewer / `<model-viewer>` in the web app.
2. **Level 1:** swap boxes for real product models where obtainable.
3. **Level 2:** use Level-0/1 renders (from a fixed camera, via `pyrender` or Blender headless) as
   the *grounding image* for Nano Banana instead of the 2D room crop — geometrically exact
   composition + photoreal materials. This is the realistic sweet spot and directly upgrades 07.

## Constraints on today's decisions (the actual content of this doc)

- Don't strip heights out of the schema "because 2D doesn't need them." (Already honored.)
- Keep `CatalogItem.raw` (03) so 3D asset URLs can be mined without re-fetching.
- 07's grounding-image input should stay pluggable — a 3D render must be able to replace the 2D
  room crop without changing the recipe's structure.
