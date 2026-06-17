"""auth-ready: add user_id columns to per-user tables

Adds a nullable `user_id VARCHAR(100)` column (defaulting to the local sentinel
'__local__') to every table whose rows belong to a user. Existing rows are
backfilled in-place. Solo behavior is unchanged; multi-user later becomes a
config flip (enable Cloudflare Access, swap the auth dependency) rather than
a schema migration.

Two tables also get unique-constraint changes:
  * daily_content_cache: unique(content_date)         -> unique(user_id, content_date)
  * user_stats:         (none)                        -> unique(user_id)

The daily_content_cache change is fiddly on SQLite because the original
unique was unnamed (auto-generated `sqlite_autoindex_*` that can't be dropped
directly). We rebuild the table with raw SQL on SQLite; Postgres uses a
straight ALTER TABLE.

Revision ID: 0003_auth_ready_user_id
Revises: 0002_topics_user_settings_push
Create Date: 2026-06-16

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_auth_ready_user_id"
down_revision: Union[str, None] = "0002_topics_user_settings_push"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SENTINEL = "__local__"

SIMPLE_USER_TABLES: list[str] = [
    "seen_papers",
    "archived_papers",
    "paper_pdfs",
    "archived_topic_reviews",
    "archived_quizzes",
]


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    # 1. simple tables — add column + index
    for table in SIMPLE_USER_TABLES:
        op.add_column(
            table,
            sa.Column(
                "user_id",
                sa.String(length=100),
                nullable=False,
                server_default=SENTINEL,
            ),
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    # 2. daily_content_cache: swap unique(content_date) for unique(user_id, content_date)
    if _is_sqlite():
        # The original unique on content_date was unnamed; SQLite materializes it
        # as sqlite_autoindex_* which we can't DROP INDEX directly. Rebuild via
        # the standard CREATE-COPY-DROP-RENAME pattern.
        op.execute(
            """
            CREATE TABLE _new_daily_content_cache (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL DEFAULT '__local__',
                content_date DATE NOT NULL,
                paper_unique_id VARCHAR(200),
                paper_data JSON,
                paper_summary JSON,
                topic_reviews JSON,
                quiz_questions JSON,
                resources JSON,
                generated_at DATETIME,
                is_completed BOOLEAN,
                completed_at DATETIME,
                CONSTRAINT uq_daily_content_cache_user_date UNIQUE (user_id, content_date)
            )
            """
        )
        op.execute(
            """
            INSERT INTO _new_daily_content_cache (
                id, content_date, paper_unique_id, paper_data, paper_summary,
                topic_reviews, quiz_questions, resources, generated_at,
                is_completed, completed_at
            )
            SELECT
                id, content_date, paper_unique_id, paper_data, paper_summary,
                topic_reviews, quiz_questions, resources, generated_at,
                is_completed, completed_at
            FROM daily_content_cache
            """
        )
        op.execute("DROP TABLE daily_content_cache")
        op.execute("ALTER TABLE _new_daily_content_cache RENAME TO daily_content_cache")
        op.execute(
            "CREATE INDEX ix_daily_content_cache_content_date "
            "ON daily_content_cache(content_date)"
        )
        op.execute(
            "CREATE INDEX ix_daily_content_cache_user_id "
            "ON daily_content_cache(user_id)"
        )
    else:
        # Postgres / other dialects: ALTER TABLE handles it natively
        op.add_column(
            "daily_content_cache",
            sa.Column(
                "user_id",
                sa.String(length=100),
                nullable=False,
                server_default=SENTINEL,
            ),
        )
        op.create_index(
            "ix_daily_content_cache_user_id", "daily_content_cache", ["user_id"]
        )
        # the constraint name on Postgres is predictable from the table+col
        op.drop_constraint(
            "daily_content_cache_content_date_key",
            "daily_content_cache",
            type_="unique",
        )
        op.create_unique_constraint(
            "uq_daily_content_cache_user_date",
            "daily_content_cache",
            ["user_id", "content_date"],
        )

    # 3. user_stats: add user_id + unique(user_id)
    op.add_column(
        "user_stats",
        sa.Column(
            "user_id",
            sa.String(length=100),
            nullable=False,
            server_default=SENTINEL,
        ),
    )
    op.create_index("ix_user_stats_user_id", "user_stats", ["user_id"])
    # Adding a new unique constraint is portable across dialects
    with op.batch_alter_table("user_stats") as batch_op:
        batch_op.create_unique_constraint("uq_user_stats_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("user_stats") as batch_op:
        batch_op.drop_constraint("uq_user_stats_user_id", type_="unique")
    op.drop_index("ix_user_stats_user_id", table_name="user_stats")
    op.drop_column("user_stats", "user_id")

    if _is_sqlite():
        # rebuild daily_content_cache with the original unique(content_date)
        op.execute(
            """
            CREATE TABLE _new_daily_content_cache (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                content_date DATE NOT NULL,
                paper_unique_id VARCHAR(200),
                paper_data JSON,
                paper_summary JSON,
                topic_reviews JSON,
                quiz_questions JSON,
                resources JSON,
                generated_at DATETIME,
                is_completed BOOLEAN,
                completed_at DATETIME,
                UNIQUE (content_date)
            )
            """
        )
        op.execute(
            """
            INSERT INTO _new_daily_content_cache (
                id, content_date, paper_unique_id, paper_data, paper_summary,
                topic_reviews, quiz_questions, resources, generated_at,
                is_completed, completed_at
            )
            SELECT id, content_date, paper_unique_id, paper_data, paper_summary,
                   topic_reviews, quiz_questions, resources, generated_at,
                   is_completed, completed_at
            FROM daily_content_cache
            """
        )
        op.execute("DROP TABLE daily_content_cache")
        op.execute("ALTER TABLE _new_daily_content_cache RENAME TO daily_content_cache")
        op.execute(
            "CREATE INDEX ix_daily_content_cache_content_date "
            "ON daily_content_cache(content_date)"
        )
    else:
        op.drop_constraint(
            "uq_daily_content_cache_user_date",
            "daily_content_cache",
            type_="unique",
        )
        op.create_unique_constraint(
            "daily_content_cache_content_date_key",
            "daily_content_cache",
            ["content_date"],
        )
        op.drop_index("ix_daily_content_cache_user_id", table_name="daily_content_cache")
        op.drop_column("daily_content_cache", "user_id")

    for table in reversed(SIMPLE_USER_TABLES):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
