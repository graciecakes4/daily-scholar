"""add topics, user_settings, push_subscriptions

Introduces the unified Topic model (replaces config/interests.yaml +
config/courses.yaml), per-user settings (scope mode + selected topic ids),
and push subscription scaffolding for Phase 1 Web Push.

Revision ID: 0002_topics_user_settings_push
Revises: 0001_baseline
Create Date: 2026-06-15

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_topics_user_settings_push"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("stream", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("arxiv_categories", sa.JSON(), nullable=False),
        sa.Column("recency_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("min_relevance", sa.Float(), nullable=False, server_default="0.18"),
        sa.Column("key_concepts", sa.JSON(), nullable=False),
        sa.Column("learning_objectives", sa.JSON(), nullable=False),
        sa.Column("resources", sa.JSON(), nullable=False),
        sa.Column("quiz_difficulty", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("prerequisites", sa.JSON(), nullable=False),
        sa.Column("created_via", sa.String(length=20), nullable=False, server_default="yaml"),
        sa.Column("source_yaml_present", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_topic_active_stream", "topics", ["active", "stream"])
    op.create_index(op.f("ix_topics_active"), "topics", ["active"])
    op.create_index(op.f("ix_topics_stream"), "topics", ["stream"])

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False, server_default="__local__"),
        sa.Column("scope_mode", sa.String(length=20), nullable=False, server_default="all"),
        sa.Column("scope_topic_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_settings_user_id"), "user_settings", ["user_id"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False, server_default="__local__"),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=200), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index(op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
    op.drop_index(op.f("ix_user_settings_user_id"), table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_index(op.f("ix_topics_stream"), table_name="topics")
    op.drop_index(op.f("ix_topics_active"), table_name="topics")
    op.drop_index("idx_topic_active_stream", table_name="topics")
    op.drop_table("topics")
