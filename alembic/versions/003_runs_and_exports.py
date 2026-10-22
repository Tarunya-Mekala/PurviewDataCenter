"""Add created_by, document_versions, is_frozen to comparison_runs and file_path, checksum_sha256, run_id to export_records

Revision ID: 003_runs_and_exports
Revises: merge_001_de2
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "003_runs_and_exports"
down_revision: Union[str, Sequence[str], None] = "merge_001_de2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to export_records if they don't exist
    conn = op.get_bind()
    insp = sa.inspect(conn)

    export_cols = [c["name"] for c in insp.get_columns("export_records")]
    if "file_path" not in export_cols:
        op.add_column("export_records", sa.Column("file_path", sa.String(500), nullable=True))
    if "checksum_sha256" not in export_cols:
        op.add_column("export_records", sa.Column("checksum_sha256", sa.String(64), nullable=True))
    if "run_id" not in export_cols:
        op.add_column("export_records", sa.Column("run_id", sa.String(64), nullable=True))

    run_cols = [c["name"] for c in insp.get_columns("comparison_runs")]
    if "created_by" not in run_cols:
        op.add_column("comparison_runs", sa.Column("created_by", sa.String(255), nullable=True))
    if "document_versions" not in run_cols:
        op.add_column("comparison_runs", sa.Column("document_versions", sa.JSON(), nullable=True))
    if "is_frozen" not in run_cols:
        op.add_column("comparison_runs", sa.Column("is_frozen", sa.Boolean(), server_default=sa.text("true"), nullable=False))


def downgrade() -> None:
    pass
