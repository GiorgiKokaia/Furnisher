# Furnisher

A tool that helps furnish bare-bones apartments. Given an empty apartment layout, a mix of
inspirational images, agent suggestions, and chat, the user designs their apartment. Output is a
furnished floor plan (items placed at correct scale, sourced from real furniture catalogs —
provider-agnostic, IKEA as the first baseline adapter) plus generated per-room images grounded in
real product photos. Items must be orderable to Georgia (republic).

Language: **Python**. Image/LLM backend for the prototype: **Gemini + Nano Banana** (personal API key).

## Where to start

Read `docs/00-architecture.md` first — it holds the component map, data flow, key decisions, and
the milestone plan. Each component then has its own doc with responsibilities, interfaces, and a
task checklist so work can be resumed (by a human or an agent) without extra context.

## Component index

| Doc | Component | One-liner |
|---|---|---|
| [docs/00-architecture.md](docs/00-architecture.md) | Architecture | Big picture, data flow, decisions, milestones |
| [docs/01-floorplan-schema.md](docs/01-floorplan-schema.md) | Floor plan schema | Canonical data model: rooms, walls, doors, windows, units |
| [docs/02-floorplan-authoring.md](docs/02-floorplan-authoring.md) | Floor plan authoring | Creating/editing plans manually; future import formats |
| [docs/03-catalog.md](docs/03-catalog.md) | Furniture catalog | Provider-agnostic search/filters/images/dims; IKEA first adapter |
| [docs/04-design-agent.md](docs/04-design-agent.md) | Design agent | Chat-driven style extraction + furniture selection (Gemini) |
| [docs/05-layout-engine.md](docs/05-layout-engine.md) | Layout engine | Scale-correct placement, clearances, validation |
| [docs/06-floorplan-renderer.md](docs/06-floorplan-renderer.md) | 2D renderer | Furnished floor plan output (SVG/PNG) |
| [docs/07-room-image-generation.md](docs/07-room-image-generation.md) | Room image generation | Nano Banana renders grounded on product photos |
| [docs/08-chat-app.md](docs/08-chat-app.md) | Chat app / orchestration | The user-facing loop tying everything together |
| [docs/09-persistence.md](docs/09-persistence.md) | Persistence | Project files, sessions, versioning |
| [docs/10-3d-stretch.md](docs/10-3d-stretch.md) | 2D→3D (stretch) | Notes for the future 3D goal |
| [docs/11-dev-setup.md](docs/11-dev-setup.md) | Dev setup | Python env, repo layout, config/secrets, testing |

## Status

**M0–M5 done** — schema, GUI plan editor, provider-agnostic catalog (generic + live IKEA
adapters), layout validation + auto-placement, furnished rendering, chat design agent. Try it:

```
uv sync
uv run furnisher plan edit my-apartment.yaml              # browser GUI layout editor
uv run furnisher catalog search "sofa" --max-price 400    # search real furniture (cached)
uv run furnisher furnish validate my-apartment.yaml examples/my-apartment.placements.json
uv run furnisher furnish render   my-apartment.yaml examples/my-apartment.placements.json
```

The design agent and the web app are the main event:

```
uv run furnisher project new my-place --plan my-apartment.yaml
uv run furnisher app my-place                 # plan + chat side by side (start here)
uv run furnisher chat my-place                # same brain, terminal REPL
uv run furnisher render room my-place Sleep   # grounded photoreal room image (Nano Banana)
```

In the app: set a budget, pull IKEA inspiration photos (✨), ask for a room — the agent
streams its progress, proposes 2-3 options as cards with product photos, and places the
one you pick. Drag pieces to adjust (they snap to walls, every move is validated), use
the 📷 buttons for photoreal room images and 🏠 for a whole-apartment cutaway view.

Remaining: layout-quality iteration (the greedy solver is legal but not always elegant),
more catalog providers (Georgia-reachable), free-space connectivity check, 2D->3D stretch
(docs/10).
