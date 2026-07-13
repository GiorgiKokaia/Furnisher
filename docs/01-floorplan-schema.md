# 01 — Floor Plan Schema

**Status:** v0 implemented (`src/furnisher/model/`)
**Depends on:** nothing (everything else depends on this)
**Code home:** `src/furnisher/model/`

## Purpose

The canonical data model for apartments. One JSON-serializable schema that the authoring tool,
design agent, layout engine, and both renderers all consume. Get this right early; changing it
later touches everything.

## Conventions (fixed)

- Units: **meters**, floats. Angles in degrees, CCW positive.
- Coordinates: origin bottom-left, **x right, y up** (math convention; flip y only when rendering
  to screen/SVG).
- Room polygons: simple (non-self-intersecting), CCW winding.
- IDs: short human-readable slugs (`"bedroom-1"`, `"door-hall-bath"`), unique per plan.

## Schema v0

Implement as **Pydantic models** (validation for free, JSON round-trip, JSON Schema export for the
future import format).

```jsonc
{
  "schema_version": "0.1",
  "name": "My apartment",
  "ceiling_height": 2.6,              // default; rooms may override
  "rooms": [
    {
      "id": "living-room",
      "type": "living_room",          // enum, see below
      "polygon": [[0,0],[5.2,0],[5.2,4.1],[0,4.1]],
      "ceiling_height": null          // optional override
    }
  ],
  "openings": [
    {
      "id": "door-hall-living",
      "kind": "door",                 // door | window | opening (doorless passage)
      "room": "living-room",          // room whose edge it sits on
      "edge": 0,                      // index into polygon edges (v[i] -> v[i+1])
      "offset": 1.2,                  // meters from edge start to opening start
      "width": 0.9,
      "height": 2.0,
      // doors only:
      "swing": "inward_left",         // inward_left|inward_right|outward_left|outward_right|sliding|none
      "connects": "hallway",          // other room id, or "exterior"
      // windows only:
      "sill_height": 0.85
    }
  ]
}
```

Walls are **implicit**: shared/exterior edges of room polygons. A fixed wall thickness
(default 0.1 m interior / 0.3 m exterior) is a *render-time* concern, not stored geometry. Revisit
if this bites (it might for exact area calculations — note it in code when implementing).

### Room types (enum v0)

`living_room, bedroom, kitchen, bathroom, wc, hallway, dining_room, office, balcony, storage, other`

### Furnishing layer (same file family, separate object)

Placements live in the **project file** (see 09), not the plan — a plan can have many furnishing
variants:

```jsonc
{
  "placements": [
    {
      "id": "p1",
      "item_ref": "ikea:00263850",    // catalog item id (03)
      "room": "living-room",
      "position": [1.4, 2.0],         // footprint center, meters
      "rotation": 90.0,               // CCW degrees; 0 = item width along +x
      "note": "sofa against north wall"
    }
  ]
}
```

Item dimensions are **not** duplicated here — they come from the cached catalog record via
`item_ref`. Scale correctness = footprint `(width, depth)` from the catalog + this pose.

## API surface to provide

- `FloorPlan.model_validate_json(...)` / `.model_dump_json()` (Pydantic built-ins)
- Geometry helpers (thin wrappers over `shapely`): `room.area()`, `room.shapely_polygon()`,
  `opening.segment() -> ((x1,y1),(x2,y2))`, `plan.room_at(point)`, `plan.validate()` (polygons
  simple + CCW, openings fit on their edge, `connects` rooms actually adjacent).

## Future import (design for, don't build)

Keep a `furnisher/model/importers/` slot. Candidates when needed: IFC (via `ifcopenshell`),
CubiCasa/rasterized-plan ML models, SweetHome3D XML. The JSON Schema export from Pydantic is our
own "standard format" in the meantime.

## Tasks

- [x] Pydantic models for `FloorPlan`, `Room`, `Opening`, `Placement` + enums (`model/plan.py`)
- [x] `plan.validate_plan()` with the checks listed above; good error messages
- [x] Geometry helpers (`model/geometry.py`; shapely used for simplicity/adjacency checks)
- [x] Two fixture plans in `tests/fixtures/` (`studio.yaml`, `two-bedroom.yaml`)
- [x] Unit tests: round-trip, validation failures, edge/offset math

## Open questions

- Angled/curved walls: polygons already allow angles; curves are out of scope for v0.
- Fixed built-ins (kitchen counters, radiators, toilets)? Probably a `fixtures` list on Room in
  v0.2 — the layout engine will need them to avoid placing furniture on top. Add when M2 starts.
