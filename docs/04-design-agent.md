# 04 — Design Agent

**Status:** not started
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

2. **Furnishing proposal (per room)** — inputs: room (type, dimensions, openings), style profile,
   conversation summary, budget remaining. The agent decides *what kinds* of items the room needs
   ("queen bed, 2 nightstands, wardrobe ≤ 60cm deep"), calls **catalog search as a tool**
   (function calling → `CatalogClient.search`), picks concrete items from real results, and
   returns `RoomProposal { items: [{item_id, purpose, placement_hint}], rationale }`.
   Placement hints are soft ("bed headboard against the wall without windows"); the layout engine
   (05) owns actual coordinates.

3. **Chat turn handler** — free-form conversation; classifies intent (adjust style / swap item /
   move item / question) and routes to re-running 1, 2, or emitting a layout-engine directive.
   Owned jointly with 08 — the orchestration loop lives there, prompt logic lives here.

## Grounding rules (put these in the system prompt)

- Never invent products: every proposed item must come from a tool-call result (verifiable
  because item ids must exist in the cache).
- Respect dimensions: the prompt includes room dims and the hard rule that item footprints must
  fit with ≥70cm walking clearance (05 re-validates; the agent just shouldn't waste proposals).
- Track budget across rooms if the user set one.

## Prompts as files

Keep prompts in `src/furnisher/agent/prompts/*.md`, loaded at runtime — reviewable in git,
editable without touching code.

## Tasks

- [ ] `furnisher/llm/` provider wrapper (Gemini impl; structured output + image inputs + tools)
- [ ] Style extraction call + `StyleProfile` model + persistence in project file
- [ ] Catalog search exposed as a Gemini function-calling tool
- [ ] Room proposal call with grounding rules; validate returned item ids against cache
- [ ] Chat-turn intent routing (with 08)
- [ ] Eval fixtures: 2–3 inspiration-image sets + expected style tags (loose asserts); one
      scripted "furnish my bedroom" conversation as an integration test (recorded/replayed)

## Open questions

- Conversation memory: full history vs. rolling summary — start with full history, summarize when
  it hurts (token cost) at M3.
- Should the agent be able to *edit the floor plan* (phase-3 authoring idea)? Not in v0.
