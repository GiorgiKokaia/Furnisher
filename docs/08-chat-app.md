# 08 — Chat App / Orchestration

**Status:** stage 1 + stage 2 built, plus a unified launcher (`furnisher start`) that ties the
layout editor and the furnish app together behind one URL. `furnisher chat` REPL and
`furnisher app` web UI (`app/webapp.py` + `app/app.html`): furnished plan + chat side by side,
room-photo gallery, per-room camera buttons, undo, budget header. Web app v2 additions:
- **Streaming**: `/api/message` returns NDJSON — `{"progress": ...}` lines (intent routing,
  each catalog search, placement) update the pending bubble live, last line carries the result.
- **Options**: furnishing is two-step — the agent proposes 2-3 labeled options (RoomOptions),
  rendered as chat cards with product photos (`referrerPolicy=no-referrer`, IKEA's CDN rejects
  foreign Referers) and a choose button (`/api/choose`; typing the number works too, also CLI).
  Nothing is placed until the user picks.
- **Drag**: pieces drag with live ghost; on drop `/api/placement` applies the world-space
  delta, snaps flush to the nearest wall within 0.3 m (`snap_to_wall`), validates, and
  rejects illegal drops back to their old spot. Click still selects (floating toolbar:
  nudge/rotate/delete).
- **🏠 apartment view**: whole-apartment isometric cutaway via Nano Banana grounded on the
  furnished plan (`/api/apartment-image`, cached by content hash).
- **✨ inspiration photos are shown**: `/api/inspire-ikea` downloads the IKEA lifestyle shots
  into `inspiration/` (served via a static mount) and returns their URLs; the app renders them
  as a clickable thumbnail row in chat (click to enlarge) — you see what the style was pulled
  from, not just a text summary.
- **Piece popup shows the product**: `state()` placements now carry `image`/`url`/`price`/`dims`;
  selecting a placed piece renders its product photo in the floating toolbar (click to enlarge),
  so you can see *what* you're nudging, not just its id.
**Depends on:** all of 01–07 (this is the integration layer)
**Code home:** `src/furnisher/app/`, `src/furnisher/hub/` (launcher)

## Single entry point — the launcher (`furnisher start`)

One command, one URL (`src/furnisher/hub/`). The home page (`hub/home.html`) lists the user's
**layout library** with thumbnails and offers *New layout*; picking one either opens the editor
or jumps straight into furnish mode. This is the front door the user actually starts from.

- **Workspace** (`hub/workspace.py`): a directory with `samples/<id>.yaml` (the layout library —
  every saved layout lands here and becomes a future sample) and `projects/<id>/` (one furnish
  session per layout, so re-selecting continues where you left off). Seeded on first run from
  starter layouts bundled in `hub/samples/`. Default root `./workspace/` (gitignored).
- **Hub server** (`hub/hub.py`): serves the home page and `/hub/*` actions, and **mounts the
  editor and furnish apps** under `/editor` and `/furnish`. It doesn't duplicate them — it swaps
  which layout/project they point at via `EditorTarget` (authoring) and `FurnishSession` (app),
  both of which are swappable holders the two apps read on every request.
  - `POST /hub/new` reserves a unique id + opens the editor on a blank, named layout.
  - `GET /hub/edit/{id}` points the editor at an existing layout, redirects to `/editor/`.
  - `GET /hub/furnish/{id}` create-or-continues the layout's project, opens the session,
    redirects to `/furnish/`. The editor's "Furnish →" button saves then hits this.
- **Relative URLs**: `app.html`/`editor.html` fetch `api/…` (not `/api/…`) and images resolve
  relative to the page, so both apps work identically standalone (`furnisher app`, at `/`) and
  mounted under the hub (at `/furnish/`). Renders/inspiration are served from the *current*
  project via explicit routes, not a fixed static mount (so switching projects just works).

Standalone commands still exist (`furnisher app <project>`, `furnisher plan edit <file>`) — the
hub is a convenience layer over the same factories, not a replacement.

## Purpose

The loop the user actually experiences: load a project, chat, add inspiration images, watch the
plan fill up, request room renders, adjust, export. Owns session state and the order in which
components run; contains **no** domain logic of its own (that lives in 04/05/06/07).

## Two stages

### Stage 1 — CLI chat (M3, keep it ugly)

`furnisher chat my-project/` — a REPL: user types, agent responds; commands prefixed with `/`:

```
/inspire path/to/image.jpg     add inspiration image, re-extract style
/plan                          re-render and write furnished plan SVG, print path
/room living-room              generate room image (07), print path
/undo                          restore previous project snapshot (09)
/budget 3000
```

The value of stage 1: it forces the orchestration API to exist independent of any UI.

### Stage 2 — web app (M5)

FastAPI + one page: furnished plan (SVG, live-updating) on the left, chat on the right, room
image gallery below. Plan clicks select placements; drag to move (validated live via 05's
`validate`, issues shown inline). Reuses the exact orchestration layer from stage 1 — if stage 2
needs new core logic, that logic was in the wrong place.

## Orchestration flow per chat turn

```
user msg ──→ agent intent routing (04)
   ├─ style change  → re-extract style → mark room images stale
   ├─ furnish room  → agent proposal (04) → auto_place (05) → validate → apply to project (09)
   ├─ replace item  → match placed item → propose_replacement (04) → keep spot or auto_place →
   │                  validate (05) → swap in project (09)
   ├─ move (UI)     → drag/nudge/rotate → validate (05) → apply or reject (web app toolbar)
   ├─ render        → 06 / 07
   └─ question      → answer from project state
after every mutation: snapshot (09), re-render plan SVG
```

Failures surface *into the chat* ("the KLIPPAN sofa doesn't fit next to the door — 45 cm short;
want a smaller one?") — `LayoutIssue` messages are written for exactly this.

## Tasks

- [x] Orchestrator class: owns Project, wires 03–07, `handle_message()` (structured result:
      reply / options / placed), progress callback, pending-options state
- [x] CLI REPL (stage 1): /inspire /inspire-ikea /budget /plan /items /room /undo; numbered
      option picking
- [x] Scripted end-to-end tests: fixture plan + FakeLLM → options → choose → furnished project
- [x] (M5) FastAPI app + page (v2: streaming, option cards, drag+snap, apartment view)
- [x] Unified launcher (`furnisher start`, `hub/`): workspace of layout samples + per-layout
      furnish projects, home page with thumbnails, editor/furnish mounted under one server
      with swappable target/session; new layouts auto-become samples
- [x] Replace a placed item from chat ("replace the sofa with a cheaper one") or the piece
      popup's ⇄ button — `replace_item` intent → grounded `propose_replacement` → swap
- [ ] Staleness tracking: room-image caching self-invalidates via content hash, but outdated
      images linger in the gallery — mark or prune them

## Open questions

- Streaming agent responses in the CLI? Nice, not necessary. Skip until stage 2.
