"""The workspace: a library of layout *samples* and the furnish *projects* started from them.

One directory holds everything a user accumulates:

    <root>/samples/<id>.yaml     layout library — every saved layout lands here and becomes a
                                 sample for next time
    <root>/projects/<id>/        one furnish session per layout, so re-selecting a layout
                                 continues where you left off (docs/09 Project)

On first use the samples dir is seeded from the starter layouts bundled with the package, so
the launcher is never empty.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from furnisher.authoring import PlanLoadError, load_plan
from furnisher.authoring.serializer import save_plan
from furnisher.model import DoorSwing, FloorPlan, Opening, OpeningKind, Room, RoomType
from furnisher.project import Project
from furnisher.render2d import RenderStyle, render_plan

BUNDLED_SAMPLES = Path(__file__).parent / "samples"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "layout"


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.samples_dir = self.root / "samples"
        self.projects_dir = self.root / "projects"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._seed_starters()

    def _seed_starters(self) -> None:
        """Copy bundled starter layouts in the first time the samples dir is empty."""
        if any(self.samples_dir.glob("*.yaml")):
            return
        for src in sorted(BUNDLED_SAMPLES.glob("*.yaml")):
            shutil.copyfile(src, self.samples_dir / src.name)

    # --- samples (the layout library) ---
    def sample_path(self, sample_id: str) -> Path:
        return self.samples_dir / f"{sample_id}.yaml"

    def has_sample(self, sample_id: str) -> bool:
        return self.sample_path(sample_id).exists()

    def new_sample_id(self, name: str) -> str:
        """A unique, not-yet-written id for a brand-new layout (the editor writes it on save)."""
        base = _slugify(name)
        candidate, n = base, 2
        while self.sample_path(candidate).exists():
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    def create_room_sample(
        self, name: str, room_type: str = "living_room", width: float = 5.0, depth: float = 4.0
    ) -> str:
        """Write a minimal single-room layout (one door + one window) and return its id — the
        one-click 'start from scratch with a room' path."""
        try:
            rtype = RoomType(room_type)
        except ValueError:
            rtype = RoomType.living_room
        w = max(2.5, float(width))
        d = max(2.5, float(depth))
        rid = _slugify(rtype.value)
        sample_id = self.new_sample_id(name)
        room = Room(id=rid, type=rtype, polygon=[(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)])
        door = Opening(
            id="door", kind=OpeningKind.door, room=rid, edge=0,
            offset=round(max(0.0, w / 2 - 0.45), 2), width=0.9,
            swing=DoorSwing.inward_left, connects="exterior",
        )
        window = Opening(
            id="window", kind=OpeningKind.window, room=rid, edge=2,
            offset=round(max(0.0, w / 2 - 0.9), 2), width=min(1.8, w - 0.4), sill_height=0.85,
        )
        save_plan(FloorPlan(name=name, rooms=[room], openings=[door, window]),
                  self.sample_path(sample_id))
        return sample_id

    def list_samples(self) -> list[dict]:
        """Every saved layout, newest first, with a thumbnail and whether it has a session."""
        thumb_style = RenderStyle(scale=26, padding=0.2)
        out = []
        for path in self.samples_dir.glob("*.yaml"):
            sample_id = path.stem
            has_project = (self.projects_dir / sample_id / "project.json").exists()
            entry = {
                "id": sample_id,
                "name": sample_id,
                "rooms": 0,
                "area": 0.0,
                "has_project": has_project,
                "in_progress": has_project,  # a furnish session exists — offer "Continue"
                "items": self._placement_count(sample_id) if has_project else 0,
                "svg": "",
                "error": None,
                "mtime": path.stat().st_mtime,
            }
            try:
                plan = load_plan(path)
                entry["name"] = plan.name
                entry["rooms"] = len(plan.rooms)
                entry["area"] = round(plan.total_area(), 1)
                entry["svg"] = render_plan(plan, style=thumb_style)
            except (PlanLoadError, ValueError) as exc:
                entry["error"] = str(exc)
            out.append(entry)
        out.sort(key=lambda e: e["mtime"], reverse=True)
        return out

    # --- projects (furnish sessions) ---
    def project_dir(self, sample_id: str) -> Path:
        return self.projects_dir / sample_id

    def _placement_count(self, sample_id: str) -> int:
        f = self.project_dir(sample_id) / "placements.json"
        if not f.exists():
            return 0
        try:
            return len(json.loads(f.read_text(encoding="utf-8")).get("placements", []))
        except (ValueError, OSError):
            return 0

    def open_or_create_project(self, sample_id: str) -> Path:
        """The furnish project for a layout, created from the layout on first open."""
        if not self.has_sample(sample_id):
            raise FileNotFoundError(f"no layout named {sample_id!r}")
        proj = self.project_dir(sample_id)
        if not (proj / "project.json").exists():
            Project.create(proj, self.sample_path(sample_id))
        return proj

    def reset_project(self, sample_id: str) -> Path:
        """Throw away the furnish session and start it over from the layout (from scratch)."""
        if not self.has_sample(sample_id):
            raise FileNotFoundError(f"no layout named {sample_id!r}")
        shutil.rmtree(self.project_dir(sample_id), ignore_errors=True)
        return self.open_or_create_project(sample_id)
