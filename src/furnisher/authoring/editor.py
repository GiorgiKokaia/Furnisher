"""Browser-based plan editor (docs/02 phase 2): FastAPI backend for editor.html.

The YAML file stays the source of truth; the editor is a view. Saving writes canonical YAML
via the serializer (geometric issues are reported but don't block saving — you're iterating).

Like the furnish app, the editor reads its current target (which YAML to edit, and the sample
id when driven by the hub) from a swappable `EditorTarget`, so the hub can point it at any
layout in the workspace. `create_app(plan_path)` keeps `furnisher plan edit <file>` working.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import ValidationError

from furnisher.authoring.infer import infer_connects
from furnisher.authoring.loader import PlanLoadError, load_plan
from furnisher.authoring.serializer import save_plan
from furnisher.model import FloorPlan
from furnisher.render2d import render_plan

EDITOR_HTML = Path(__file__).parent / "editor.html"


class EditorTarget:
    """Which layout the editor is currently editing. `sample_id` is set only when the hub
    drives the editor (enables the in-editor 'Furnish this' / 'Layouts' navigation)."""

    def __init__(
        self, path: Path | None = None, sample_id: str | None = None, name: str | None = None
    ):
        self.path = Path(path) if path else None
        self.sample_id = sample_id
        self.name = name  # display name for a brand-new (not-yet-saved) layout

    def set(self, path: Path, sample_id: str | None, name: str | None = None) -> None:
        self.path = Path(path)
        self.sample_id = sample_id
        self.name = name


def _schema_errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()]


def create_app(plan_path: Path) -> FastAPI:
    """Standalone editor for one YAML file (`furnisher plan edit <file>`)."""
    return create_editor_app(EditorTarget(plan_path, None))


def create_editor_app(target: EditorTarget) -> FastAPI:
    app = FastAPI(title="Furnisher plan editor")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return EDITOR_HTML.read_text(encoding="utf-8")

    @app.get("/api/plan")
    def get_plan():
        plan_path = target.path
        if plan_path is None:
            return JSONResponse({"error": "no layout selected"}, status_code=400)
        if plan_path.exists():
            try:
                plan = load_plan(plan_path)
            except (PlanLoadError, ValueError) as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
        else:
            plan = FloorPlan(name=target.name or plan_path.stem, rooms=[])
        return {
            "path": str(plan_path),
            "sample_id": target.sample_id,
            "plan": plan.model_dump(mode="json"),
        }

    @app.post("/api/validate")
    def validate(body: dict):
        try:
            plan = infer_connects(FloorPlan.model_validate(body))
        except ValidationError as exc:
            return {"ok": False, "issues": _schema_errors(exc)}
        return {"ok": True, "issues": plan.validate_plan(), "plan": plan.model_dump(mode="json")}

    @app.post("/api/plan")
    def save(body: dict):
        if target.path is None:
            return {"ok": False, "saved": False, "issues": ["no layout selected"]}
        try:
            plan = infer_connects(FloorPlan.model_validate(body))
        except ValidationError as exc:
            return {"ok": False, "saved": False, "issues": _schema_errors(exc)}
        save_plan(plan, target.path)
        return {
            "ok": True,
            "saved": True,
            "sample_id": target.sample_id,
            "issues": plan.validate_plan(),
            "plan": plan.model_dump(mode="json"),
        }

    @app.post("/api/render", response_class=PlainTextResponse)
    def render(body: dict):
        try:
            plan = FloorPlan.model_validate(body)
        except ValidationError as exc:
            return PlainTextResponse("\n".join(_schema_errors(exc)), status_code=422)
        return render_plan(plan)

    return app
