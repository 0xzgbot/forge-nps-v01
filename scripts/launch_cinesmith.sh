#!/usr/bin/env bash
# Launch Cinesmith with Hermes isolation and portable paths.
# Never points Hermes at ~/.hermes unless CINESMITH_ALLOW_GLOBAL_HERMES=1.
#
# Usage:
#   ./scripts/launch_cinesmith.sh              # dev: uvicorn --reload
#   ./scripts/launch_cinesmith.sh --package    # ship: no reload, package banner
#   CINESMITH_PACKAGE_MODE=1 ./scripts/launch_cinesmith.sh
#   CINESMITH_SKIP_PREFLIGHT=1 ./scripts/launch_cinesmith.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export CINESMITH_REPO_ROOT="$ROOT"
export HERMES_HOME="${HERMES_HOME:-$ROOT/hermes_home}"
export CINESMITH_HERMES_HOME="$ROOT/hermes_home"
export PYTHONPATH="${PYTHONPATH:-}:$ROOT"

PACKAGE_MODE="${CINESMITH_PACKAGE_MODE:-${FORGE_PACKAGE_MODE:-0}}"
SKIP_PREFLIGHT="${CINESMITH_SKIP_PREFLIGHT:-${FORGE_SKIP_PREFLIGHT:-0}}"
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --package|-p)
      PACKAGE_MODE=1
      ;;
    --skip-preflight)
      SKIP_PREFLIGHT=1
      ;;
    --help|-h)
      cat <<'EOF'
Cinesmith launcher

  ./scripts/launch_cinesmith.sh              Dev mode (uvicorn --reload)
  ./scripts/launch_cinesmith.sh --package    Package mode (no reload)
  ./scripts/launch_cinesmith.sh --skip-preflight

Env:
  CINESMITH_PACKAGE_MODE=1     Same as --package
  CINESMITH_SKIP_PREFLIGHT=1   Skip scripts/preflight_desktop_spark.py
  DASHBOARD_PORT / PORT    Default 7000
  CINESMITH_HOST               Default 127.0.0.1
  CINESMITH_ALLOW_GLOBAL_HERMES=1  Allow ~/.hermes (not recommended)
EOF
      exit 0
      ;;
    *)
      ARGS+=("$arg")
      ;;
  esac
done

# Prefer sibling media folder when present; else repo-local media/
if [[ -z "${CINESMITH_MEDIA_ROOT:-}" ]]; then
  CINESMITH_MEDIA_ROOT="${FORGE_MEDIA_ROOT:-}"
fi
if [[ -z "${CINESMITH_MEDIA_ROOT:-}" ]]; then
  if [[ -d "$ROOT/../CINESMITH_MEDIA" ]]; then
    export CINESMITH_MEDIA_ROOT="$(cd "$ROOT/../CINESMITH_MEDIA" && pwd)"
  elif [[ -d "$ROOT/../FORGE_NPS_MEDIA" ]]; then
    export CINESMITH_MEDIA_ROOT="$(cd "$ROOT/../FORGE_NPS_MEDIA" && pwd)"
  else
    mkdir -p "$ROOT/media/images" "$ROOT/media/videos" "$ROOT/media/imports"
    export CINESMITH_MEDIA_ROOT="$ROOT/media"
  fi
fi

# Guard: refuse accidental global Hermes unless explicitly allowed
if [[ "${CINESMITH_ALLOW_GLOBAL_HERMES:-${FORGE_ALLOW_GLOBAL_HERMES:-0}}" != "1" ]]; then
  export HERMES_HOME="$ROOT/hermes_home"
fi

PORT="${DASHBOARD_PORT:-${PORT:-7000}}"
HOST="${CINESMITH_HOST:-${FORGE_HOST:-127.0.0.1}}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

# Re-assert isolation after sourcing .env (in case .env set HERMES_HOME)
if [[ "${CINESMITH_ALLOW_GLOBAL_HERMES:-${FORGE_ALLOW_GLOBAL_HERMES:-0}}" != "1" ]]; then
  export HERMES_HOME="$ROOT/hermes_home"
  export CINESMITH_HERMES_HOME="$ROOT/hermes_home"
fi
# Media may have been overridden by .env — keep explicit export if still empty
if [[ -z "${CINESMITH_MEDIA_ROOT:-}" ]]; then
  CINESMITH_MEDIA_ROOT="${FORGE_MEDIA_ROOT:-}"
fi
if [[ -z "${CINESMITH_MEDIA_ROOT:-}" ]]; then
  if [[ -d "$ROOT/../CINESMITH_MEDIA" ]]; then
    export CINESMITH_MEDIA_ROOT="$(cd "$ROOT/../CINESMITH_MEDIA" && pwd)"
  elif [[ -d "$ROOT/../FORGE_NPS_MEDIA" ]]; then
    export CINESMITH_MEDIA_ROOT="$(cd "$ROOT/../FORGE_NPS_MEDIA" && pwd)"
  else
    export CINESMITH_MEDIA_ROOT="$ROOT/media"
  fi
fi

# Optional preflight (hard fails abort launch)
if [[ "$SKIP_PREFLIGHT" != "1" ]]; then
  if [[ -f "$ROOT/scripts/preflight_desktop_spark.py" ]]; then
    if ! python3 "$ROOT/scripts/preflight_desktop_spark.py"; then
      echo ""
      echo "Preflight failed. Fix issues above, or relaunch with CINESMITH_SKIP_PREFLIGHT=1 / --skip-preflight."
      exit 1
    fi
  fi
fi

# Re-assert isolation one more time after preflight (preflight may load dotenv patterns)
if [[ "${CINESMITH_ALLOW_GLOBAL_HERMES:-${FORGE_ALLOW_GLOBAL_HERMES:-0}}" != "1" ]]; then
  export HERMES_HOME="$ROOT/hermes_home"
  export CINESMITH_HERMES_HOME="$ROOT/hermes_home"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
if [[ "$PACKAGE_MODE" == "1" ]]; then
  echo "  Cinesmith — Desktop + Spark package mode"
else
  echo "  Cinesmith — development mode"
fi
echo "═══════════════════════════════════════════════════════════"
echo "  repo:        $ROOT"
echo "  HERMES_HOME: $HERMES_HOME"
echo "  MEDIA:       ${CINESMITH_MEDIA_ROOT}"
echo "  url:         http://${HOST}:${PORT}"
if [[ "$PACKAGE_MODE" == "1" ]]; then
  echo "  reload:      off (package)"
else
  echo "  reload:      on (dev)"
fi
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Open:  http://${HOST}:${PORT}"
echo "  Docs:  docs/DESKTOP_SPARK_PACKAGE.md"
echo ""

UVICORN_ARGS=(python3 -m uvicorn dashboard.cinesmith_dashboard:app --host "$HOST" --port "$PORT")
if [[ "$PACKAGE_MODE" != "1" ]]; then
  UVICORN_ARGS+=(--reload)
fi
# Pass through any unknown args to uvicorn
if [[ ${#ARGS[@]} -gt 0 ]]; then
  UVICORN_ARGS+=("${ARGS[@]}")
fi

exec "${UVICORN_ARGS[@]}"
