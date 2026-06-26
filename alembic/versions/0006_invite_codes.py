"""add invite_codes table (Phase B signup gate)

Issues an invitation-code gate in front of POST /auth/signup. Admin
generates a code in the admin UI; the user submits it during signup;
backend validates + redeems atomically. Multi-use codes supported via
`max_uses` (default 1 = single-use).

Idempotent guards (`_has_table`) so re-running on a half-applied DB
is safe.

Revision ID: 0006_invite_codes
Revises: 0005_users_and_sessions
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_invite_codes"
down_revision: Union[str, None] = "0005_users_and_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("invite_codes"):
        return

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("redeemed_at", sa.DateTime(), nullable=True),
        sa.Column("last_redeemed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_invite_codes_code"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], name="fk_invite_codes_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["last_redeemed_by_user_id"], ["users.id"],
            name="fk_invite_codes_last_redeemed_by",
        ),
    )
    op.create_index(op.f("ix_invite_codes_code"), "invite_codes", ["code"])


def downgrade() -> None:
    if _has_table("invite_codes"):
        op.drop_index(op.f("ix_invite_codes_code"), table_name="invite_codes")
        op.drop_table("invite_codes")
