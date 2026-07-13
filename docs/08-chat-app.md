# 08 — Chat App / Orchestration

**Status:** stage 1 + stage 2 built — `furnisher chat` REPL and `furnisher app` web UI
(`app/webapp.py` + `app/app.html`): furnished plan + chat side by side, room-photo gallery,
per-room camera buttons, undo, budget header. Drag-to-adjust placements still pending.
**Depends on:** all of 01–07 (this is the integration layer)
**Code home:** `src/furnisher/app/`

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
   ├─ move/swap     → mutate placements → validate (05) → apply or report issues
   ├─ render        → 06 / 07
   └─ question      → answer from project state
after every mutation: snapshot (09), re-render plan SVG
```

Failures surface *into the chat* ("the KLIPPAN sofa doesn't fit next to the door — 45 cm short;
want a smaller one?") — `LayoutIssue` messages are written for exactly this.

## Tasks

- [ ] Orchestrator class: owns Project, wires 03–07, exposes `handle_message()`, `handle_command()`
- [ ] CLI REPL (stage 1) with the commands above
- [ ] Staleness tracking (which room images are outdated after which mutations)
- [ ] Scripted end-to-end test: fixture plan + canned agent responses → furnished project
- [ ] (M5) FastAPI app + page

## Open questions

- Streaming agent responses in the CLI? Nice, not necessary. Skip until stage 2.
