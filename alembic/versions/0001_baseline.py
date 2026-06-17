"""baseline — existing Daily Scholar schema (pre-Topic-model)

This is the pre-Phase-0 schema as it existed in beta. Fresh installs run
this on first migrate. Existing beta-tester DBs that already have these
tables should be marked at this revision via:

    alembic stamp 0001_baseline

before running `alembic upgrade head` to pick up later migrations.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-15

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seen_papers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("unique_id", sa.String(length=200), nullable=False),
        sa.Column("arxiv_id", sa.String(length=50), nullable=True),
        sa.Column("semantic_scholar_id", sa.String(length=100), nullable=True),
        sa.Column("doi", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("authors", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("shown_date", sa.Date(), nullable=False),
        sa.Column("shown_at", sa.DateTime(), nullable=True),
        sa.Column("was_archived", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unique_id"),
    )
    op.create_index("idx_seen_shown_date", "seen_papers", ["shown_date"])
    op.create_index(op.f("ix_seen_papers_unique_id"), "seen_papers", ["unique_id"])

    op.create_table(
        "archived_papers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seen_paper_id", sa.Integer(), nullable=True),
        sa.Column("unique_id", sa.String(length=200), nullable=False),
        sa.Column("arxiv_id", sa.String(length=50), nullable=True),
        sa.Column("semantic_scholar_id", sa.String(length=100), nullable=True),
        sa.Column("doi", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("authors", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("published_date", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("primary_category", sa.String(length=100), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_findings", sa.JSON(), nullable=True),
        sa.Column("local_pdf_path", sa.String(length=500), nullable=True),
        sa.Column("has_local_pdf", sa.Boolean(), nullable=True),
        sa.Column("user_rating", sa.Integer(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("read_status", sa.String(length=20), nullable=True),
        sa.Column("linked_topic_ids", sa.JSON(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["seen_paper_id"], ["seen_papers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unique_id"),
    )
    op.create_index("idx_archived_status", "archived_papers", ["read_status"])
    op.create_index("idx_archived_date", "archived_papers", ["archived_at"])
    op.create_index(op.f("ix_archived_papers_unique_id"), "archived_papers", ["unique_id"])

    op.create_table(
        "paper_pdfs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("archived_paper_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("is_processed", sa.Boolean(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["archived_paper_id"], ["archived_papers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )

    op.create_table(
        "archived_topic_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.String(length=100), nullable=False),
        sa.Column("topic_name", sa.String(length=200), nullable=False),
        sa.Column("course_id", sa.String(length=100), nullable=False),
        sa.Column("course_name", sa.String(length=200), nullable=False),
        sa.Column("week_covered", sa.Integer(), nullable=True),
        sa.Column("review_content", sa.Text(), nullable=True),
        sa.Column("key_points", sa.JSON(), nullable=True),
        sa.Column("connections", sa.JSON(), nullable=True),
        sa.Column("practice_suggestions", sa.JSON(), nullable=True),
        sa.Column("key_concepts", sa.JSON(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("confidence_level", sa.Integer(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("linked_paper_ids", sa.JSON(), nullable=True),
        sa.Column("first_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_topic_status", "archived_topic_reviews", ["status"])
    op.create_index(op.f("ix_archived_topic_reviews_topic_id"), "archived_topic_reviews", ["topic_id"])

    op.create_table(
        "archived_quizzes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("topic_ids", sa.JSON(), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=True),
        sa.Column("total_points", sa.Integer(), nullable=True),
        sa.Column("score_earned", sa.Float(), nullable=True),
        sa.Column("percentage", sa.Float(), nullable=True),
        sa.Column("questions", sa.JSON(), nullable=True),
        sa.Column("taken_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "daily_content_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_date", sa.Date(), nullable=False),
        sa.Column("paper_unique_id", sa.String(length=200), nullable=True),
        sa.Column("paper_data", sa.JSON(), nullable=True),
        sa.Column("paper_summary", sa.JSON(), nullable=True),
        sa.Column("topic_reviews", sa.JSON(), nullable=True),
        sa.Column("quiz_questions", sa.JSON(), nullable=True),
        sa.Column("resources", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_date"),
    )
    op.create_index(op.f("ix_daily_content_cache_content_date"), "daily_content_cache", ["content_date"])

    op.create_table(
        "user_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("total_papers_seen", sa.Integer(), nullable=True),
        sa.Column("total_papers_archived", sa.Integer(), nullable=True),
        sa.Column("total_papers_completed", sa.Integer(), nullable=True),
        sa.Column("total_topics_reviewed", sa.Integer(), nullable=True),
        sa.Column("total_quizzes_taken", sa.Integer(), nullable=True),
        sa.Column("total_quiz_questions", sa.Integer(), nullable=True),
        sa.Column("total_correct_answers", sa.Integer(), nullable=True),
        sa.Column("current_streak_days", sa.Integer(), nullable=True),
        sa.Column("longest_streak_days", sa.Integer(), nullable=True),
        sa.Column("last_activity_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("user_stats")
    op.drop_index(op.f("ix_daily_content_cache_content_date"), table_name="daily_content_cache")
    op.drop_table("daily_content_cache")
    op.drop_table("archived_quizzes")
    op.drop_index(op.f("ix_archived_topic_reviews_topic_id"), table_name="archived_topic_reviews")
    op.drop_index("idx_topic_status", table_name="archived_topic_reviews")
    op.drop_table("archived_topic_reviews")
    op.drop_table("paper_pdfs")
    op.drop_index(op.f("ix_archived_papers_unique_id"), table_name="archived_papers")
    op.drop_index("idx_archived_date", table_name="archived_papers")
    op.drop_index("idx_archived_status", table_name="archived_papers")
    op.drop_table("archived_papers")
    op.drop_index(op.f("ix_seen_papers_unique_id"), table_name="seen_papers")
    op.drop_index("idx_seen_shown_date", table_name="seen_papers")
    op.drop_table("seen_papers")
