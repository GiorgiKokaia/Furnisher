# 05 — Layout Engine

**Status:** not started
**Depends on:** 01 (geometry), 03 (item dimensions)
**Code home:** `src/furnisher/layout/`

## Purpose

Turn "these items belong in this room (with soft hints)" into concrete, scale-correct
`Placement`s — and validate any placement, whether it came from the solver, the agent, or a human
dragging things around. **Validation is the core; auto-placement is heuristics on top.**

## Two entry points

```python
def validate(plan: FloorPlan, placements: list[Placement],
             catalog: CatalogClient) -> list[LayoutIssue]:
    """Cheap, pure, geometric. Called constantly (after every edit)."""

def auto_place(plan: FloorPlan, room_id: str, items: list[PlacementRequest],
               catalog: CatalogClient) -> list[Placement]:
    """Best-effort solver. PlacementRequest = item + soft hints from the agent (04)."""
```

`LayoutIssue` carries severity (`error` = physically impossible, `warning` = bad practice), the
placement ids involved, and a human/agent-readable message.

## Validation rules v0 (geometric, via shapely)

- **error** — footprint (rotated w×d rect) not fully inside the room polygon
- **error** — footprints overlap
- **error** — placement blocks a door opening or its swing arc
- **warning** — obstructs a window below its sill? (only if item height > sill height)
- **warning** — main walking clearance < 0.7 m (room must stay connected: free-space check —
  erode the free area by 0.35 m and require doors to remain reachable from each other)
- **warning** — item-specific clearances (bed sides ≥ 0.6 m, wardrobe/drawer front ≥ 0.9 m,
  sofa-to-coffee-table 0.3–0.5 m). Keep these in a small data table
  (`layout/clearances.py`), keyed by item `type_name` keywords — crude but effective.

## Auto-placement v0 (don't over-engineer)

Greedy + local search, largest item first:

1. Order items by footprint area, descending.
2. Candidate poses: against walls (aligned to the nearest edge, small offset grid along it),
   rotations from {0, 90, 180, 270} + wall-parallel; respect hints ("against wall w/o windows"
   filters candidates).
3. Score each valid candidate: hint satisfaction, wall contact for wall-loving items (beds,
   sofas, wardrobes), remaining free-space connectivity, distance rules from the clearance table.
4. Place best; continue. If an item can't be placed, return partial result + `LayoutIssue`s
   explaining why (the agent can then propose a smaller item — this feedback loop is the point).

Deterministic given a seed. If greedy proves too weak, next step is simulated annealing over the
same scorer — *not* an ML model, not an ILP, until proven necessary.

## Tasks

- [ ] Footprint/pose math (`Placement` → shapely polygon), door-swing arcs
- [ ] `validate()` with the v0 rule set + `LayoutIssue`
- [ ] Clearance data table
- [ ] `auto_place()` greedy v0
- [ ] Property-ish tests on fixture plans: solver output always passes `validate()`; overlapping /
      out-of-room / door-blocking fixtures each produce their specific issue
- [ ] Connectivity (erosion) check — trickiest bit, test it well

## Open questions

- Rugs/wall items (mirrors, shelves) don't obey footprint rules — add a `mount: floor|wall|ceiling`
  layer concept when first needed (likely M3).
- Fixed room fixtures (radiators, kitchen units) — blocked on 01's `fixtures` addition (v0.2).
