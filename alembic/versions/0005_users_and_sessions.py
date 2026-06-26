"""add users + sessions tables (Phase A in-app auth foundation)

Introduces the `users` table (real human accounts with email + password)
and `sessions` table (opaque server-side session tokens).

Notes:
  * The existing 9 user-scoped tables continue to use `user_id VARCHAR(100)`
    (the email or a custom handle). No schema changes to those tables —
    the new `users.user_id` column matches the string they already store,
    so nothing has to be backfilled or re-keyed.
  * The `__local__` sentinel is NOT inserted as a real user row. It stays
    as the bottom of the auth fallback chain in `backend/auth.py` for
    solo-mode local dev.
  * Idempotent guards (`_has_table`) so re-running on a half-applied DB
    is safe.

Revision ID: 0005_users_and_sessions
Revises: 0004_notification_settings
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_users_and_sessions"
down_revision: Union[str, None] = "0004_notification_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("email", sa.String(length=200), nullable=False),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("password_hash", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email", name="uq_users_email"),
            sa.UniqueConstraint("user_id", name="uq_users_user_id"),
            sa.ForeignKeyConstraint(
                ["approved_by_user_id"], ["users.id"], name="fk_users_approved_by_user_id"
            ),
        )
        op.create_index(op.f("ix_users_email"), "users", ["email"])
        op.create_index(op.f("ix_users_user_id"), "users", ["user_id"])

    if not _has_table("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token", name="uq_sessions_token"),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], name="fk_sessions_user_id"
            ),
        )
        op.create_index(op.f("ix_sessions_token"), "sessions", ["token"])
        op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])


def downgrade() -> None:
    if _has_table("sessions"):
        op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
        op.drop_index(op.f("ix_sessions_token"), table_name="sessions")
        op.drop_table("sessions")
    if _has_table("users"):
        op.drop_index(op.f("ix_users_user_id"), table_name="users")
        op.drop_index(op.f("ix_users_email"), table_name="users")
        op.drop_table("users")
