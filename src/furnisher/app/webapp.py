"""M5 web app (docs/08 stage 2): furnished plan + chat side by side, room image gallery.

Thin layer over the same Orchestrator the CLI REPL uses — if this file needs new core
logic, that logic is in the wrong place.

The app is driven by a swappable `FurnishSession` (which project is open), so the same
instance can be mounted inside the hub launcher (docs/08 unified entry) and have the hub
switch projects under it. `create_app(project_dir)` keeps the standalone `furnisher app`
path working by opening a session on one project up front.
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from shapely.geometry import LineString

from furnisher.app.orchestrator import Orchestrator, image_proxy_url
from furnisher.catalog import default_catalog
from furnisher.layout import placement_polygon, validate
from furnisher.model import geometry
from furnisher.project import Project
from furnisher.render2d import RenderStyle, render_plan

WALL_SNAP_M = 0.3  # dragged items this close to a wall get pulled flush (0.05 gap)
APP_HTML = Path(__file__).parent / "app.html"


def snap_to_wall(plan, placement, item) -> None:
    """Pull a dragged item flush to its nearest wall when it lands close to one."""
    room = plan.room(placement.room)
    footprint = placement_polygon(placement, item)
    best = None
    for i in range(len(room.polygon)):
        a, b = geometry.edge(room.polygon, i)
        dist = footprint.distance(LineString([a, b]))
        if best is None or dist < best[0]:
            n = geometry.left_normal(geometry.unit(a, b))
            best = (dist, n)
    if best is None:
        return
    dist, n = best
    shift = dist - 0.05
    if 0 < shift and dist < WALL_SNAP_M:
        placement.position = (
            round(placement.position[0] - n[0] * shift, 3),
            round(placement.position[1] - n[1] * shift, 3),
        )


class FurnishSession:
    """Which project the furnish app is currently serving. The hub swaps this to switch
    layouts; catalog and LLM are shared across projects (expensive, project-agnostic)."""

    def __init__(self, catalog, llm):
        self.catalog = catalog
        self.llm = llm
        self.orch: Orchestrator | None = None

    def open(self, project_dir: Path) -> Orchestrator:
        self.orch = Orchestrator(Project.load(project_dir), self.catalog, self.llm)
        return self.orch


def create_app(project_dir: Path, llm=None) -> FastAPI:
    """Standalone furnish app for one project (`furnisher app <project>`)."""
    if llm is None:
        from furnisher.llm import GeminiLLM

        llm = GeminiLLM()
    session = FurnishSession(default_catalog(), llm)
    session.open(project_dir)
    return create_furnish_app(session)


def _safe_under(base: Path, rel: str) -> Path | None:
    """Resolve `rel` under `base`, refusing to escape it (path-traversal guard)."""
    target = (base / rel).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        return None
    return target


def create_furnish_app(session: FurnishSession) -> FastAPI:
    """The furnish app, reading the current project from `session` on every request."""
    catalog = session.catalog
    app = FastAPI(title="Furnisher")

    def state() -> dict:
        orch = session.orch
        project = orch.project
        issues = validate(project.plan, project.placements, catalog)
        rooms_dir = project.path / "renders" / "rooms"
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
            "svg_scale": RenderStyle().scale,  # px per meter, for drag math in the browser
            "rooms": [r.id for r in project.plan.rooms],
            "placements": [
                {
                    "id": p.id,
                    "room": p.room,
                    "item": catalog.get(p.item_ref).name,
                    "type": catalog.get(p.item_ref).type_name,
                    "price": catalog.get(p.item_ref).price,
                    "currency": catalog.get(p.item_ref).currency,
                    "dims": f"{catalog.get(p.item_ref).width_m * 100:.0f}×"
                    f"{catalog.get(p.item_ref).depth_m * 100:.0f} cm",
                    "image": image_proxy_url(catalog.get(p.item_ref)),
                    "url": catalog.get(p.item_ref).url,
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
    def index():
        if session.orch is None:  # opened directly without picking a layout — send home
            return RedirectResponse("/", status_code=307)
        return HTMLResponse(APP_HTML.read_text(encoding="utf-8"))

    # renders/ and inspiration/ are served from the *current* project (no fixed static mount,
    # so switching projects just works). URLs are relative in app.html, so these resolve both
    # standalone (at /) and when the hub mounts this app under /furnish.
    @app.get("/renders/{path:path}")
    def renders(path: str):
        target = _safe_under(session.orch.project.path / "renders", path)
        if target is None or not target.is_file():
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(target)

    @app.get("/inspiration/{path:path}")
    def inspiration(path: str):
        target = _safe_under(session.orch.project.path / "inspiration", path)
        if target is None or not target.is_file():
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(target)

    @app.get("/api/item-image")
    def item_image(id: str, n: int = 0):
        """Cache-backed product-image proxy: downloads+caches server-side (reliable), then
        serves the local file — browsers hotlinking the IKEA CDN get intermittent failures."""
        try:
            paths = catalog.image_paths(id, max_images=n + 1)
        except KeyError:
            return JSONResponse({"error": "unknown item"}, status_code=404)
        if len(paths) <= n:
            return JSONResponse({"error": "no image"}, status_code=404)
        return FileResponse(paths[n])

    @app.get("/api/state")
    def get_state():
        return state()

    @app.post("/api/message")
    def message(body: dict):
        """NDJSON stream: {"progress": ...} lines while the agent works, then the result."""
        orch = session.orch
        text = (body.get("text") or "").strip()
        if not text:
            return JSONResponse({"error": "empty message"}, status_code=400)

        progress_queue: queue.Queue = queue.Queue()
        result: dict = {}

        def work() -> None:
            orch.on_progress = progress_queue.put
            try:
                result.update(orch.handle_message(text))
            except Exception as exc:  # surface into the chat instead of a broken stream
                result["reply"] = f"error: {exc}"
                orch.project.append_chat("assistant", result["reply"])
            finally:
                orch.on_progress = None
                progress_queue.put(None)

        def stream():
            threading.Thread(target=work, daemon=True).start()
            while True:
                item = progress_queue.get()
                if item is None:
                    break
                yield json.dumps({"progress": item}) + "\n"
            yield json.dumps({**result, "state": state()}) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/choose")
    def choose(body: dict):
        result = session.orch.handle_message(str(int(body.get("index", -1)) + 1))
        return {**result, "state": state()}

    @app.post("/api/undo")
    def undo():
        orch = session.orch
        ok = orch.project.undo()
        orch.render_svg()
        return {"ok": ok, "state": state()}

    @app.post("/api/placement")
    def placement_edit(body: dict):
        """Move/rotate/delete one placed item, validated live (docs/08 click-to-adjust)."""
        orch = session.orch
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
                if body.get("snap", True):
                    snap_to_wall(project.plan, changed, catalog.get(changed.item_ref))
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
        orch = session.orch
        query = (body.get("query") or "").strip()
        if not query:
            return JSONResponse({"error": "empty query"}, status_code=400)
        orch.last_inspiration = []
        reply = orch.inspire_from_ikea(query, body.get("notes", ""))
        orch.project.append_chat("assistant", reply)
        images = [f"inspiration/{name}" for name in orch.last_inspiration]
        return {"reply": reply, "images": images, "state": state()}

    @app.post("/api/apartment-image")
    def apartment_image(body: dict):
        from furnisher.render3d import generate_apartment_image

        orch = session.orch
        if not orch.project.placements:
            return JSONResponse(
                {"error": "nothing placed yet — furnish a room first"}, status_code=400
            )
        out = generate_apartment_image(
            session.llm,
            catalog,
            orch.project,
            feedback=body.get("feedback", ""),
            force=bool(body.get("force")),
        )
        return {"image": f"renders/rooms/{out.name}", "state": state()}

    @app.post("/api/room-image")
    def room_image(body: dict):
        from furnisher.render3d import generate_room_image

        orch = session.orch
        room_id = body.get("room")
        try:
            out = generate_room_image(
                session.llm,
                catalog,
                orch.project,
                room_id,
                feedback=body.get("feedback", ""),
                force=bool(body.get("force")),
            )
        except (ValueError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return {"image": f"renders/rooms/{out.name}", "state": state()}

    return app
