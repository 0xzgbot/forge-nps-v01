#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for Cinesmith.
# Prepares a Python virtualenv, project dependencies, the hermes_engine
# submodule, and a local .env so the FastAPI dashboard can run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[install] repo root: $ROOT"

# 1. System package required to create Python virtualenvs on Debian/Ubuntu.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "[install] installing python3-venv"
  sudo apt-get update -qq
  PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  sudo apt-get install -y -qq "python${PYVER}-venv" || sudo apt-get install -y -qq python3-venv
fi

# 2. Fetch the hermes_engine submodule (provides the Hermes CLI launcher).
echo "[install] syncing git submodules"
git submodule update --init --recursive || echo "[install] WARN: submodule init failed (dashboard still runs without it)"

# 3. Create the virtualenv and install Python dependencies.
if [ ! -x ".venv/bin/python" ]; then
  echo "[install] creating virtualenv .venv"
  python3 -m venv .venv
fi
echo "[install] installing Python requirements"
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

# 4. Seed a local .env from the template if the developer has none yet.
if [ ! -f ".env" ]; then
  echo "[install] creating .env from .env.template"
  cp .env.template .env
fi

echo "[install] done"
