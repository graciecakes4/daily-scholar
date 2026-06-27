"""add scope library tables and UserSettings.active_scope_id (Phase E)

Promotes the legacy per-user scope (UserSettings.scope_mode +
scope_topic_ids) into a first-class, shareable entity:

  * `scopes`                - the saved view (name, description, owner,
                              visibility, mode, topic_ids, fork lineage)
  * `scope_access_grants`   - per-(scope, user) view-access records for
                              private scopes
  * `scope_access_requests` - pending/approved/denied access requests
                              that resolve into grants

Plus `user_settings.active_scope_id` so a user can switch which scope
in their library drives discovery / review / quizzes. The legacy
scope_mode + scope_topic_ids columns stay populated as a back-compat
cache for one release; the materialization happens out-of-band via
`scripts/migrate_to_scope_library.py`.

scope_access_grants.user_id and scope_access_requests.requester_user_id
are kept as String(100) for consistency with the existing user-scoped
tables (topic_subscriptions, seen_papers, ...). See the post-beta
TODO in backend/database.py.

Idempotent guards so re-running on a half-applied DB is safe.

Revision ID: 0012_scopes
Revises: 0011a_placeholder
Create Date: 2026-06-27

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_scopes"
down_revision: Union[str, None] = "0011a_placeholder"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    cols = sa.inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == column for c in cols)


def upgrade() -> None:
    # ------------------------------------------------------------------ scopes
    if not _has_table("scopes"):
        op.create_table(
            "scopes",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
            sa.Column("scope_mode", sa.String(length=20), nullable=False, server_default="all"),
            sa.Column("scope_topic_ids", sa.JSON(), nullable=False),
            sa.Column("forked_from_scope_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["owner_user_id"], ["users.id"],
                name="fk_scopes_owner_user_id",
            ),
            sa.ForeignKeyConstraint(
                ["forked_from_scope_id"], ["scopes.id"],
                name="fk_scopes_forked_from_scope_id",
                ondelete="SET NULL",
            ),
        )
        op.create_index(op.f("ix_scopes_owner_user_id"), "scopes", ["owner_user_id"])
        op.create_index(op.f("ix_scopes_visibility"), "scopes", ["visibility"])
        op.create_index(op.f("ix_scopes_forked_from_scope_id"), "scopes", ["forked_from_scope_id"])
        op.create_index("idx_scope_owner_visibility", "scopes", ["owner_user_id", "visibility"])
        op.create_index("idx_scope_visibility_name", "scopes", ["visibility", "name"])

    # ------------------------------------------------------------ access grants
    if not _has_table("scope_access_grants"):
        op.create_table(
            "scope_access_grants",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("scope_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
            sa.Column("granted_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["scope_id"], ["scopes.id"],
                name="fk_scope_access_grants_scope_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["granted_by_user_id"], ["users.id"],
                name="fk_scope_access_grants_granted_by_user_id",
            ),
            sa.UniqueConstraint(
                "scope_id", "user_id",
                name="uq_scope_access_grants_scope_user",
            ),
        )
        op.create_index(op.f("ix_scope_access_grants_scope_id"), "scope_access_grants", ["scope_id"])
        op.create_index(op.f("ix_scope_access_grants_user_id"), "scope_access_grants", ["user_id"])
        op.create_index("idx_scope_access_grants_user", "scope_access_grants", ["user_id"])

    # ---------------------------------------------------------- access requests
    if not _has_table("scope_access_requests"):
        op.create_table(
            "scope_access_requests",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("scope_id", sa.Integer(), nullable=False),
            sa.Column("requester_user_id", sa.String(length=100), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["scope_id"], ["scopes.id"],
                name="fk_scope_access_requests_scope_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["decided_by_user_id"], ["users.id"],
                name="fk_scope_access_requests_decided_by_user_id",
            ),
        )
        op.create_index(op.f("ix_scope_access_requests_scope_id"), "scope_access_requests", ["scope_id"])
        op.create_index(op.f("ix_scope_access_requests_requester_user_id"), "scope_access_requests", ["requester_user_id"])
        op.create_index(op.f("ix_scope_access_requests_status"), "scope_access_requests", ["status"])
        op.create_index(
            "idx_scope_access_requests_scope_status",
            "scope_access_requests", ["scope_id", "status"],
        )
        op.create_index(
            "idx_scope_access_requests_requester_status",
            "scope_access_requests", ["requester_user_id", "status"],
        )

    # ----------------------------------------------- user_settings.active_scope_id
    # SQLite needs batch_alter_table to add a column with a FK constraint
    # cleanly. The column is nullable so legacy rows survive until the
    # migration script (scripts/migrate_to_scope_library.py) populates it.
    if not _has_column("user_settings", "active_scope_id"):
        with op.batch_alter_table("user_settings") as batch:
            batch.add_column(sa.Column("active_scope_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_user_settings_active_scope_id",
                "scopes",
                ["active_scope_id"], ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            op.f("ix_user_settings_active_scope_id"),
            "user_settings", ["active_scope_id"],
        )


def downgrade() -> None:
    if _has_column("user_settings", "active_scope_id"):
        op.drop_index(op.f("ix_user_settings_active_scope_id"), table_name="user_settings")
        with op.batch_alter_table("user_settings") as batch:
            batch.drop_constraint("fk_user_settings_active_scope_id", type_="foreignkey")
            batch.drop_column("active_scope_id")

    if _has_table("scope_access_requests"):
        op.drop_index("idx_scope_access_requests_requester_status", table_name="scope_access_requests")
        op.drop_index("idx_scope_access_requests_scope_status", table_name="scope_access_requests")
        op.drop_index(op.f("ix_scope_access_requests_status"), table_name="scope_access_requests")
        op.drop_index(op.f("ix_scope_access_requests_requester_user_id"), table_name="scope_access_requests")
        op.drop_index(op.f("ix_scope_access_requests_scope_id"), table_name="scope_access_requests")
        op.drop_table("scope_access_requests")

    if _has_table("scope_access_grants"):
        op.drop_index("idx_scope_access_grants_user", table_name="scope_access_grants")
        op.drop_index(op.f("ix_scope_access_grants_user_id"), table_name="scope_access_grants")
        op.drop_index(op.f("ix_scope_access_grants_scope_id"), table_name="scope_access_grants")
        op.drop_table("scope_access_grants")

    if _has_table("scopes"):
        op.drop_index("idx_scope_visibility_name", table_name="scopes")
        op.drop_index("idx_scope_owner_visibility", table_name="scopes")
        op.drop_index(op.f("ix_scopes_forked_from_scope_id"), table_name="scopes")
        op.drop_index(op.f("ix_scopes_visibility"), table_name="scopes")
        op.drop_index(op.f("ix_scopes_owner_user_id"), table_name="scopes")
        op.drop_table("scopes")
