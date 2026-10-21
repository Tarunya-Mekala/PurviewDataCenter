"""Merge the initial schema migration heads.

Revision ID: merge_001_de2
Revises: 001, de2e09e0bbfc
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "merge_001_de2"
down_revision: Union[str, Sequence[str], None] = ("001", "de2e09e0bbfc")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
