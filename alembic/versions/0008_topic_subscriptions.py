"""add topic_subscriptions table (Phase D subscribe model)

Lets users subscribe to other users' public topics so those topics
appear in their scope (paper discovery, daily content, quiz) without
being copied. Updates from the owner propagate to subscribers
automatically.

  * UNIQUE(user_id, topic_id) so a user can only subscribe once.
  * topic_id FK → topics.id; the API hard-delete path explicitly
    cleans up subscriptions before dropping the parent row (SQLite's
    FK CASCADE is opt-in via PRAGMA and we don't want to depend on it).

Idempotent guards so re-running on a half-applied DB is safe.

Revision ID: 0008_topic_subscriptions
Revises: 0007_topic_ownership
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_topic_subscriptions"
down_revision: Union[str, None] = "0007_topic_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("topic_subscriptions"):
        return

    op.create_table(
        "topic_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("topic_id", sa.String(length=100), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "topic_id",
            name="uq_topic_subscriptions_user_topic",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["topics.id"],
            name="fk_topic_subscriptions_topic_id",
        ),
    )
    op.create_index(
        op.f("ix_topic_subscriptions_user_id"),
        "topic_subscriptions", ["user_id"],
    )
    op.create_index(
        op.f("ix_topic_subscriptions_topic_id"),
        "topic_subscriptions", ["topic_id"],
    )
    op.create_index(
        "idx_topic_subscriptions_user",
        "topic_subscriptions", ["user_id"],
    )


def downgrade() -> None:
    if _has_table("topic_subscriptions"):
        op.drop_index("idx_topic_subscriptions_user", table_name="topic_subscriptions")
        op.drop_index(op.f("ix_topic_subscriptions_topic_id"), table_name="topic_subscriptions")
        op.drop_index(op.f("ix_topic_subscriptions_user_id"), table_name="topic_subscriptions")
        op.drop_table("topic_subscriptions")
