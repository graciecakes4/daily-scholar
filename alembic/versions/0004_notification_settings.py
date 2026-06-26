"""add notification_settings JSON column to user_settings

Adds a single JSON column on `user_settings` that holds per-user notification
preferences (timezone + per-type cron/enabled). One column lets the registry
grow new notification types without further migrations.

Idempotent: skips the add if a prior dev session ran Base.metadata.create_all
before alembic was caught up.

Revision ID: 0004_notification_settings
Revises: 0003_auth_ready_user_id
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_notification_settings"
down_revision: Union[str, None] = "0003_auth_ready_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("user_settings", "notification_settings"):
        # server_default '{}' so existing rows backfill to an empty dict
        # rather than NULL, which the service layer would otherwise have
        # to special-case on every read.
        op.add_column(
            "user_settings",
            sa.Column(
                "notification_settings",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    if _has_column("user_settings", "notification_settings"):
        op.drop_column("user_settings", "notification_settings")
