# Desktop build

Packages this backend as a standalone executable for the Plutus desktop
app (see `desktop_plutus_hr-frontend`'s `electron/`), which bundles this
alongside an embedded Postgres and the Next.js frontend so the whole app
runs fully offline on 127.0.0.1 — no cloud backend, no network required.

`app/desktop_main.py` is the entrypoint: it runs `alembic upgrade head`
against whatever `DATABASE_URL` it's given, then starts uvicorn on
`DESKTOP_BACKEND_HOST`/`DESKTOP_BACKEND_PORT` (defaults
`127.0.0.1:8000`) — the same migrate-then-serve sequence as
`railway.json`'s `preDeployCommand`/`startCommand`, just in one process
since the desktop app has no separate pre-deploy step.

## Building

```bash
uv sync --group dev
./desktop/build.sh
```

Produces a onedir PyInstaller bundle at `dist/plutus-backend/` — onedir
rather than onefile because alembic needs its `script_location`
(`env.py`, `versions/*.py`) as real files on disk at runtime, not frozen
into the executable; see `plutus-backend.spec`'s `datas`.

The Electron app's `electron/prepare-resources.js` copies this directory
in as an `extraResource`; `BACKEND_DIST_DIR` in that script (or the
`build-desktop.yml` CI workflow in the frontend repo) points at it.

## Running it standalone (for testing)

```bash
DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/plutus" \
JWT_SECRET="some-32-byte-secret" \
DESKTOP_BACKEND_PORT=8123 \
dist/plutus-backend/plutus-backend
```

## Accounting audit

The accounting / chart-of-accounts audit and implementation plan lives in
one place, the cloud backend repo:
[`ACCOUNTING_IMPLEMENTATION_AUDIT.md`](https://github.com/oghenenoghie/plutus-hr-system/blob/main/ACCOUNTING_IMPLEMENTATION_AUDIT.md).
It applies to this repo unchanged: `app/` and `alembic/` here are identical
to `plutus-hr-system` (see the audit's §2.4). Per its assumption A28, every
accounting change, including every Alembic revision, has to land in both
repositories in the same revision order. Otherwise the desktop and cloud
schemas diverge, and `alembic upgrade head` in `app/desktop_main.py` would
migrate desktop installs to a different schema than the cloud's.
