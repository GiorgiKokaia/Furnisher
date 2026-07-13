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

**M0 done** — scaffold, floor plan schema (`furnisher.model`), YAML authoring with live SVG
preview, empty-plan renderer, CLI, tests. Try it:

```
uv sync
uv run furnisher plan preview tests/fixtures/two-bedroom.yaml --watch
```

Next: author the real apartment as a plan file, then Milestone M1 (catalog: provider protocol,
cache, `generic` + IKEA adapters) — see `docs/00-architecture.md`.
