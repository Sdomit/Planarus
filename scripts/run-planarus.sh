#!/usr/bin/env bash
# =============================================================================
#  Planarus — local dev launcher for macOS / Linux (the scripts\run-planarus.bat twin)
#  Starts the FastAPI backend + Vite frontend, waits until both actually answer,
#  then opens the UI. Commands mirror docs/dev/setup.md.
#  NOTE: local dev only — the external (ChatGPT) API stays DISABLED.
#
#  Ports default to 8000/5173 and step up if busy; both servers are told the
#  result, so the proxy and the URL below can never point at a dead port.
# =============================================================================
set -euo pipefail
# The script lives in scripts/; everything it drives is relative to the repo
# root one level up, so resolve that rather than the script's own directory.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- preflight ---------------------------------------------------------------
if [ ! -x "$ROOT/apps/api/.venv/bin/python" ]; then
  echo "[ERROR] Backend venv missing: apps/api/.venv"
  echo "        First-time setup (see docs/dev/setup.md):"
  echo "          cd apps/api && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'"
  echo "        Debian/Ubuntu also need:  sudo apt install python3-venv"
  exit 1
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo "[ERROR] pnpm not found on PATH. Install Node 20+, then: corepack enable"
  exit 1
fi
if [ ! -d "$ROOT/apps/web/node_modules" ]; then
  echo "[SETUP] Web dependencies missing — running pnpm install once..."
  (cd "$ROOT" && pnpm install)
fi

# --- pick free ports ---------------------------------------------------------
# Python is already a hard dependency of this script, so use it for the probe.
# How the probe decides a port is taken — and why it connects rather than binds,
# on both loopback families — is documented in free_port itself.
# ponytail: check-then-bind races if something grabs the port in the next
# second; the server logs the bind error — rerun. Add a retry loop only if
# that actually happens to you.
free_port() {
  "$ROOT/apps/api/.venv/bin/python" - "$1" <<'PY'
import socket, sys

def busy(port):
    # Connect, don't bind. A bind test is unreliable: SO_REUSEADDR and Windows'
    # permissive 0.0.0.0-vs-127.0.0.1 rules both let it succeed on a taken port.
    # If anything answers on either loopback family, the port is taken.
    # ponytail: only checks loopback. A server bound solely to a LAN address
    # goes undetected — no dev server does that; revisit if one ever does.
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(0.25)
                if s.connect_ex((addr, port)) == 0:
                    return True
        except OSError:
            pass
    return False

start = int(sys.argv[1])
print(next((p for p in range(start, start + 50) if not busy(p)), start))
PY
}
API_PORT=$(free_port 8000)
WEB_PORT=$(free_port 5173)
[ "$API_PORT" = "8000" ] || echo "[PORT] 8000 busy — API moved to :$API_PORT"
[ "$WEB_PORT" = "5173" ] || echo "[PORT] 5173 busy — Web moved to :$WEB_PORT"

# --- optional team mode: ./scripts/run-planarus.sh team ------------------------------
# Off by default (D25/D26): a plain run stays the single-user local tool with no
# sign-in at all. "team" turns on the account gate and the password provider, so
# the first account you create claims the server as its admin and you can add
# viewers from Team. Exported for the children only — this shell exits with them.
MODE="local (no sign-in)"
if [ "${1:-}" = "team" ]; then
  export PLANARUS_AUTH_ENABLED=true PLANARUS_AUTH_PASSWORD_ENABLED=true
  MODE="team (sign-in required)"
fi

echo "Starting Planarus  |  API :$API_PORT   Web :$WEB_PORT   Mode: $MODE"

# --- start both, and make sure they die with this script ---------------------
# Job control on, so each background job leads its own process group and cleanup
# can signal the whole tree with a negative PID.
#
# `$!` is the *subshell*, not the server inside it: uvicorn --reload runs a
# reload supervisor plus a worker, and `pnpm dev:web` runs Vite as its own child.
# Killing the bare PID leaves those alive, still holding 8000/5173, so the next
# run silently steps to 8001/5174 and you debug a stale server. Ctrl+C happened
# to work anyway — the terminal signals the whole foreground group — but any
# other exit path (a `set -e` abort, SIGTERM) orphaned both servers.
set -m

API_PID=""; WEB_PID=""
stop_group() { [ -n "$1" ] && kill -- -"$1" 2>/dev/null || true; }
cleanup() { stop_group "$API_PID"; stop_group "$WEB_PID"; }
trap cleanup EXIT INT TERM

# Force the external API off regardless of what is exported in your shell.
export PLANARUS_EXTERNAL_API_ENABLED=false
# --reload-dir app: watch only source, not the thousands of files in .venv.
(cd "$ROOT/apps/api" \
  && .venv/bin/alembic upgrade head \
  && .venv/bin/uvicorn app.main:app --reload --reload-dir app --port "$API_PORT") &
API_PID=$!

# vite.config.ts reads both: VITE_PORT also flips strictPort on, so Vite cannot
# silently drift to another port and invalidate the URL we open below.
export VITE_PORT="$WEB_PORT"
export VITE_API_TARGET="http://localhost:$API_PORT"
(cd "$ROOT" && pnpm dev:web) &
WEB_PID=$!

# --- wait for both to actually answer ----------------------------------------
# /health only returns 2xx once migrations ran and the app imported, so this
# also waits out "alembic upgrade head" on a first boot.
wait_for() {
  local url=$1 name=$2 tries=$3
  for _ in $(seq 1 "$tries"); do
    curl -sf -o /dev/null --max-time 2 "$url" && { echo "  $name is up   $url"; return 0; }
    sleep 1
  done
  echo "[WARN] $name not answering at $url — check its output above."
}
wait_for "http://localhost:$API_PORT/health" "API" 120
wait_for "http://localhost:$WEB_PORT" "Web" 60

# open: macOS. xdg-open: most Linux desktops. Neither existing is not an error.
( command -v open >/dev/null 2>&1 && open "http://localhost:$WEB_PORT" ) \
  || ( command -v xdg-open >/dev/null 2>&1 && xdg-open "http://localhost:$WEB_PORT" ) \
  || echo "  Open http://localhost:$WEB_PORT in your browser."

echo
echo "  UI:        http://localhost:$WEB_PORT"
echo "  API docs:  http://localhost:$API_PORT/docs"
echo "Ctrl+C here stops both servers."
wait
