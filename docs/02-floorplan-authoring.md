# 02 — Floor Plan Authoring

**Status:** phase 1 built (YAML + sugar + `plan validate` / `plan preview --watch`)
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

## Phase 2 — browser editor (M5)

Small FastAPI app serving a canvas editor: drag vertices, drag openings along edges, edit
properties in a sidebar. Reads/writes the same YAML/JSON file — the editor is a *view*, the file
stays the source of truth. Keep the JS dependency-light (vanilla or a single small lib); all
validation stays in Python via a `/validate` endpoint.

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
- [ ] Author one *real* apartment (the user's) as the canonical test plan
- [ ] (M5) FastAPI editor skeleton

## Open questions

- Does phase 2 editor also handle furniture placement adjustment? Leaning yes — same canvas,
  different layer (coordinates with 05/08). Decide at M5.
