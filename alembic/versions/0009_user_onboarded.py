"""add users.onboarded flag (Phase E onboarding wizard)

False for fresh signups so the layout redirects them to /onboarding;
true for everyone who existed before this migration (they were created
when there was no wizard, so they don't need one).

Idempotent guards so re-running on a half-applied DB is safe.

Revision ID: 0009_user_onboarded
Revises: 0008_topic_subscriptions
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_user_onboarded"
down_revision: Union[str, None] = "0008_topic_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if _has_column("users", "onboarded"):
        return

    # add the column with server_default true so existing rows backfill
    # to onboarded (they're approved users who shouldn't see a wizard).
    op.add_column(
        "users",
        sa.Column(
            "onboarded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # change the default for future inserts to false — fresh signups
    # need to be unonboarded so the wizard catches them on first login.
    # SQLite doesn't support ALTER COLUMN SET DEFAULT; the application
    # layer compensates by passing onboarded=False on User() construction.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("users", "onboarded", server_default=sa.false())


def downgrade() -> None:
    if _has_column("users", "onboarded"):
        op.drop_column("users", "onboarded")
