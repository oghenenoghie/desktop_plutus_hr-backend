# PyInstaller spec for the desktop-bundled backend.
#
# Builds a onedir bundle (not onefile) because alembic needs its
# script_location — env.py, script.py.mako, versions/*.py — as real files
# on disk at runtime, not frozen into the executable. desktop_main.py
# resolves them next to the executable at `sys.executable`'s directory.
#
# Run from the repo root: uv run pyinstaller desktop/plutus-backend.spec

import sys
from pathlib import Path

REPO_ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(REPO_ROOT / "app" / "desktop_main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[
        (str(REPO_ROOT / "alembic.ini"), "."),
        (str(REPO_ROOT / "alembic" / "env.py"), "alembic"),
        (str(REPO_ROOT / "alembic" / "script.py.mako"), "alembic"),
        (str(REPO_ROOT / "alembic" / "versions"), "alembic/versions"),
    ],
    hiddenimports=[
        "psycopg",
        "psycopg_binary",
        "argon2",
        "email_validator",
        "PIL",
        "reportlab",
        "boto3",
        "apscheduler.triggers.cron",
        "apscheduler.triggers.interval",
        "apscheduler.executors.pool",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="plutus-backend",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="plutus-backend",
)
