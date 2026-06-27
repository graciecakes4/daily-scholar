#!/usr/bin/env python3
"""
Seed the system-owned public starter scopes manually.

Normally this runs automatically on backend startup (see
backend/main.py `lifespan`), so you only need this CLI when:

  * you've just added a new starter to backend/services/starter_scopes
    .STARTER_SCOPES and want to materialize it without restarting, or
  * you're debugging the seeding logic against a specific DB.

Usage:
    python scripts/seed_starter_scopes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.services.starter_scopes import seed_starter_scopes  # noqa: E402


def main() -> int:
    summary = seed_starter_scopes()
    print(
        f"starter scopes: "
        f"{summary['inserted']} inserted, "
        f"{summary['refreshed']} refreshed, "
        f"{summary['unchanged']} unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
