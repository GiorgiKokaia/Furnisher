# 11 — Dev Setup & Conventions

**Status:** done (M0 scaffold in place; `uv` invoked as `python -m uv` on this machine)

## Stack

- **Python 3.12+**, managed with **uv** (`uv init`, `uv add`, `uv run`). Windows is the primary
  dev machine — keep dependencies Windows-friendly (watch out: `cairosvg` needs cairo; document
  the install or prefer `resvg-py`).
- Package layout: `src/` layout, single package `furnisher`, one subpackage per component doc:

```
pyproject.toml
src/furnisher/
  model/        # 01 schema + geometry
  authoring/    # 02
  catalog/      # 03
  agent/        # 04 (+ prompts/)
  llm/          # 04/07 provider wrapper
  layout/       # 05
  render2d/     # 06
  render3d/     # 07 (2.5D for now)
  app/          # 08 orchestration + furnish FastAPI app
  hub/          # 08 launcher: workspace + home page, mounts editor + furnish (+ samples/)
  project/      # 09 persistence
  cli.py        # `furnisher` entry point (typer); `furnisher start` = the launcher
tests/
  fixtures/     # plans, recorded API responses, golden SVGs
workspace/      # gitignored: user's layout library (samples/) + furnish projects/
experiments/    # gitignored scratch (esp. room-render iterations, 07)
```

## Core dependencies (add as needed, not all up front)

`pydantic`, `shapely`, `httpx`, `pyyaml`, `typer`, `watchfiles`, `google-genai`, `resvg-py`
(SVG→PNG; chosen over cairosvg — no native cairo needed on Windows), `fastapi`+`uvicorn`,
`pytest`. (`svgwrite`/`pillow` turned out unnecessary — SVG is hand-rolled strings.)

## Configuration & secrets

- `GEMINI_API_KEY` from environment; also load a gitignored `.env` at repo root via
  `pydantic-settings`. **Never** write the key into project files, logs, or docs.
- A single `Settings` object (`furnisher/config.py`): api key, per-provider market settings
  (e.g. IKEA `cc`/`lc`), cache dir (`~/.furnisher/`), model names. All model names live here,
  nowhere else.
- `.gitignore` from day one: `.env`, `experiments/`, `__pycache__/`, `*.egg-info`, `.venv/`.

## Shipping a build to a non-technical person (`packaging/`)

`uv run --with pyinstaller python packaging/build_exe.py` produces a single
`dist/Furnisher.exe` (~46 MB, Windows-only — PyInstaller cannot cross-build, so a Mac
recipient needs a hosted instance instead). `furnisher/desktop.py` is the frozen entry point:
it re-answers the three things the CLI takes for granted — workspace goes to
`%LOCALAPPDATA%\Furnisher\workspace` (CWD is wherever Explorer launched from), the port falls
back to a free one if 8380 is taken, and failures print and wait rather than flashing a window
shut. Ship `dist/READ ME FIRST.txt` alongside it: an unsigned exe trips SmartScreen, and a
non-technical recipient who doesn't know to click "More info" → "Run anyway" is simply stuck.

**The embedded key is not a secret.** The build injects `GEMINI_API_KEY` via a generated
runtime hook (gitignored, deleted after the build), so it never enters a tracked file — but it
is trivially extractable from the .exe. Anything shipped this way should be a dedicated,
spend-capped, revocable key; treat a shipped key as published.

## Conventions

- Every LLM/API-touching test runs against **recorded fixtures**; network access in tests is a
  bug. Record real responses once per endpoint into `tests/fixtures/`.
- CLI is the integration surface: each milestone's exit criterion is a `furnisher ...` command
  that a human can run (see 00). Wire subcommands as components land.
- Type hints everywhere; `ruff` for lint+format (`ruff check`, `ruff format`).
- Keep component docs (`docs/*.md`) updated when reality diverges — they're the resume-point for
  future sessions/agents. Update the **Status** line and check off tasks as they complete.

## Tasks (M0 kickoff)

- [x] pyproject (hatchling, src layout) + `uv sync`
- [x] `.gitignore`, `.env` handling, `Settings` (`config.py`)
- [x] `furnisher` typer entry point with `--version`
- [x] `pytest` + `ruff` configured and passing
- [x] First commit
