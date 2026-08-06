#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

failures=0
warnings=0

fail() {
  printf '[FAIL] %s\n' "$1" >&2
  failures=$((failures + 1))
}

warn() {
  printf '[WARN] %s\n' "$1" >&2
  warnings=$((warnings + 1))
}

info() {
  printf '[INFO] %s\n' "$1"
}

info "Checking tracked files for local-only runtime artifacts"

while IFS= read -r path; do
  case "$path" in
    .env|.env.*)
      [[ "$path" == ".env.template" ]] || fail "tracked environment file: $path"
      ;;
    data/config.json|data/config.json.bak)
      fail "tracked runtime config file: $path"
      ;;
    data/renders/*|data/outputs/*|dashboard/static/renders/*|hermes_outputs/*)
      fail "tracked generated render/output artifact: $path"
      ;;
    *.DS_Store|*/.DS_Store)
      fail "tracked macOS metadata file: $path"
      ;;
    *.mp4|*.webm|*.mov)
      case "$path" in
        marketing/assets/the-cinesmith-demo.mp4) ;;
        *)
          warn "tracked video asset outside the approved demo path: $path"
          ;;
      esac
      ;;
  esac
done < <(git -C "$ROOT" ls-files)

info "Scanning tracked content for obvious secret tokens"

secret_matches="$(
  git -C "$ROOT" grep -InE \
    '(sk-[A-Za-z0-9_-]{20,}|gh[opsu]_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{25,}|xox[baprs]-[0-9A-Za-z-]{20,}|Bearer[[:space:]]+[A-Za-z0-9._~+/=-]{40,})' \
    -- . \
    ':(exclude)marketing/assets/*' \
    ':(exclude)data/character_banks/anchors/*' \
    ':(glob,exclude)hermes_home/**/references/*' \
    || true
)"

if [[ -n "$secret_matches" ]]; then
  printf '%s\n' "$secret_matches" >&2
  fail "possible API key or bearer token found in tracked files"
fi

info "Scanning tracked content for private/local IP addresses"

ip_matches="$(
  git -C "$ROOT" grep -InE \
    '(http://)?(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|100\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3})' \
    -- . \
    ':(exclude)marketing/assets/*' \
    ':(exclude)data/character_banks/anchors/*' \
    ':(glob,exclude)hermes_home/**/references/*' \
    || true
)"

if [[ -n "$ip_matches" ]]; then
  printf '%s\n' "$ip_matches" >&2
  warn "private/local IP address references need review before pushing public changes"
fi

info "Running local dashboard smoke suite when Cinesmith is listening on 127.0.0.1:7000"

if python3 - <<'PY'
import socket
sock = socket.socket()
sock.settimeout(0.25)
try:
    sock.connect(("127.0.0.1", 7000))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
then
  python3 "$ROOT/scripts/smoke_cinesmith.py" --base-url http://127.0.0.1:7000
else
  warn "dashboard not listening on 127.0.0.1:7000; skipped scripts/smoke_cinesmith.py"
fi

if (( failures > 0 )); then
  printf '[FAIL] Hygiene check found %d blocking issue(s) and %d warning(s).\n' "$failures" "$warnings" >&2
  exit 1
fi

printf '[OK] Hygiene check passed with %d warning(s).\n' "$warnings"
