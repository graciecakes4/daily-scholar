"""no-op (placeholder file, cannot be deleted from sandbox)

The real `users.tour_state` migration lives in 0011_tour_version_seen.py
— originally drafted as `tour_version_seen INT`, rewritten in place to
add the JSON `tour_state` column instead. The sandbox where the rewrite
happened couldn't delete the obsolete-name file, so this stub exists
to satisfy alembic's "every .py needs a revision var" requirement
without disturbing the linear upgrade chain.

upgrade() / downgrade() are no-ops. Safe to delete this file on the
host filesystem at your convenience — alembic will not notice.

Revision ID: 0011a_placeholder
Revises: 0011_tour_version_seen
Create Date: 2026-06-26

"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "0011a_placeholder"
down_revision: Union[str, None] = "0011_tour_version_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
