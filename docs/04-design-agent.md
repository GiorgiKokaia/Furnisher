# 04 — Design Agent

**Status:** built + extended (`src/furnisher/agent/`, `src/furnisher/llm/`) — style
extraction (from files and IKEA inspiration photos), intent routing, and **two-step
furnishing**: `propose_options()` returns 2-3 labeled `RoomOptions` (grounding-filtered);
nothing is placed until the user picks. Reports progress via an `on_progress` callback
(each catalog search, option shaping) for streaming UIs. Verified live.
Gotcha recorded in agent.py: no `from __future__ import annotations` in files defining
google-genai tool functions (stringified annotations break automatic function calling).
**Depends on:** 01 (reads plans), 03 (searches catalog), 05 (hands off placement)
**Code home:** `src/furnisher/agent/`

## Purpose

The "specialized design agent": takes the floor plan, inspiration images, and the chat
conversation, and produces (a) a **style profile**, (b) concrete **item proposals** per room from
the catalog, (c) plain-language suggestions/rationale for the user.

## Model & SDK

- SDK: `google-genai` (`pip install google-genai`), key from `GEMINI_API_KEY` (see 11).
- Chat/reasoning model: `gemini-2.5-flash` to start (cheap, multimodal); escalate to `-pro` only
  if quality demands it.
- Wrap the provider in `furnisher/llm/` (a ~3-method interface: `complete`, `complete_structured`,
  `generate_image`) so 07 shares it and swapping providers later is cheap.

## Pipeline (three separable calls, not one mega-prompt)

1. **Style extraction** — inputs: inspiration images + any user notes. Output (structured, JSON
   schema enforced via the SDK's `response_schema`): `StyleProfile { palette: [colors], materials:
   [wood, metal, ...], style_tags: [scandinavian, ...], avoid: [...], budget_total?, notes }`.
   Runs once up front, re-runs when the user adds images; stored in the project file.

2. **Furnishing options (per room)** — inputs: room (type, dimensions, openings), style profile,
   budget remaining. The agent decides *what kinds* of items the room needs, calls **catalog
   search as a tool** (function calling → `Catalog.search`), picks concrete items from real
   results, and returns 2-3 `RoomOption { label, items: [{item_id, purpose, hint, anchor}],
   rationale }` sets for the user to choose between. Hints are coarse (`wall`/`center`/`free` +
   an optional anchor purpose); the layout engine (05) owns actual coordinates.

3. **Chat turn handler** — free-form conversation; classifies intent into a small closed set
   (`furnish_room`, `set_budget`, `clear_room`, `replace_item`, `question` — `agent/models.py`
   `Intent`, prompt `prompts/route.md`) and routes accordingly. `replace_item` carries a
   free-text `target` (which placed item) + `note` (the requirement, e.g. "cheaper"); the
   orchestrator matches the target against current placements and calls `propose_replacement`
   (one grounded catalog item of the same function), then swaps it in — keeping the exact spot
   if it still validates, otherwise re-placing that single item via `auto_place`.
   Owned jointly with 08 — the orchestration loop lives there, prompt logic lives here.

## Grounding rules (put these in the system prompt)

- Never invent products: every proposed item must come from a tool-call result (verifiable
  because item ids must exist in the cache).
- Respect dimensions: the prompt includes room dims and the hard rule that item footprints must
  fit with ≥70cm walking clearance (05 re-validates; the agent just shouldn't waste proposals).
- Track budget across rooms if the user set one.

## IKEA inspiration photos

IKEA's /rooms/ idea gallery is a JS app with no query API, but every product search hit
carries `contextualImageUrl` — a professionally styled room photo. `IkeaProvider
.inspiration_images(query)` collects those; `Orchestrator.inspire_from_ikea(query)` downloads
them into the project's `inspiration/` dir and re-extracts the style profile. Exposed as
`/inspire-ikea <query>` in chat and the ✨ button in the web app. (Verified live:
"gemütliches schlafzimmer holz" → 4 photos → Scandinavian/Cozy profile.)

## Prompts as files

Keep prompts in `src/furnisher/agent/prompts/*.md`, loaded at runtime — reviewable in git,
editable without touching code.

## Tasks

- [x] `furnisher/llm/` provider wrapper (Gemini: text / structured / auto function-calling /
      image gen; retries on MALFORMED_FUNCTION_CALL)
- [x] Style extraction call + `StyleProfile` model + persistence in project file
- [x] Catalog search exposed as a Gemini function-calling tool (with progress reporting)
- [x] Room options call with grounding rules; returned item ids validated against the catalog
- [x] Chat-turn intent routing (with 08); digit shortcut picks a pending option
- [x] Scripted "furnish the bedroom" conversations as integration tests (FakeLLM in
      tests/test_orchestrator.py + test_webapp.py)
- [ ] Eval fixtures for style extraction: inspiration-image sets + expected style tags

## Open questions

- Conversation memory: full history vs. rolling summary — start with full history, summarize when
  it hurts (token cost) at M3.
- Should the agent be able to *edit the floor plan* (phase-3 authoring idea)? Not in v0.
