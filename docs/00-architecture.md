# 00 — Architecture Overview

**Status:** planning
**Source:** `big_picture.txt`

## Goal

Let a user take a completely empty apartment and design its furnishing through chat, inspirational
images, and suggestions from a design agent. Outputs:

1. A **furnished 2D floor plan** — real catalog items placed at correct scale. Catalog is
   provider-agnostic (search + filters + images + dimensions); IKEA is only the first adapter.
   Items must be orderable to Georgia (republic).
2. **Per-room images** — generated with Nano Banana, grounded in the actual product photos so the
   render matches what the user would really buy.

Stretch goal: 2D→3D.

## Data flow

```
                       ┌─────────────────────┐
  user-authored plan → │  Floor plan schema   │ ←──(future: import IFC/etc.)
  (02 authoring)       │  (01, canonical)     │
                       └─────────┬───────────┘
                                 │
  inspiration images ┐           ▼
  chat messages      ├──→ ┌──────────────┐    search   ┌──────────────────┐
  (08 chat app)      ┘    │ Design agent │ ──────────→ │ Catalog (03)      │
                          │ (04, Gemini) │ ←────────── │ dims/images/price │
                          └──────┬───────┘   products  └──────────────────┘
                                 │ selected items + intent
                                 ▼
                          ┌──────────────┐
                          │ Layout engine │  places items, checks clearances
                          │ (05)          │
                          └──────┬───────┘
                     placements  │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
     ┌────────────────┐                   ┌─────────────────────┐
     │ 2D renderer (06)│                   │ Room image gen (07) │
     │ furnished plan  │ ──plan render──→  │ Nano Banana, grounded│
     └────────────────┘                   │ on product photos    │
                                          └─────────────────────┘

  Everything reads/writes a Project file (09 persistence). The chat app (08) orchestrates the loop.
```

## Components

- **01 Floor plan schema** — the canonical JSON data model everything else consumes. Rooms as
  polygons in meters, doors/windows as openings on edges, room types, ceiling heights.
- **02 Floor plan authoring** — how plans get created at first: hand-written YAML/JSON with a live
  SVG preview (phase 1), simple browser editor (phase 2), standard-format import later.
- **03 Furniture catalog** — provider-agnostic search + product detail (dimensions, images,
  price, URL) behind a `CatalogProvider` protocol with an aggressive shared cache. Adapters:
  `generic` (local pseudo-catalog, unblocks everything), `ikea` (baseline, timeboxed), more later
  based on what ships to Georgia.
- **04 Design agent** — Gemini-powered: extracts a style profile from inspiration images, chats
  with the user, proposes concrete catalog items per room.
- **05 Layout engine** — turns "these items in this room" into scale-correct placements; enforces
  clearances, door swings, window sills; validates manual moves.
- **06 2D renderer** — draws the furnished floor plan (SVG first) with item footprints and labels.
- **07 Room image generation** — Nano Banana (`gemini-2.5-flash-image`) renders each room, with the
  plan render + product photos passed as grounding inputs.
- **08 Chat app / orchestration** — the loop the user actually experiences; session state, applying
  agent proposals, triggering renders.
- **09 Persistence** — one project = one directory of JSON + assets; versioned snapshots so the
  user can iterate safely.
- **10 3D stretch** — parked notes so early decisions don't block it.
- **11 Dev setup** — Python 3.12+, uv, repo layout, `GEMINI_API_KEY` handling, pytest.

## Key decisions (made — revisit only with a reason)

- **Units are meters, floats**, origin bottom-left, x right / y up, room polygons CCW. Every
  component uses this; conversions happen only at render/UI edges.
- **The floor plan schema (01) is the single contract.** Agent, layout engine, and renderers never
  talk to each other's internals — they read/write the project file.
- **Python throughout**; any web UI is a thin layer (FastAPI + static JS) over the Python core.
- **LLM/image provider is behind a small interface** (`furnisher/llm/`). Prototype uses Gemini +
  Nano Banana; keep the surface small so swapping providers is cheap.
- **Catalog data is cached locally** the moment it's fetched — unofficial endpoints can break or
  rate-limit; renders and layouts must keep working offline from cache.
- Placements store the **catalog item's real bounding box (w × d × h)**; scale correctness is a
  hard invariant, never eyeballed.

## Milestones

- ~~**M0 — Skeleton + plans on screen.**~~ **Done** (plus the phase-2 GUI editor, pulled forward).
- ~~**M1 — Catalog.**~~ **Done.** *Exit verified live: BILLY 0.80×0.28×2.02 m from the real IKEA
  endpoints.*
- ~~**M2 — Manual furnishing.**~~ **Done.** *Exit: `examples/my-apartment.placements.json` — 14
  items at true scale in the real apartment, validates clean.* (Auto-placement + connectivity
  check deliberately deferred to M3.)
- ~~**M3 — The agent.**~~ **Done.** *Exit verified live: budget → "furnish the bedroom,
  scandinavian, cozy" → real items placed, 1492/1500 EUR tracked across two rooms.*
  (Inspiration-image style extraction is wired via `/inspire` but not yet exercised with
  real photos.)
- ~~**M4 — Room images.**~~ **Done.** *Exit verified live: bedroom render visibly contains the
  actual MALM bed, PAX wardrobe and MALM nightstand in planned positions; feedback re-roll
  keeps products while changing mood.*
- **M5 — Usable app.** Web UI: plan view + chat side by side, click-to-adjust placements (02
  phase 2, 08). 
- **Stretch — 3D** (10).

## Open questions (park here, answer when relevant)

- ~~Budget as a first-class constraint for the agent?~~ **Decided: yes.** Budget is a supported
  constraint end-to-end: `SearchFilters.price_max` (03), agent tracks spend across rooms (04),
  `/budget` command (08).
- Multi-floor apartments? (Schema should not preclude it; ignore until asked.)
- Which concrete furniture providers ship to Georgia (republic)? Research at M1 with the user.
