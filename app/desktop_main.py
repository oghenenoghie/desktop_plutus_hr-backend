"""Entrypoint for the desktop-bundled build (see desktop/plutus-backend.spec).

Mirrors railway.json's preDeployCommand + startCommand — run migrations,
then serve — but in one process, since the desktop app has no separate
pre-deploy step: the Electron main process just spawns this executable
once per launch.

The embedded Postgres cluster's own user (DATABASE_URL) is a superuser,
which row-level security never applies to. So this runs the migrations as
that user, then provisions the ordinary role APP_DATABASE_ROLE with the
password the Electron app keeps for it (APP_DATABASE_PASSWORD), and serves
as that role with REQUIRE_RLS_ENFORCED on. Without APP_DATABASE_PASSWORD
(an older Electron shell) it serves as the cluster user, and the API logs
that row-level security isn't enforced.

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
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from alembic import command

APP_DATABASE_ROLE = "plutus_app"


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


def _serve_as_app_role() -> None:
    """Provisions the ordinary role and points DATABASE_URL at it."""
    password = os.environ.get("APP_DATABASE_PASSWORD")
    if not password:
        return
    from app.core import db
    from app.core.config import get_settings
    from app.core.db_roles import ensure_app_role, grant_app_role

    owner_url = os.environ["DATABASE_URL"]
    owner = create_engine(owner_url)
    with owner.begin() as conn:
        ensure_app_role(conn, role=APP_DATABASE_ROLE, password=password)
        grant_app_role(conn, role=APP_DATABASE_ROLE)
    owner.dispose()

    app_url = make_url(owner_url).set(username=APP_DATABASE_ROLE, password=password)
    os.environ["MIGRATION_DATABASE_URL"] = owner_url
    os.environ["DATABASE_URL"] = app_url.render_as_string(hide_password=False)
    os.environ["APP_DATABASE_ROLE"] = APP_DATABASE_ROLE
    os.environ["REQUIRE_RLS_ENFORCED"] = "true"
    # The migrations read the settings as the cluster user; the app must
    # read them afresh.
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_session_factory.cache_clear()


def main() -> None:
    _run_migrations()
    _serve_as_app_role()

    host = os.environ.get("DESKTOP_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("DESKTOP_BACKEND_PORT", "8000"))

    from app.main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
