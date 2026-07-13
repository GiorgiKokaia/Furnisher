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


if __name__ == "__main__":
    app()
