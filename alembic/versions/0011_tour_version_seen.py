"""add users.tour_state for per-tour versioned UI tours

JSON column holding `{tour_id: highest_version_seen}`. Frontend hardcodes
a TOUR_VERSION per tour and gates "show me" on `stored < current`.
Adding a new tour later is just a new key — no migration.

Tour ids in use as of this migration:
  - "dashboard"  (frontend/components/DashboardTour.tsx)
  - "scope"      (frontend/components/ScopeTour.tsx)
  - "topics"     (frontend/components/TopicsTour.tsx)

Backfill: existing rows default to '{}' so every user sees the current
version of every tour once on next visit to the respective page.
If you'd rather suppress the post-deploy replay, run:
    UPDATE users SET tour_state = '{"dashboard": 1, "scope": 1, "topics": 1}';

Note on filename vs purpose: this file's name says `tour_version_seen`
for git-history reasons (the original draft used an INT column called
`tour_version_seen`; reworked to JSON before the migration was ever
applied anywhere). The revision id stays `0011_tour_version_seen` so
the alembic linear history doesn't need editing.

Idempotent guard so re-running on a half-applied DB is safe.

Revision ID: 0011_tour_version_seen
Revises: 0010_admin_audit_log
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_tour_version_seen"
down_revision: Union[str, None] = "0010_admin_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if _has_column("users", "tour_state"):
        return
    op.add_column(
        "users",
        sa.Column(
            "tour_state",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    if _has_column("users", "tour_state"):
        op.drop_column("users", "tour_state")
