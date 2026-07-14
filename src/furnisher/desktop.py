"""Entry point for the double-clickable build (see packaging/).

The CLI assumes a developer: a repo checkout to keep `workspace/` in, a terminal already
open to read errors in, and a `.env` with a key. None of that holds when someone
double-clicks an .exe from their Downloads folder, so this module re-answers those three
questions and otherwise defers to the same `create_hub` the CLI uses.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def default_workspace() -> Path:
    """Somewhere writable that survives moving the .exe around.

    CWD is wherever Explorer happened to launch us from (often Downloads, sometimes a
    read-only mount), so the layouts must not live there.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "Furnisher" / "workspace"


def free_port(preferred: int = 8380) -> int:
    """Prefer the usual port so the URL is stable, but never fail on a busy one."""
    for port in (preferred, 0):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return probe.getsockname()[1]
            except OSError:
                continue
    return preferred


def _fatal(message: str) -> None:
    print("\n  Something went wrong:\n")
    print(f"    {message}\n")
    print("  Send this message to Giorgi and he can sort it out.")
    input("\n  Press Enter to close this window. ")
    sys.exit(1)


def main() -> None:
    import uvicorn

    from furnisher.hub import Workspace, create_hub
    from furnisher.llm import GeminiLLM, LLMError

    workspace = default_workspace()
    workspace.mkdir(parents=True, exist_ok=True)
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    print("\n  Furnisher\n")
    print("  Starting up — your browser will open in a moment.")
    print(f"  If it doesn't, open this address yourself:  {url}")
    print("\n  Keep this black window open while you use it.")
    print("  Closing it stops the program.\n")

    try:
        llm = GeminiLLM()
    except LLMError as exc:
        _fatal(f"couldn't reach the AI service ({exc})")
        return

    try:
        hub = create_hub(Workspace(workspace), llm)
    except Exception as exc:  # noqa: BLE001 - last resort: show it, don't flash and vanish
        _fatal(str(exc))
        return

    threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        uvicorn.run(hub, host="127.0.0.1", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        _fatal(str(exc))


if __name__ == "__main__":
    main()
