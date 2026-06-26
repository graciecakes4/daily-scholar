"""add owner_user_id + visibility to topics (Phase C ownership)

Adds two nullable-then-not-null columns to `topics`:

  * owner_user_id  → FK to users.id; NULL means "system topic" (visible
    to everyone, only admins can edit). Existing yaml-bootstrapped rows
    backfill to NULL so they keep their global semantics.
  * visibility     → "private" | "public" (string column for forward
    compat). Existing rows (system topics) backfill to "public" so
    legacy global access is preserved; new user-created rows default
    to "private".

Idempotent guards so re-running on a half-applied DB is safe.

Revision ID: 0007_topic_ownership
Revises: 0006_invite_codes
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_topic_ownership"
down_revision: Union[str, None] = "0006_invite_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, index_name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return index_name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    # owner_user_id — nullable FK; FK constraint is dialect-sensitive on
    # SQLite (no real enforcement) so we add the column with the FK spec
    # and rely on Postgres to enforce. SQLite stores the column as INTEGER.
    if not _has_column("topics", "owner_user_id"):
        if op.get_bind().dialect.name == "sqlite":
            # SQLite can't add a FK constraint via ALTER TABLE — add the
            # column without the FK; the model still declares it so it
            # gets created with the FK on fresh installs via metadata.
            op.add_column(
                "topics",
                sa.Column("owner_user_id", sa.Integer(), nullable=True),
            )
        else:
            op.add_column(
                "topics",
                sa.Column(
                    "owner_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", name="fk_topics_owner_user_id"),
                    nullable=True,
                ),
            )

    if not _has_index("topics", "ix_topics_owner_user_id"):
        op.create_index("ix_topics_owner_user_id", "topics", ["owner_user_id"])

    # visibility — string column; existing rows backfill to "public" so
    # the previous "everyone sees everything" behavior is preserved.
    if not _has_column("topics", "visibility"):
        op.add_column(
            "topics",
            sa.Column(
                "visibility",
                sa.String(length=20),
                nullable=False,
                server_default="public",     # backfills existing rows
            ),
        )
        # change the default for future inserts to "private" — user-created
        # topics start private; admins explicitly flip to public.
        # SQLite doesn't support ALTER COLUMN SET DEFAULT; Postgres does.
        if op.get_bind().dialect.name != "sqlite":
            op.alter_column(
                "topics", "visibility",
                server_default="private",
            )

    if not _has_index("topics", "ix_topics_visibility"):
        op.create_index("ix_topics_visibility", "topics", ["visibility"])
    if not _has_index("topics", "idx_topic_owner_visibility"):
        op.create_index(
            "idx_topic_owner_visibility", "topics",
            ["owner_user_id", "visibility"],
        )


def downgrade() -> None:
    if _has_index("topics", "idx_topic_owner_visibility"):
        op.drop_index("idx_topic_owner_visibility", table_name="topics")
    if _has_index("topics", "ix_topics_visibility"):
        op.drop_index("ix_topics_visibility", table_name="topics")
    if _has_index("topics", "ix_topics_owner_user_id"):
        op.drop_index("ix_topics_owner_user_id", table_name="topics")
    if _has_column("topics", "visibility"):
        op.drop_column("topics", "visibility")
    if _has_column("topics", "owner_user_id"):
        op.drop_column("topics", "owner_user_id")
