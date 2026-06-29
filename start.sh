#!/usr/bin/env bash
# start.sh — launch the Daily Scholar local stack (backend + frontend).
#
# Starts uvicorn + Next.js dev server in the background, polls /health
# until the backend is reachable (or times out), then prints URLs and
# keeps both processes running until you Ctrl-C.
#
# Usage:
#   ./start.sh                 # start both, wait for health, attach
#   ./start.sh --backend-only  # backend only (no frontend)
#   ./start.sh --no-wait       # don't poll /health; useful in CI smoke tests
#
# Requires: ./setup.sh has been run at least once.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ONLY=0
WAIT_FOR_HEALTH=1
HEALTH_TIMEOUT_SECONDS=300
HEALTH_URL="http://127.0.0.1:8000/health"
FRONTEND_URL="http://127.0.0.1:3000"

for arg in "$@"; do
  case "$arg" in
    --backend-only) BACKEND_ONLY=1 ;;
    --no-wait) WAIT_FOR_HEALTH=0 ;;
    -h|--help)
      sed -n '2,14p' "$0"; exit 0 ;;
  esac
done

# ---- preflight -------------------------------------------------------------
if [[ ! -d "$REPO_ROOT/venv" ]]; then
  echo "✗ venv not found at $REPO_ROOT/venv. Run ./setup.sh first." >&2; exit 1
fi
if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "✗ .env not found. Run ./setup.sh first." >&2; exit 1
fi
if [[ "$BACKEND_ONLY" -eq 0 && ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
  echo "✗ frontend/node_modules missing. Run ./setup.sh (without --no-frontend)." >&2; exit 1
fi

# shellcheck source=/dev/null
source "$REPO_ROOT/venv/bin/activate"

# ---- pid tracking ----------------------------------------------------------
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "→ Shutting down ..."
  # uvicorn --reload and `npm run dev` each fork a worker child; killing only
  # the parent leaves the child as a zombie that holds the DB lock (sqlite)
  # and the dev server port. Kill descendants first, escalate to SIGKILL if
  # they don't exit cleanly within 5s.
  for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      pkill -TERM -P "$pid" 2>/dev/null || true
      kill -TERM "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
      done
      pkill -KILL -P "$pid" 2>/dev/null || true
      kill -KILL "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  echo "✓ Done."
}
trap cleanup INT TERM EXIT

# ---- backend ---------------------------------------------------------------
# --timeout-keep-alive 75 matches Node's outbound HTTP agent default; without
# this, Next.js's /api/* proxy reuses sockets uvicorn has already closed (5s
# default) and intermittently fails with "socket hang up" / ECONNRESET. Keep
# in sync with the same flag in ../Dockerfile.
echo "→ Starting backend (uvicorn) on :8000 ..."
(cd "$REPO_ROOT" && uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --timeout-keep-alive 75) &
BACKEND_PID=$!

# ---- health check ----------------------------------------------------------
if [[ "$WAIT_FOR_HEALTH" -eq 1 ]]; then
  echo "→ Waiting for backend health (timeout ${HEALTH_TIMEOUT_SECONDS}s) ..."
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT_SECONDS ))
  healthy=0
  while [[ $(date +%s) -lt $deadline ]]; do
    if curl -fsS -m 2 "$HEALTH_URL" >/dev/null 2>&1; then
      healthy=1; break
    fi
    sleep 1
  done
  if [[ $healthy -eq 0 ]]; then
    echo "✗ Backend didn't become healthy within ${HEALTH_TIMEOUT_SECONDS}s." >&2
    echo "  Check the uvicorn output above for errors (often a missing .env value)." >&2
    exit 1
  fi
  echo "  ✓ Backend healthy."
fi

# ---- frontend --------------------------------------------------------------
if [[ "$BACKEND_ONLY" -eq 0 ]]; then
  echo "→ Starting frontend (Next.js dev) on :3000 ..."
  (cd "$REPO_ROOT/frontend" && npm run dev --silent) &
  FRONTEND_PID=$!
fi

# ---- ready -----------------------------------------------------------------
echo ""
echo "✅ Daily Scholar is running:"
echo "   - App:        $FRONTEND_URL"
echo "   - API:        http://127.0.0.1:8000"
echo "   - API docs:   http://127.0.0.1:8000/docs"
echo "   - Health:     $HEALTH_URL"
echo ""
echo "Press Ctrl-C to stop."

# wait for either to exit (or for the user to Ctrl-C)
wait
