#!/usr/bin/env python3
"""
Materialize legacy per-user scope settings into the new scope library.

Background: prior to the scope-library phase, each user had exactly one
"scope" stored as two columns on UserSettings (`scope_mode` and
`scope_topic_ids`). With the scope-library phase, scopes become
first-class rows in the `scopes` table, a user can own many of them,
and UserSettings.active_scope_id points at the one currently driving
discovery/review/quizzes.

This script walks every UserSettings row and, for each user that:
  - has a real row in the `users` table (so we can set owner_user_id), and
  - does not yet have an active_scope_id

creates a new private Scope named "My scope" carrying their existing
scope_mode + scope_topic_ids, and points active_scope_id at it.

Users without a matching `users` row (the `__local__` sentinel and any
other pre-auth handles) are skipped. Those users will land on the
onboarding picker the next time they sign in with a real account.

By default this is a DRY RUN — it prints what would change and exits.
Pass --apply to commit.

Usage:
    # see what would change
    python scripts/migrate_to_scope_library.py

    # actually do it
    python scripts/migrate_to_scope_library.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# allow running from repo root without installing as a package
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.database import (  # noqa: E402
    Scope,
    SCOPE_VISIBILITY_PRIVATE,
    User,
    UserSettings,
    get_session,
)


# the name we stamp on every materialized scope so users can recognize
# their pre-migration setting in the library
DEFAULT_SCOPE_NAME = "My scope"
DEFAULT_SCOPE_DESCRIPTION = (
    "Auto-created from your previous scope setting. "
    "Rename, edit, or share whenever you like."
)


def migrate(*, apply: bool) -> int:
    """
    Returns 0 on success, non-zero on validation failure.
    Side effects: prints per-user summary and either commits or rolls back.
    """
    session = get_session()
    try:
        all_settings = session.query(UserSettings).all()

        # bucket each settings row so the summary is informative
        already_migrated: list[str] = []
        skipped_no_user: list[str] = []
        to_migrate: list[tuple[UserSettings, User]] = []

        # build a user_id -> User lookup once
        user_by_handle = {u.user_id: u for u in session.query(User).all()}

        for s in all_settings:
            if s.active_scope_id is not None:
                already_migrated.append(s.user_id)
                continue
            user = user_by_handle.get(s.user_id)
            if user is None:
                skipped_no_user.append(s.user_id)
                continue
            to_migrate.append((s, user))

        # report
        print()
        print(f"scope-library migration  (apply={apply})")
        print(f"{'category':<30} {'count':>8}")
        print("-" * 40)
        print(f"{'already migrated':<30} {len(already_migrated):>8}")
        print(f"{'to migrate':<30} {len(to_migrate):>8}")
        print(f"{'skipped (no users row)':<30} {len(skipped_no_user):>8}")
        print("-" * 40)

        if skipped_no_user:
            preview = ", ".join(repr(u) for u in skipped_no_user[:5])
            more = "" if len(skipped_no_user) <= 5 else f" (+{len(skipped_no_user) - 5} more)"
            print(f"  skipped handles: {preview}{more}")
            print("  these users will see the onboarding picker on next sign-in.")

        if not to_migrate:
            print("\nnothing to do.")
            return 0

        # show a preview of what each migration will produce
        print("\nplanned scopes:")
        print(f"  {'user_id':<30} {'mode':<6} {'topic count':>11}")
        for s, _ in to_migrate[:20]:
            n = len(list(s.scope_topic_ids or []))
            print(f"  {s.user_id:<30} {s.scope_mode:<6} {n:>11}")
        if len(to_migrate) > 20:
            print(f"  ... (+{len(to_migrate) - 20} more)")

        if not apply:
            print("\ndry-run — no changes written. re-run with --apply to commit.")
            return 0

        # apply inside one transaction so a mid-flight failure rolls back
        for s, user in to_migrate:
            scope = Scope(
                name=DEFAULT_SCOPE_NAME,
                description=DEFAULT_SCOPE_DESCRIPTION,
                owner_user_id=user.id,
                visibility=SCOPE_VISIBILITY_PRIVATE,
                scope_mode=s.scope_mode,
                # copy the list — don't share the reference with the legacy column
                scope_topic_ids=list(s.scope_topic_ids or []),
                forked_from_scope_id=None,
            )
            session.add(scope)
            # flush to assign the new scope.id before we point at it
            session.flush()
            s.active_scope_id = scope.id

        session.commit()
        print(f"\ncommitted: created {len(to_migrate)} scope row(s) and "
              f"set active_scope_id for each.")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"\nerror: migration failed and was rolled back: {exc}")
        return 1
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize legacy UserSettings.scope_* into Scope rows.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually commit the migration (default is dry-run).",
    )
    args = parser.parse_args()
    return migrate(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
