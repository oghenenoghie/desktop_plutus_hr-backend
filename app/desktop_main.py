"""Entrypoint for the desktop-bundled build (see desktop/plutus-backend.spec).

Mirrors railway.json's preDeployCommand + startCommand — run migrations,
then serve — but in one process, since the desktop app has no separate
pre-deploy step: the Electron main process just spawns this executable
once per launch.

Runs from a PyInstaller onedir bundle, where alembic's script_location and
alembic.ini ship as data files under sys._MEIPASS (the COLLECT step's
data directory, e.g. dist/plutus-backend/_internal) — not next to
sys.executable itself, which is one level up in onedir mode.
"""

import os
import sys
from pathlib import Path

import uvicorn
from alembic.config import Config

from alembic import command


def _bundle_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def _run_migrations() -> None:
    bundle_root = _bundle_root()
    cfg = Config(str(bundle_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(bundle_root / "alembic"))
    command.upgrade(cfg, "head")


def main() -> None:
    _run_migrations()

    host = os.environ.get("DESKTOP_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("DESKTOP_BACKEND_PORT", "8000"))

    from app.main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
