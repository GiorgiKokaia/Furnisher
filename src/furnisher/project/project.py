"""Project persistence (docs/09): one apartment being furnished = one directory.

Everything on disk, human-readable, so sessions resume trivially and agents can inspect
state with `cat`. Snapshots are dumb copies of the two small JSON files; undo restores the
latest one. Git-style cleverness is explicitly out of scope.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from furnisher.authoring import load_plan
from furnisher.model import FloorPlan, Placement

SNAPSHOT_CAP = 100


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Project:
    def __init__(self, path: Path, plan: FloorPlan, placements: list[Placement], meta: dict):
        self.path = path
        self.plan = plan
        self.placements = placements
        self.meta = meta  # name, created, budget, currency, style_profile (plain dicts)

    # --- lifecycle ---
    @classmethod
    def create(cls, path: Path, plan_source: Path, name: str | None = None) -> "Project":
        if (path / "project.json").exists():
            raise FileExistsError(f"{path} already contains a project")
        plan = load_plan(plan_source)  # validate before committing to disk
        path.mkdir(parents=True, exist_ok=True)
        (path / "renders").mkdir(exist_ok=True)
        (path / "inspiration").mkdir(exist_ok=True)
        shutil.copyfile(plan_source, path / "plan.yaml")
        meta = {
            "name": name or plan.name,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "budget": None,
            "currency": "EUR",
            "style_profile": None,
        }
        project = cls(path, plan, [], meta)
        project.save()
        return project

    @classmethod
    def load(cls, path: Path) -> "Project":
        meta = json.loads((path / "project.json").read_text(encoding="utf-8"))
        plan = load_plan(path / "plan.yaml")
        placements_file = path / "placements.json"
        placements = []
        if placements_file.exists():
            data = json.loads(placements_file.read_text(encoding="utf-8"))
            placements = [Placement.model_validate(p) for p in data.get("placements", [])]
        return cls(path, plan, placements, meta)

    def save(self) -> None:
        _write_atomic(self.path / "project.json", json.dumps(self.meta, indent=2))
        _write_atomic(
            self.path / "placements.json",
            json.dumps(
                {"placements": [p.model_dump(mode="json") for p in self.placements]}, indent=2
            ),
        )

    # --- snapshots / undo ---
    def snapshot(self) -> None:
        stamp = (
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
            + f"-{time.time_ns() % 1000:03d}"
        )
        target = self.path / "snapshots" / stamp
        target.mkdir(parents=True, exist_ok=True)
        for name in ("project.json", "placements.json"):
            source = self.path / name
            if source.exists():
                shutil.copyfile(source, target / name)
        snapshots = sorted((self.path / "snapshots").iterdir())
        for old in snapshots[:-SNAPSHOT_CAP]:
            shutil.rmtree(old, ignore_errors=True)

    def undo(self) -> bool:
        snapshots = (
            sorted((self.path / "snapshots").iterdir())
            if (self.path / "snapshots").is_dir()
            else []
        )
        if not snapshots:
            return False
        latest = snapshots[-1]
        for name in ("project.json", "placements.json"):
            source = latest / name
            if source.exists():
                shutil.copyfile(source, self.path / name)
        shutil.rmtree(latest, ignore_errors=True)
        restored = Project.load(self.path)
        self.plan, self.placements, self.meta = restored.plan, restored.placements, restored.meta
        return True

    # --- chat log ---
    def append_chat(self, role: str, text: str) -> None:
        entry = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "role": role,
            "text": text,
        }
        with (self.path / "chat.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def chat_history(self, limit: int = 50) -> list[dict]:
        log_file = self.path / "chat.jsonl"
        if not log_file.exists():
            return []
        lines = log_file.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    # --- budget ---
    def spent(self, catalog) -> float:
        total = 0.0
        for p in self.placements:
            try:
                total += catalog.get(p.item_ref).price
            except KeyError:
                pass
        return total
