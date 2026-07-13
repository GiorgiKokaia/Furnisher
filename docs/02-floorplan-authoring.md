# 02 — Floor Plan Authoring

**Status:** phase 1 built (YAML + sugar + `plan validate` / `plan preview --watch`);
phase 2 built (`furnisher plan edit` browser editor)
**Depends on:** 01 (schema), 06 (renderer, for preview)
**Code home:** `src/furnisher/authoring/`

## Purpose

"We need some way of creating the floor-plans at first so we can manually adjust them." Room
shapes, sizes, types, doors, windows — authored by hand, previewed instantly, adjusted until right.

## Phase 1 — text + live preview (build this for M0)

Hand-author plans as **YAML** (friendlier than JSON for humans; converts 1:1 to the schema), with
a watcher that re-renders an SVG preview on every save:

```
furnisher plan preview my-apartment.yaml     # writes/updates my-apartment.svg, watches file
furnisher plan validate my-apartment.yaml    # schema + geometry checks, human-readable errors
```

YAML sugar worth adding (desugars to schema polygons — keep it minimal):

- `rect: [x, y, w, h]` as an alternative to `polygon:` for rectangular rooms (most rooms).
- Openings may give `offset_frac` instead of `offset`: the fraction of the edge at which the
  opening's *center* sits, so `offset_frac: 0.5` centers it on the edge.

Why text-first: fastest path to a real plan of the user's own apartment; diffs nicely in git; the
design agent can read and even propose plan edits with zero extra tooling.

## Phase 2 — browser editor (built early, was planned for M5)

`furnisher plan edit my-apartment.yaml [--port 8377]` — FastAPI app (`authoring/editor.py`)
serving a single-file vanilla-JS canvas editor (`authoring/editor.html`, no build step). The YAML
file stays the source of truth; the editor is a view. All validation/serialization stays in
Python.

What it does:
- Draw rooms by dragging; move rooms; reshape via corner handles. Grid cell size (5 cm – 1 m)
  and snap on/off are toolbar controls, persisted in localStorage; the canvas draws the chosen
  grid (meter lines darker). With snap off, coordinates are still rounded to 0.1 mm.
- Place doors/windows/passages by clicking a wall (tools D/W/P); drag them along their wall;
  edit width/offset/swing/sill/connects in the sidebar.
- Door/passage `connects` is auto-inferred from adjacency on save (`authoring/infer.py`) —
  leave it "(auto)".
- Validate button surfaces `validate_plan()` issues; Save writes canonical YAML via
  `authoring/serializer.py` (geometric warnings don't block saving — you're iterating).
- Preview button shows the server-rendered SVG (with door arcs; the canvas draws openings as
  simple colored bars).
- Zoom (wheel), pan (drag empty space / space+drag), fit (F), delete (Del), Ctrl+S to save.

Serializer detail worth knowing: `rect` sugar is only re-emitted when a polygon is exactly the
canonical loader-produced rectangle — anything else stays a `polygon`, because rect desugaring
renumbers edges and would silently break the openings referencing them.

## Phase 3 — import (future, don't build)

Slot exists in `furnisher/model/importers/` (see 01). Most likely first import: photo/scan of a
plan → rooms, via an ML model or the design agent itself with vision. Park it.

## Implementation notes

- File watching: `watchfiles` package.
- The preview should render room names, types, dimensions (auto-label each room with its size in
  m²), and door swings — that's what you need to eyeball correctness against reality.
- Validation errors must name the offending id and say what to fix (agents will act on them).

## Tasks

- [x] YAML ↔ schema loader with the `rect` / `offset_frac` sugar (`authoring/loader.py`)
- [x] `furnisher plan validate` CLI (typer)
- [x] `furnisher plan preview` with `watchfiles` live re-render (`--watch`)
- [x] Author one *real* apartment (the user's) as the canonical test plan
      (`my-apartment.yaml`, drawn in the GUI editor)
- [x] FastAPI editor (`plan edit`): canvas drawing, opening placement, sidebar props,
      auto-`connects`, save/validate/preview — verified end-to-end with Playwright
- [x] Editor niceties: Ctrl+Z undo stack, arrow-key nudge, grid-size + snap toggle,
      overlap rejection on placement
- [ ] Editor niceties still open: vertex add/remove for non-rect rooms

## Open questions

- ~~Does phase 2 editor also handle furniture placement adjustment?~~ **Answered:**
  placement adjustment lives in the *web app* (08: drag with wall snap, nudge/rotate/
  delete toolbar), not in the plan editor — the plan editor stays about architecture.
