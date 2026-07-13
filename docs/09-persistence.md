# 09 — Persistence

**Status:** not started
**Depends on:** 01 (schema)
**Code home:** `src/furnisher/project/`

## Purpose

A project = one apartment being furnished. Everything on disk, human-readable where possible, so
sessions resume trivially and agents can inspect state with `cat`.

## Layout

```
my-apartment/                    # a project is a directory
  project.json                   # manifest: name, created, style profile, budget, settings
  plan.yaml                      # floor plan (authoring format, 02)
  placements.json                # current furnishing state (01 furnishing layer)
  chat.jsonl                     # conversation log (append-only)
  inspiration/                   # user-provided images
  renders/
    plan.svg                     # always-current furnished plan
    rooms/{room-id}-{hash}.png   # generated room images (hash = placements+style+recipe, see 07)
  snapshots/
    2026-07-13T15-30-02/         # copy of project.json + placements.json per mutation
```

Global (not per-project): catalog cache at `~/.furnisher/` (03).

## Snapshots / undo

Cheap and dumb: after every mutation the orchestrator (08) copies the two small JSON files into a
timestamped snapshot dir. `/undo` = restore latest snapshot. Cap at ~100, prune oldest. Git-style
cleverness is explicitly out of scope — the files are tiny.

## API

```python
class Project:
    @classmethod
    def load(cls, path: Path) -> "Project": ...
    def save(self) -> None                    # atomic writes (tmp + rename)
    def snapshot(self) -> None
    def undo(self) -> bool
    # typed accessors: .plan, .placements, .style_profile, .chat_log
```

## Tasks

- [ ] `Project` class with atomic save, load-with-validation (clear errors on schema drift)
- [ ] Snapshot/undo + pruning
- [ ] `furnisher project new <dir>` scaffolding CLI
- [ ] Schema-version field + a "migrations" stub (just a version check that fails loudly for now)

## Open questions

- Multi-variant furnishing ("show me option A vs B")? The layout supports it later via multiple
  placement files; don't build until asked.
