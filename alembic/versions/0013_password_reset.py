"""add password_reset_tokens table (li3b)

Self-serve forgot-password flow. POST /auth/forgot-password verifies the
requester by email (SMTP-delivered link, see backend/services/email.py)
rather than a knowledge-factor check, so there's only one table:

  * `password_reset_tokens` - single-use, short-lived token minted after
                               POST /auth/forgot-password confirms the
                               email belongs to an active account.
                               Consumed by POST /auth/reset-password.

Idempotent guards so re-running on a half-applied DB is safe.

Revision ID: 0013_password_reset
Revises: 0012_scopes
Create Date: 2026-07-04

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_password_reset"
down_revision: Union[str, None] = "0012_scopes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("password_reset_tokens"):
        return

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_password_reset_tokens_user_id",
        ),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token"),
        "password_reset_tokens", ["token"], unique=True,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"),
        "password_reset_tokens", ["user_id"],
    )


def downgrade() -> None:
    if _has_table("password_reset_tokens"):
        op.drop_index(
            op.f("ix_password_reset_tokens_user_id"),
            table_name="password_reset_tokens",
        )
        op.drop_index(
            op.f("ix_password_reset_tokens_token"),
            table_name="password_reset_tokens",
        )
        op.drop_table("password_reset_tokens")
