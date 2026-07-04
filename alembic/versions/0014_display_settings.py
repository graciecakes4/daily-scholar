"""add display_settings JSON column to user_settings (Phase 5 / fd3 foundation)

Adds a single JSON column on `user_settings` that holds per-user display
preferences (theme + font size), mirroring the notification_settings
column added in 0004. One column lets the theme/font-size registry grow
without further migrations.

Idempotent: skips the add if a prior dev session already applied it via
Base.metadata.create_all.

Revision ID: 0014_display_settings
Revises: 0013_password_reset
Create Date: 2026-07-04

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_display_settings"
down_revision: Union[str, None] = "0013_password_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("user_settings", "display_settings"):
        # server_default '{}' so existing rows backfill to an empty dict
        # rather than NULL — the service layer backfills registry defaults
        # on read, same pattern as notification_settings.
        op.add_column(
            "user_settings",
            sa.Column(
                "display_settings",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    if _has_column("user_settings", "display_settings"):
        op.drop_column("user_settings", "display_settings")
