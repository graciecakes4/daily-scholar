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


# -- idempotency helpers -----------------------------------------------------
#
# Some beta DBs ended up in a "half-applied 0003" state — typically the
# user_id columns were added (by a dev-time `Base.metadata.create_all` or a
# manual ALTER) before alembic_version was advanced past 0002. Re-running
# this migration on those DBs previously raised `duplicate column name`.
# Each step below now checks current schema state and skips if already done.

def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _has_index(table: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in _inspector().get_indexes(table)}


def _has_named_unique(table: str, name: str) -> bool:
    """True if `name` is a unique constraint OR a unique index on `table`.

    SQLite represents some unique constraints as autoindexes, so we check
    both surfaces. Postgres reports them as constraints.
    """
    insp = _inspector()
    if name in {u["name"] for u in insp.get_unique_constraints(table)}:
        return True
    if name in {i["name"] for i in insp.get_indexes(table) if i.get("unique")}:
        return True
    return False


def upgrade() -> None:
    sqlite = _is_sqlite()

    # 1. simple user-scoped tables: column + index (each guarded)
    for table in SIMPLE_USER_TABLES:
        if not _has_column(table, "user_id"):
            op.add_column(
                table,
                sa.Column(
                    "user_id",
                    sa.String(length=100),
                    nullable=False,
                    server_default=SENTINEL,
                ),
            )
        if not _has_index(table, f"ix_{table}_user_id"):
            op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    # 2. daily_content_cache: column + unique(user_id, content_date)
    dcc_has_user_id = _has_column("daily_content_cache", "user_id")
    dcc_has_new_unique = _has_named_unique(
        "daily_content_cache", "uq_daily_content_cache_user_date"
    )

    if not dcc_has_new_unique:
        if sqlite:
            if not dcc_has_user_id:
                # original-state DB: do the full CREATE-COPY-DROP-RENAME so
                # the new compound UNIQUE replaces the old unnamed unique
                # on content_date (which SQLite materializes as
                # sqlite_autoindex_* and can't be DROP INDEX'd directly).
                _sqlite_full_rebuild_dcc()
            else:
                # half-applied state: user_id column is already there but
                # the constraint swap never ran. Drop the old UNIQUE INDEX
                # on content_date and add the compound unique by hand.
                _sqlite_swap_dcc_unique()
        else:
            # Postgres / other dialects
            if not dcc_has_user_id:
                op.add_column(
                    "daily_content_cache",
                    sa.Column(
                        "user_id",
                        sa.String(length=100),
                        nullable=False,
                        server_default=SENTINEL,
                    ),
                )
            existing = {
                u["name"]
                for u in _inspector().get_unique_constraints("daily_content_cache")
            }
            if "daily_content_cache_content_date_key" in existing:
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

    # ensure user_id index exists regardless of which branch ran above
    if _has_column("daily_content_cache", "user_id") and not _has_index(
        "daily_content_cache", "ix_daily_content_cache_user_id"
    ):
        op.create_index(
            "ix_daily_content_cache_user_id", "daily_content_cache", ["user_id"]
        )

    # 3. user_stats: column + index + UNIQUE(user_id)
    if not _has_column("user_stats", "user_id"):
        op.add_column(
            "user_stats",
            sa.Column(
                "user_id",
                sa.String(length=100),
                nullable=False,
                server_default=SENTINEL,
            ),
        )
    if not _has_index("user_stats", "ix_user_stats_user_id"):
        op.create_index("ix_user_stats_user_id", "user_stats", ["user_id"])
    if not _has_named_unique("user_stats", "uq_user_stats_user_id"):
        with op.batch_alter_table("user_stats") as batch_op:
            batch_op.create_unique_constraint("uq_user_stats_user_id", ["user_id"])


def _sqlite_full_rebuild_dcc() -> None:
    """Original-state SQLite rebuild for daily_content_cache."""
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


def _sqlite_swap_dcc_unique() -> None:
    """Half-applied-state SQLite recovery: column present, constraint missing.

    Drops the old UNIQUE INDEX on content_date and replaces it with a
    non-unique index plus the compound UNIQUE on (user_id, content_date).
    """
    op.execute("DROP INDEX IF EXISTS ix_daily_content_cache_content_date")
    op.execute(
        "CREATE INDEX ix_daily_content_cache_content_date "
        "ON daily_content_cache(content_date)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_daily_content_cache_user_date "
        "ON daily_content_cache(user_id, content_date)"
    )


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
