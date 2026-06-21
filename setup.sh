#!/usr/bin/env bash
# setup.sh — one-shot local setup for Daily Scholar.
#
# Brings a fresh clone to a runnable state with SQLite + local filesystem,
# no Railway / Cloudflare / B2 dependency. Safe to re-run; every step is
# idempotent.
#
# Usage:
#   ./setup.sh                # full setup
#   ./setup.sh --no-frontend  # skip the npm install step (backend-only)
#
# Requires: Python 3.10+, Node 18+ (unless --no-frontend), git.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKIP_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --no-frontend) SKIP_FRONTEND=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0 ;;
  esac
done

# ---- python ----------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 not found. Install Python 3.10+ and retry." >&2; exit 1
fi
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "→ Python $PYV detected."

if [[ ! -d "$REPO_ROOT/venv" ]]; then
  echo "→ Creating venv at $REPO_ROOT/venv ..."
  python3 -m venv "$REPO_ROOT/venv"
else
  echo "→ venv already exists, reusing."
fi

# shellcheck source=/dev/null
source "$REPO_ROOT/venv/bin/activate"
echo "→ Installing Python dependencies (this may take a minute on first run)..."
pip install --quiet --upgrade pip
pip install --quiet -r "$REPO_ROOT/requirements.txt"

# ---- .env ------------------------------------------------------------------
if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "→ Creating .env from .env.example ..."
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  echo "  ⚠ Edit .env to set ANTHROPIC_API_KEY before running ./start.sh"
else
  echo "→ .env already exists, leaving alone."
fi

# ---- data dir --------------------------------------------------------------
mkdir -p "$REPO_ROOT/data" "$REPO_ROOT/uploads"

# ---- migrations (no-op if up to date; idempotent) -------------------------
echo "→ Applying database migrations ..."
(cd "$REPO_ROOT" && alembic upgrade head >/dev/null 2>&1) || {
  echo "  ⚠ Alembic returned non-zero — the backend will retry on first start (this is usually fine)."
}

# ---- VAPID keys hint (optional; web push) ---------------------------------
if ! grep -q '^VAPID_PUBLIC_KEY=..' "$REPO_ROOT/.env" 2>/dev/null; then
  echo "  ℹ Web Push not configured. To enable, run:"
  echo "    python scripts/generate_vapid_keys.py"
  echo "    then paste the three printed lines into .env"
fi

# ---- frontend --------------------------------------------------------------
if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
  if ! command -v node >/dev/null 2>&1; then
    echo "✗ node not found. Install Node 18+ or rerun with --no-frontend." >&2; exit 1
  fi
  echo "→ Installing frontend dependencies ..."
  (cd "$REPO_ROOT/frontend" && npm install --silent)
else
  echo "→ Skipping frontend (--no-frontend)."
fi

echo ""
echo "✅ Setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit .env to add your ANTHROPIC_API_KEY"
echo "  2. Run ./start.sh to launch the backend + frontend"
echo "  3. Open http://localhost:3000"
