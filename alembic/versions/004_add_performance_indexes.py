"""Add performance indexes on project_id, document_id, review_status, and related foreign keys

Revision ID: 004_performance_indexes
Revises: 003_runs_and_exports
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "004_performance_indexes"
down_revision: Union[str, Sequence[str], None] = "003_runs_and_exports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    def _create_idx_if_missing(table_name: str, index_name: str, columns: list):
        try:
            existing = [idx["name"] for idx in insp.get_indexes(table_name)]
            if index_name not in existing:
                op.create_index(index_name, table_name, columns)
        except Exception:
            pass

    _create_idx_if_missing(
        "extracted_records",
        "idx_extracted_records_proj_status_del",
        ["project_id", "review_status", "is_deleted"],
    )
    _create_idx_if_missing(
        "extracted_records",
        "idx_extracted_records_proj_del",
        ["project_id", "is_deleted"],
    )
    _create_idx_if_missing(
        "extracted_records",
        "idx_extracted_records_doc_del",
        ["document_id", "is_deleted"],
    )
    _create_idx_if_missing(
        "documents",
        "idx_documents_proj_status",
        ["project_id", "status"],
    )
    _create_idx_if_missing(
        "documents",
        "idx_documents_proj_source",
        ["project_id", "source"],
    )
    _create_idx_if_missing(
        "comparison_runs",
        "idx_comparison_runs_proj_run",
        ["project_id", "run_number"],
    )
    _create_idx_if_missing(
        "vendors",
        "idx_vendors_proj_name",
        ["project_id", "name"],
    )


def downgrade() -> None:
    for idx_name, tbl in [
        ("idx_vendors_proj_name", "vendors"),
        ("idx_comparison_runs_proj_run", "comparison_runs"),
        ("idx_documents_proj_source", "documents"),
        ("idx_documents_proj_status", "documents"),
        ("idx_extracted_records_doc_del", "extracted_records"),
        ("idx_extracted_records_proj_del", "extracted_records"),
        ("idx_extracted_records_proj_status_del", "extracted_records"),
    ]:
        try:
            op.drop_index(idx_name, table_name=tbl)
        except Exception:
            pass
