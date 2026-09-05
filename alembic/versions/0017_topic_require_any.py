"""add require_any domain gate to topics

Adds a JSON `require_any` list to `topics`. When non-empty, a paper must
contain at least one of these terms before any of the topic's keywords are
scored at all.

Why: relevance is `matched_keywords / total_keywords`, so a topic that wants
broad method vocabulary ("conditional diffusion", "modality dropout",
"contrastive learning") pays for it twice — a large denominator drags every
score down, forcing a low min_relevance, and the low threshold then admits
papers from every other field that shares that vocabulary. A live run
surfaced a brain-MRI inpainting paper and a neural-compilation paper inside
an astronomy praxis track for exactly this reason. The gate separates "what
methods am I interested in" from "what field am I in", so neither has to be
compromised to express the other.

Backfill: existing rows get an empty list, which disables the gate — every
topic scores exactly as it did before.

Idempotent: skips the add if a prior dev session already applied it via
Base.metadata.create_all.

Revision ID: 0017_topic_require_any
Revises: 0016_topic_track
Create Date: 2026-09-05

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_topic_require_any"
down_revision: Union[str, None] = "0016_topic_track"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("topics", "require_any"):
        op.add_column(
            "topics",
            sa.Column(
                "require_any",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )


def downgrade() -> None:
    if _has_column("topics", "require_any"):
        op.drop_column("topics", "require_any")
