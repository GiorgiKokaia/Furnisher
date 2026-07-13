"""M5 web app (docs/08 stage 2): furnished plan + chat side by side, room image gallery.

Thin layer over the same Orchestrator the CLI REPL uses — if this file needs new core
logic, that logic is in the wrong place.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from furnisher.app.orchestrator import Orchestrator
from furnisher.catalog import default_catalog
from furnisher.layout import validate
from furnisher.project import Project
from furnisher.render2d import render_plan

APP_HTML = Path(__file__).parent / "app.html"


def create_app(project_dir: Path, llm=None) -> FastAPI:
    if llm is None:
        from furnisher.llm import GeminiLLM

        llm = GeminiLLM()
    catalog = default_catalog()
    orch = Orchestrator(Project.load(project_dir), catalog, llm)

    app = FastAPI(title="Furnisher")
    renders_dir = orch.project.path / "renders"
    renders_dir.mkdir(exist_ok=True)
    app.mount("/renders", StaticFiles(directory=renders_dir), name="renders")

    def state() -> dict:
        project = orch.project
        issues = validate(project.plan, project.placements, catalog)
        rooms_dir = renders_dir / "rooms"
        images = (
            sorted(
                (p.name for p in rooms_dir.glob("*.png")),
                key=lambda n: (rooms_dir / n).stat().st_mtime,
                reverse=True,
            )
            if rooms_dir.is_dir()
            else []
        )
        style = project.meta.get("style_profile") or {}
        return {
            "name": project.meta["name"],
            "style_tags": style.get("style_tags", []),
            "budget": project.meta.get("budget"),
            "currency": project.meta.get("currency", "EUR"),
            "spent": project.spent(catalog),
            "rooms": [r.id for r in project.plan.rooms],
            "placements": [
                {
                    "id": p.id,
                    "room": p.room,
                    "item": catalog.get(p.item_ref).name,
                    "position": list(p.position),
                    "rotation": p.rotation,
                }
                for p in project.placements
            ],
            "svg": render_plan(project.plan, placements=project.placements, catalog=catalog),
            "shopping_list": orch.shopping_list(),
            "issues": [str(i) for i in issues],
            "room_images": images,
            "chat": project.chat_history(limit=100),
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return APP_HTML.read_text(encoding="utf-8")

    @app.get("/api/state")
    def get_state():
        return state()

    @app.post("/api/message")
    def message(body: dict):
        text = (body.get("text") or "").strip()
        if not text:
            return JSONResponse({"error": "empty message"}, status_code=400)
        try:
            reply = orch.handle_message(text)
        except Exception as exc:  # surface into the chat instead of a blank 500
            reply = f"error: {exc}"
            orch.project.append_chat("assistant", reply)
        return {"reply": reply, "state": state()}

    @app.post("/api/undo")
    def undo():
        ok = orch.project.undo()
        orch.render_svg()
        return {"ok": ok, "state": state()}

    @app.post("/api/placement")
    def placement_edit(body: dict):
        """Move/rotate/delete one placed item, validated live (docs/08 click-to-adjust)."""
        pid = body.get("id")
        action = body.get("action")
        project = orch.project
        current = next((p for p in project.placements if p.id == pid), None)
        if current is None or action not in ("move", "rotate", "delete"):
            return JSONResponse({"error": f"unknown placement {pid!r} or action"}, status_code=400)
        if action == "delete":
            trial = [p for p in project.placements if p.id != pid]
        else:
            changed = current.model_copy(deep=True)
            if action == "move":
                changed.position = (
                    round(changed.position[0] + float(body.get("dx", 0)), 3),
                    round(changed.position[1] + float(body.get("dy", 0)), 3),
                )
            else:
                changed.rotation = (changed.rotation + 90) % 360
            trial = [changed if p.id == pid else p for p in project.placements]
            errors = [
                i
                for i in validate(project.plan, trial, catalog)
                if i.severity == "error" and pid in i.placements
            ]
            if errors:
                return {"ok": False, "error": errors[0].message, "state": state()}
        project.snapshot()
        project.placements = trial
        project.save()
        orch.render_svg()
        return {"ok": True, "state": state()}

    @app.post("/api/inspire-ikea")
    def inspire_ikea(body: dict):
        query = (body.get("query") or "").strip()
        if not query:
            return JSONResponse({"error": "empty query"}, status_code=400)
        reply = orch.inspire_from_ikea(query, body.get("notes", ""))
        orch.project.append_chat("assistant", reply)
        return {"reply": reply, "state": state()}

    @app.post("/api/room-image")
    def room_image(body: dict):
        from furnisher.render3d import generate_room_image

        room_id = body.get("room")
        try:
            out = generate_room_image(
                llm,
                catalog,
                orch.project,
                room_id,
                feedback=body.get("feedback", ""),
                force=bool(body.get("force")),
            )
        except (ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return {"image": f"/renders/rooms/{out.name}", "state": state()}

    return app
