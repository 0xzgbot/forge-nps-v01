#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUBMODULE_DIR="$ROOT_DIR/hermes_engine"

if [[ ! -d "$SUBMODULE_DIR/.git" && ! -f "$SUBMODULE_DIR/.git" ]]; then
  echo "Error: hermes_engine is missing or not a git repo at: $SUBMODULE_DIR" >&2
  exit 1
fi

echo "[1/5] Ensuring submodule mapping exists in parent repo..."
git -C "$ROOT_DIR" submodule sync -- hermes_engine

echo "[2/5] Fetching latest hermes-agent (main)..."
git -C "$SUBMODULE_DIR" fetch origin main --tags

echo "[3/5] Switching to main..."
git -C "$SUBMODULE_DIR" switch main >/dev/null 2>&1 || git -C "$SUBMODULE_DIR" checkout main

echo "[4/5] Pulling latest from origin/main..."
git -C "$SUBMODULE_DIR" pull --ff-only origin main

echo "[5/5] Updating parent gitlink..."
git -C "$ROOT_DIR" add hermes_engine .gitmodules

echo
echo "hermes_engine is now at:"
git -C "$SUBMODULE_DIR" rev-parse --short HEAD
echo
echo "Next step:"
echo "  git commit -m \"chore: update hermes_engine submodule\""
