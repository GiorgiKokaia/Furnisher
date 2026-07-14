"""Build the double-clickable Furnisher.exe.

    uv run --with pyinstaller python packaging/build_exe.py

The key: `furnisher.config` reads GEMINI_API_KEY from the environment, so we generate a
PyInstaller *runtime hook* that sets it before any furnisher import runs. The hook is written
to a gitignored path and deleted after the build, so the key never lands in a tracked file --
but understand that it IS readable inside the .exe by anyone who cares to look. Treat any key
you ship here as public: use a dedicated, revocable, spend-capped one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "packaging" / "_key_hook.py"  # gitignored; deleted in the finally below

# Files that live inside the package but aren't .py, so PyInstaller can't infer them.
DATA = [
    "furnisher/agent/prompts",
    "furnisher/app/app.html",
    "furnisher/authoring/editor.html",
    "furnisher/catalog/data",
    "furnisher/hub/home.html",
    "furnisher/hub/samples",
]


def read_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "GEMINI_API_KEY":
                    key = value.strip().strip("'\"")
    if not key:
        sys.exit("no GEMINI_API_KEY in the environment or .env — nothing to embed")
    return key


def main() -> None:
    key = read_key()
    HOOK.write_text(f'import os\nos.environ["GEMINI_API_KEY"] = {key!r}\n', encoding="utf-8")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", "Furnisher",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--runtime-hook", str(HOOK),
        # typer/click and uvicorn pull these in dynamically, so static analysis misses them
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        "--collect-all", "resvg_py",
    ]
    for item in DATA:
        src = ROOT / "src" / item
        dest = item if src.is_dir() else str(Path(item).parent)
        args += ["--add-data", f"{src}{os.pathsep}{dest}"]
    args.append(str(ROOT / "src" / "furnisher" / "desktop.py"))

    try:
        subprocess.run(args, cwd=ROOT, check=True)
    finally:
        HOOK.unlink(missing_ok=True)  # never leave the key lying around in the tree
        shutil.rmtree(ROOT / "build", ignore_errors=True)

    exe = ROOT / "dist" / ("Furnisher.exe" if os.name == "nt" else "Furnisher")
    size = exe.stat().st_size / 1_000_000
    print(f"\nbuilt {exe} ({size:.0f} MB)")


if __name__ == "__main__":
    main()
