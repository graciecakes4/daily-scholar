"""add admin_audit_log table (Phase F+1: admin audit trail)

Append-only log of admin mutations: approvals, role changes, suspensions,
invite generation/revocation. Denormalized actor + target identifiers
preserve display info even after the underlying user/invite is deleted.

Idempotent guards so re-running on a half-applied DB is safe.

Revision ID: 0010_admin_audit_log
Revises: 0009_user_onboarded
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_admin_audit_log"
down_revision: Union[str, None] = "0009_user_onboarded"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("admin_audit_log"):
        return

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id_string", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=True),
        sa.Column("target_label", sa.String(length=200), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"],
            name="fk_admin_audit_actor_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_admin_audit_log_event_type"), "admin_audit_log", ["event_type"])
    op.create_index(op.f("ix_admin_audit_log_actor_user_id"), "admin_audit_log", ["actor_user_id"])
    op.create_index(op.f("ix_admin_audit_log_target_id"), "admin_audit_log", ["target_id"])
    op.create_index(op.f("ix_admin_audit_log_created_at"), "admin_audit_log", ["created_at"])
    op.create_index("idx_admin_audit_created", "admin_audit_log", ["created_at"])
    op.create_index("idx_admin_audit_event_created", "admin_audit_log", ["event_type", "created_at"])


def downgrade() -> None:
    if _has_table("admin_audit_log"):
        for ix in (
            "idx_admin_audit_event_created",
            "idx_admin_audit_created",
            op.f("ix_admin_audit_log_created_at"),
            op.f("ix_admin_audit_log_target_id"),
            op.f("ix_admin_audit_log_actor_user_id"),
            op.f("ix_admin_audit_log_event_type"),
        ):
            try:
                op.drop_index(ix, table_name="admin_audit_log")
            except Exception:
                pass
        op.drop_table("admin_audit_log")
