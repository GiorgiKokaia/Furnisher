# 06 — 2D Floor Plan Renderer

**Status:** empty-plan mode built (`src/furnisher/render2d/`); furnished + room-crop modes pending
**Depends on:** 01 (schema), 03 (item names for labels)
**Code home:** `src/furnisher/render2d/`

## Purpose

Draw the floor plan — empty (for authoring preview, 02) and furnished (final output, and the
spatial grounding input for room image generation, 07). SVG as the primary target (crisp, easy to
generate by hand, trivially converted to PNG when a raster is needed).

## Output modes

1. **Empty plan** — walls, room fill by type, room label (`name`, `type`, `area m²`), door arcs,
   windows as double lines, dimension annotations on exterior edges. Used by `plan preview` (02).
2. **Furnished plan** — the above + item footprints: rotated rectangle, subtle fill, item short
   name + footprint size (`KIVIK 228×95`). This is a primary product output.
3. **Per-room crop for image grounding (07)** — one room, tight crop, footprints labeled with
   numbers matching a legend; optionally a camera-position marker. Minimal styling — its consumer
   is a vision model, so clarity beats beauty: high contrast, no decorative fills, unambiguous
   labels.

## Implementation

- Hand-rolled SVG via `svgwrite` or plain string templating (the geometry is simple; a heavy lib
  buys little). PNG conversion via `cairosvg` (accept the native dependency; fallback `resvg-py`).
- One `RenderStyle` dataclass (colors per room type, stroke widths, font sizes, scale px/m,
  mode flags) so all three modes are one renderer with different styles.
- y-flip happens here and only here (schema is y-up, SVG is y-down).
- Wall thickness is painted (offset the room polygon outward 0.05 m per side, exterior 0.3 m) —
  it's presentation, not model geometry (see 01).

```python
def render_plan(plan: FloorPlan, placements: list[Placement] | None,
                catalog: CatalogClient | None, style: RenderStyle) -> str:  # SVG text
def render_room(plan, room_id, placements, catalog, style) -> str
```

## Tasks

- [x] Empty-plan SVG: polygons, wall stroke, labels, area computation (`render2d/svg.py`;
      hand-rolled SVG strings, no `svgwrite` needed)
- [x] Doors (swing arcs as sampled polylines — avoids SVG arc sweep-flag pitfalls) and windows
- [x] Furnished mode: footprint rects with rotation, front-direction tick, name + cm dims labels
      (`render_plan(plan, placements=..., catalog=...)`)
- [x] Room-crop mode (`render2d/room_crop.py`): numbered footprints biggest-first, front
      ticks, door/window labels with wall names, camera marker; returns (svg, legend, camera)
- [ ] PNG export
- [ ] Golden-file tests (compare SVG output against checked-in fixtures; on mismatch write the
      new file next to the golden one for eyeballing)

## Open questions

- North arrow / real-world orientation for lighting hints in 07? Add `north_deg` to the schema
  (01) if room renders benefit from knowing window light direction. Decide during M4.
