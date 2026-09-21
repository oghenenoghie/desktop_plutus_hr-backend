#!/usr/bin/env bash
# Builds the desktop backend bundle at dist/plutus-backend/ (onedir).
# The Electron app (desktop_plutus_hr-frontend) copies this directory
# in as an extraResource — see that repo's electron-builder config.
set -euo pipefail

cd "$(dirname "$0")/.."

uv run --group dev pyinstaller desktop/plutus-backend.spec --noconfirm --distpath dist --workpath build
