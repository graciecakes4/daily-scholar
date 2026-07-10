"""add last_seen_at column to sessions (session-list UI)

Adds a nullable `last_seen_at` timestamp to `sessions`, written on a
throttled basis (see SESSION_LAST_SEEN_THROTTLE in
backend/services/auth_sessions.py) whenever a valid session token is
resolved, so the /settings/account/sessions UI can show "active N min
ago" per device. NULL for rows minted before this migration or that
have never been re-validated since — the UI falls back to created_at
in that case.

Idempotent: skips the add if a prior dev session already applied it via
Base.metadata.create_all.

Revision ID: 0015_session_last_seen
Revises: 0014_display_settings
Create Date: 2026-07-10

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_session_last_seen"
down_revision: Union[str, None] = "0014_display_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("sessions", "last_seen_at"):
        op.add_column(
            "sessions",
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("sessions", "last_seen_at"):
        op.drop_column("sessions", "last_seen_at")
