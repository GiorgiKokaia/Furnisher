"""`furnisher` CLI entry point. The CLI is the integration surface (docs/11)."""

from __future__ import annotations

from pathlib import Path

import typer

import furnisher
from furnisher.authoring import PlanLoadError, load_plan
from furnisher.render2d import render_plan

app = typer.Typer(help="Furnisher — chat-driven apartment furnishing.", no_args_is_help=True)
plan_app = typer.Typer(help="Floor plan authoring.", no_args_is_help=True)
app.add_typer(plan_app, name="plan")
catalog_app = typer.Typer(help="Furniture catalog search.", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")
furnish_app = typer.Typer(help="Furnishing: validate and render placements.", no_args_is_help=True)
app.add_typer(furnish_app, name="furnish")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"furnisher {furnisher.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    pass


def _load_or_exit(plan_file: Path):
    try:
        return load_plan(plan_file)
    except (PlanLoadError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@plan_app.command()
def validate(plan_file: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Check a plan YAML file: schema, geometry, opening placement."""
    plan = _load_or_exit(plan_file)
    errors = plan.validate_plan()
    for error in errors:
        typer.echo(f"ERROR: {error}", err=True)
    if errors:
        raise typer.Exit(code=1)
    typer.echo(
        f"OK — {plan.name!r}: {len(plan.rooms)} rooms, {len(plan.openings)} openings, "
        f"{plan.total_area():.1f} m² total"
    )


@plan_app.command()
def preview(
    plan_file: Path = typer.Argument(..., exists=True, readable=True),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output SVG path."),
    watch: bool = typer.Option(False, "--watch", "-w", help="Re-render on every save."),
) -> None:
    """Render a plan YAML file to SVG (optionally re-rendering whenever the file changes)."""
    out_path = out or plan_file.with_suffix(".svg")

    def render_once() -> None:
        try:
            plan = load_plan(plan_file)
        except (PlanLoadError, ValueError) as exc:
            typer.echo(f"error: {exc}", err=True)
            if not watch:
                raise typer.Exit(code=1) from exc
            return
        for error in plan.validate_plan():
            typer.echo(f"WARNING: {error}", err=True)
        out_path.write_text(render_plan(plan), encoding="utf-8")
        typer.echo(f"wrote {out_path}")

    render_once()
    if watch:
        from watchfiles import watch as watch_files

        typer.echo(f"watching {plan_file} (Ctrl+C to stop)")
        for _ in watch_files(plan_file):
            render_once()


@plan_app.command()
def edit(
    plan_file: Path = typer.Argument(..., help="Plan YAML file (created on first save)."),
    port: int = typer.Option(8377, "--port", "-p"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open a browser tab."),
) -> None:
    """Open the browser-based layout editor for a plan YAML file."""
    import threading
    import webbrowser

    import uvicorn

    from furnisher.authoring.editor import create_app

    url = f"http://127.0.0.1:{port}"
    if not no_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    typer.echo(f"editing {plan_file} at {url} (Ctrl+C to stop)")
    uvicorn.run(create_app(plan_file), host="127.0.0.1", port=port, log_level="warning")


@catalog_app.command("search")
def catalog_search(
    query: str = typer.Argument(...),
    max_price: float | None = typer.Option(None, "--max-price"),
    max_width: float | None = typer.Option(None, "--max-width", help="meters"),
    max_depth: float | None = typer.Option(None, "--max-depth", help="meters"),
    max_height: float | None = typer.Option(None, "--max-height", help="meters"),
    provider: str | None = typer.Option(None, "--provider", help="generic | ikea"),
    limit: int = typer.Option(8, "--limit", "-n"),
) -> None:
    """Search all catalog providers (results are cached in ~/.furnisher/)."""
    from furnisher.catalog import SearchFilters, default_catalog

    filters = SearchFilters(
        price_max=max_price, max_width_m=max_width, max_depth_m=max_depth, max_height_m=max_height
    )
    items = default_catalog().search(query, filters, provider=provider, limit=limit)
    if not items:
        typer.echo("no results")
        raise typer.Exit(code=1)
    for item in items:
        typer.echo(item.summary())


@catalog_app.command("show")
def catalog_show(item_id: str = typer.Argument(..., help="e.g. generic:loft-sofa-3")) -> None:
    """Show one catalog item (cache-first)."""
    from furnisher.catalog import default_catalog

    item = default_catalog().get(item_id)
    typer.echo(item.model_dump_json(indent=2, exclude={"raw"}))


project_app = typer.Typer(help="Project directories.", no_args_is_help=True)
app.add_typer(project_app, name="project")


@project_app.command("new")
def project_new(
    directory: Path = typer.Argument(..., help="Project directory to create."),
    plan: Path = typer.Option(..., "--plan", exists=True, help="Plan YAML to copy in."),
    name: str | None = typer.Option(None, "--name"),
) -> None:
    """Create a project directory from a plan file."""
    from furnisher.project import Project

    try:
        Project.create(directory, plan, name)
    except (FileExistsError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"created project at {directory}")


@app.command("chat")
def chat(project_dir: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Chat-driven furnishing (stage 1 REPL, docs/08)."""
    from furnisher.app.orchestrator import Orchestrator
    from furnisher.catalog import default_catalog
    from furnisher.llm import GeminiLLM, LLMError
    from furnisher.project import Project

    try:
        llm = GeminiLLM()
    except LLMError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    orch = Orchestrator(Project.load(project_dir), default_catalog(), llm)
    typer.echo(
        f"project {orch.project.meta['name']!r} — rooms: "
        f"{', '.join(r.id for r in orch.project.plan.rooms)}\n"
        "commands: /inspire <image> [notes] /budget <n> /plan /items /undo /quit — "
        "anything else is chat"
    )
    while True:
        try:
            message = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            continue
        if message.startswith("/"):
            cmd, _, arg = message.partition(" ")
            if cmd in ("/quit", "/exit"):
                break
            try:
                if cmd == "/plan":
                    typer.echo(f"agent> wrote {orch.render_svg()}")
                elif cmd == "/items":
                    typer.echo("agent>\n" + orch.shopping_list())
                elif cmd == "/budget":
                    typer.echo("agent> " + orch.set_budget(float(arg)))
                elif cmd == "/undo":
                    ok = orch.project.undo()
                    orch.render_svg()
                    typer.echo("agent> " + ("restored previous state" if ok else "nothing to undo"))
                elif cmd == "/inspire":
                    image_arg, _, notes = arg.partition(" ")
                    typer.echo("agent> " + orch.add_inspiration(Path(image_arg), notes))
                else:
                    typer.echo(f"agent> unknown command {cmd}")
            except Exception as exc:  # keep the REPL alive
                typer.echo(f"agent> error: {exc}")
            continue
        try:
            typer.echo("agent> " + orch.handle_message(message))
        except Exception as exc:
            typer.echo(f"agent> error: {exc}")


def _load_placements(path: Path):
    import json

    from furnisher.model import Placement

    data = json.loads(path.read_text(encoding="utf-8"))
    return [Placement.model_validate(p) for p in data.get("placements", [])]


@furnish_app.command("validate")
def furnish_validate(
    plan_file: Path = typer.Argument(..., exists=True),
    placements_file: Path = typer.Argument(..., exists=True),
) -> None:
    """Check placements: fit, overlaps, door swings, clearances."""
    from furnisher.catalog import default_catalog
    from furnisher.layout import validate as layout_validate

    plan = _load_or_exit(plan_file)
    placements = _load_placements(placements_file)
    issues = layout_validate(plan, placements, default_catalog())
    for issue in issues:
        typer.echo(str(issue), err=issue.severity == "error")
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise typer.Exit(code=1)
    typer.echo(f"OK — {len(placements)} placements, {len(issues)} warnings")


@furnish_app.command("render")
def furnish_render(
    plan_file: Path = typer.Argument(..., exists=True),
    placements_file: Path = typer.Argument(..., exists=True),
    out: Path | None = typer.Option(None, "--out", "-o"),
) -> None:
    """Render the furnished floor plan to SVG."""
    from furnisher.catalog import default_catalog

    plan = _load_or_exit(plan_file)
    placements = _load_placements(placements_file)
    out_path = out or plan_file.with_suffix(".furnished.svg")
    out_path.write_text(
        render_plan(plan, placements=placements, catalog=default_catalog()), encoding="utf-8"
    )
    typer.echo(f"wrote {out_path}")


if __name__ == "__main__":
    app()
