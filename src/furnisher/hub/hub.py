"""The launcher (docs/08 unified entry): one server, one URL.

`/`                home page — pick a layout or create a new one
`/editor/…`        the plan editor (mounted), pointed at the chosen/new layout
`/furnish/…`       the furnish app (mounted), pointed at the chosen layout's project
`/hub/new`         reserve a new layout id and open the editor on it
`/hub/edit/{id}`   open the editor on an existing layout
`/hub/furnish/{id}` create-or-continue the layout's furnish session, then jump into it

The editor and furnish apps are the same ones used standalone; the hub just swaps which
layout/project they point at (via `EditorTarget` / `FurnishSession`) and mounts them here.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from furnisher.app.webapp import FurnishSession, create_furnish_app
from furnisher.authoring.editor import EditorTarget, create_editor_app
from furnisher.hub.workspace import Workspace

HOME_HTML = Path(__file__).parent / "home.html"


def create_hub(workspace: Workspace, llm, catalog=None) -> FastAPI:
    if catalog is None:
        from furnisher.catalog import default_catalog

        catalog = default_catalog()

    session = FurnishSession(catalog, llm)
    editor_target = EditorTarget()
    hub = FastAPI(title="Furnisher")

    @hub.get("/", response_class=HTMLResponse)
    def home() -> str:
        return HOME_HTML.read_text(encoding="utf-8")

    @hub.get("/hub/samples")
    def samples():
        return {"samples": workspace.list_samples()}

    @hub.post("/hub/new")
    def new_layout(body: dict):
        name = (body.get("name") or "").strip() or "New layout"
        sample_id = workspace.new_sample_id(name)
        # the blank plan carries the chosen name so it reads nicely before the first save
        editor_target.set(workspace.sample_path(sample_id), sample_id, name)
        return {"sample_id": sample_id, "editor_url": "/editor/"}

    @hub.get("/hub/edit/{sample_id}")
    def edit(sample_id: str):
        if not workspace.has_sample(sample_id):
            return JSONResponse({"error": f"no layout {sample_id!r}"}, status_code=404)
        editor_target.set(workspace.sample_path(sample_id), sample_id)
        return RedirectResponse("/editor/", status_code=303)

    @hub.get("/hub/furnish/{sample_id}")
    def furnish(sample_id: str):
        try:
            project_dir = workspace.open_or_create_project(sample_id)
        except (FileNotFoundError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        session.open(project_dir)
        return RedirectResponse("/furnish/", status_code=303)

    hub.mount("/editor", create_editor_app(editor_target))
    hub.mount("/furnish", create_furnish_app(session))
    return hub
