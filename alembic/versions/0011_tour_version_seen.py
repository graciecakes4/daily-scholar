"""add users.tour_version_seen for versioned dashboard tour

Tracks the highest tour version the user has seen so we can re-trigger
the tour when we bump the frontend's TOUR_VERSION constant (added/
rewritten steps). Cross-device sync — replaces the localStorage flag
we shipped with the original tour.

Backfill: existing rows default to 0 so they see the current tour
version once on next dashboard visit (consistent with the
localStorage-unset behavior we already had). If you'd rather backfill
to the current TOUR_VERSION post-deploy, run:
    UPDATE users SET tour_version_seen = 1;

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
    if _has_column("users", "tour_version_seen"):
        return
    op.add_column(
        "users",
        sa.Column(
            "tour_version_seen",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    if _has_column("users", "tour_version_seen"):
        op.drop_column("users", "tour_version_seen")
