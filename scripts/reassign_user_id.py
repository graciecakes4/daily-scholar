#!/usr/bin/env python3
"""
Reassign every user-scoped row from one user_id to another.

Use case: you've been running Daily Scholar in solo mode (`user_id='__local__'`)
and now Cloudflare Access is on, so your real identity becomes
`grace@example.com`. This script moves every row across all nine user-scoped
tables in one transaction so your archives, history, stats, push subs, and
scope settings follow you to the new identity.

Tables touched (the nine user-scoped tables introduced with the auth-identity schema):

  seen_papers
  archived_papers
  archived_quizzes
  archived_topic_reviews
  paper_pdfs
  daily_content_cache
  user_stats
  push_subscriptions
  user_settings

By default this is a DRY RUN — it prints the per-table counts that *would*
move and exits. Pass --apply to actually update. Pass --hard-overwrite to
allow the move even if the target already has rows in any of these tables
(default refuses to merge to avoid clobbering existing per-user data).

Usage:
    # see what would move
    python scripts/reassign_user_id.py --from __local__ --to grace@example.com

    # actually do it
    python scripts/reassign_user_id.py --from __local__ --to grace@example.com --apply

    # allow merge into an identity that already has rows
    python scripts/reassign_user_id.py --from __local__ --to grace@example.com --apply --hard-overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# allow running from repo root without installing as a package
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import update

from backend.database import (  # noqa: E402
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    DailyContentCache,
    PaperPDF,
    PushSubscription,
    SeenPaper,
    UserSettings,
    UserStats,
    get_session,
)

# every model that carries a user_id column per Phase 4 schema track
USER_SCOPED_MODELS = [
    SeenPaper,
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    PaperPDF,
    DailyContentCache,
    UserStats,
    PushSubscription,
    UserSettings,
]


def _count_for_user(session, model, user_id: str) -> int:
    return session.query(model).filter(model.user_id == user_id).count()


def _table_name(model) -> str:
    return getattr(model, "__tablename__", model.__name__)


def reassign(
    source_user_id: str,
    target_user_id: str,
    *,
    apply: bool,
    hard_overwrite: bool,
) -> int:
    """
    Returns 0 on success, non-zero on validation failure.
    Side effects: prints per-table counts and either commits or rolls back.
    """
    if source_user_id == target_user_id:
        print(f"error: --from and --to are identical ({source_user_id!r}); nothing to do")
        return 2

    session = get_session()
    try:
        # phase 1: report what we'd move and pre-flight check the target
        moves: list[tuple[str, int]] = []
        target_collisions: list[tuple[str, int]] = []
        for model in USER_SCOPED_MODELS:
            src_count = _count_for_user(session, model, source_user_id)
            tgt_count = _count_for_user(session, model, target_user_id)
            moves.append((_table_name(model), src_count))
            if tgt_count > 0:
                target_collisions.append((_table_name(model), tgt_count))

        total_to_move = sum(c for _, c in moves)
        print(f"\nreassign: {source_user_id!r} -> {target_user_id!r}")
        print(f"{'table':<25} {'source rows':>12} {'target rows':>12}")
        print("-" * 51)
        for (table, src), (_, tgt) in zip(
            moves,
            [(t, _count_for_user(session, m, target_user_id))
             for t, m in zip([_table_name(m) for m in USER_SCOPED_MODELS], USER_SCOPED_MODELS)],
        ):
            print(f"{table:<25} {src:>12} {tgt:>12}")
        print("-" * 51)
        print(f"{'TOTAL TO MOVE':<25} {total_to_move:>12}")

        if total_to_move == 0:
            print(f"\nnothing to do — no rows owned by {source_user_id!r}")
            return 0

        if target_collisions and not hard_overwrite:
            print(
                f"\nrefusing to merge: target {target_user_id!r} already owns rows in "
                f"{len(target_collisions)} table(s): "
                f"{', '.join(f'{t}({c})' for t, c in target_collisions)}"
            )
            print("re-run with --hard-overwrite if you intentionally want to merge identities.")
            return 3

        if not apply:
            print("\ndry-run — no changes written. re-run with --apply to commit.")
            return 0

        # phase 2: apply the update inside one transaction
        # NOTE: UserSettings has a UNIQUE(user_id) constraint, so a merge that
        # has rows on both sides would violate it even with --hard-overwrite.
        # We delete the target's UserSettings row first so the source's wins.
        # Same logic for UserStats (also UNIQUE(user_id)).
        if hard_overwrite:
            for unique_model in (UserSettings, UserStats):
                tgt_row = session.query(unique_model).filter(
                    unique_model.user_id == target_user_id
                ).first()
                src_row = session.query(unique_model).filter(
                    unique_model.user_id == source_user_id
                ).first()
                if tgt_row is not None and src_row is not None:
                    print(
                        f"  hard-overwrite: deleting target {_table_name(unique_model)} row "
                        f"so source wins"
                    )
                    session.delete(tgt_row)
            session.flush()

        total_moved = 0
        for model in USER_SCOPED_MODELS:
            result = session.execute(
                update(model)
                .where(model.user_id == source_user_id)
                .values(user_id=target_user_id)
            )
            total_moved += result.rowcount or 0

        session.commit()
        print(f"\n✅ moved {total_moved} row(s) total.")
        return 0
    except Exception as e:  # noqa: BLE001
        session.rollback()
        print(f"\n❌ failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--from", dest="source", required=True,
        help="source user_id to move FROM (often '__local__')",
    )
    parser.add_argument(
        "--to", dest="target", required=True,
        help="target user_id to move TO (e.g., your Cloudflare Access email)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually write the changes; without this it's a dry run",
    )
    parser.add_argument(
        "--hard-overwrite", action="store_true",
        help="allow merging into a target that already owns rows; user_settings / user_stats target rows are dropped so source wins",
    )
    args = parser.parse_args()
    return reassign(
        args.source, args.target, apply=args.apply, hard_overwrite=args.hard_overwrite,
    )


if __name__ == "__main__":
    raise SystemExit(main())
