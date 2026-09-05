"""add track + prerequisite_only columns to topics (track bifurcation)

Adds two nullable-safe columns to `topics`:

  - `track`             : research track slug ("praxis", "astro", ...).
                          NULL means untracked — the topic still scores
                          papers but counts toward no track's quota.
  - `prerequisite_only` : foundations topics that should inform review
                          and quiz generation without ever consuming a
                          daily paper slot.

Both exist so paper discovery can aggregate search keywords and arXiv
categories PER TRACK instead of globally. The global aggregation
truncated to the top 5 keywords across all topics sorted by weight
descending, which let the two highest-weight topics supply every search
term and starved the other track completely.

Backfill: existing rows get track=NULL / prerequisite_only=0, which is
inert — discovery falls back to its previous single-pool behaviour when
no topic in scope declares a track. The YAML bootstrap assigns real
values on the next boot.

Idempotent: skips each add if a prior dev session already applied it via
Base.metadata.create_all.

Revision ID: 0016_topic_track
Revises: 0015_session_last_seen
Create Date: 2026-09-04

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_topic_track"
down_revision: Union[str, None] = "0015_session_last_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    if not _has_column("topics", "track"):
        op.add_column("topics", sa.Column("track", sa.String(50), nullable=True))
    if not _has_index("topics", "ix_topics_track"):
        op.create_index("ix_topics_track", "topics", ["track"])

    if not _has_column("topics", "prerequisite_only"):
        # server_default so the NOT NULL add works against existing rows;
        # the model-level default takes over for new inserts.
        op.add_column(
            "topics",
            sa.Column(
                "prerequisite_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    if _has_index("topics", "ix_topics_track"):
        op.drop_index("ix_topics_track", table_name="topics")
    if _has_column("topics", "track"):
        op.drop_column("topics", "track")
    if _has_column("topics", "prerequisite_only"):
        op.drop_column("topics", "prerequisite_only")
