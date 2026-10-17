"""001_initial_schema_and_features

Revision ID: 001
Revises: 
Create Date: 2026-10-16 14:28:04.271572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # 1. Create all base tables if they don't exist yet
    from app.core.database import Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=conn)

    # 2. Introspect existing tables to add any missing columns safely
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    columns_to_check = {
        "projects": [
            ("status", sa.String(50), {"nullable": False, "server_default": "active"}),
            ("owner_id", sa.String(64), {"nullable": True}),
            ("created_by", sa.String(255), {"nullable": True}),
        ],
        "documents": [
            ("source", sa.String(50), {"nullable": False, "server_default": "plan"}),
            ("vendor_id", sa.String(64), {"nullable": True}),
            ("version", sa.Integer(), {"nullable": False, "server_default": "1"}),
            ("uploaded_by", sa.String(255), {"nullable": True}),
        ],
        "vendors": [
            ("contact_person", sa.String(255), {"nullable": True}),
            ("contact_email", sa.String(255), {"nullable": True}),
            ("contact_phone", sa.String(50), {"nullable": True}),
        ],
        "extracted_records": [
            ("cleaned_part_number", sa.String(255), {"nullable": True}),
            ("model", sa.String(255), {"nullable": True}),
            ("serial_number", sa.String(255), {"nullable": True}),
            ("condition", sa.String(50), {"nullable": True}),
            ("condition_notes", sa.Text(), {"nullable": True}),
            ("rack", sa.String(100), {"nullable": True}),
            ("u_position", sa.String(50), {"nullable": True}),
            ("power_kw", sa.Float(), {"nullable": True}),
            ("cable_length_m", sa.Float(), {"nullable": True}),
            ("manufacturer", sa.String(255), {"nullable": True}),
            ("unmapped_columns", sa.JSON(), {"nullable": True}),
            ("review_reason", sa.String(100), {"nullable": True}),
            ("original_values", sa.JSON(), {"nullable": True}),
            ("extraction_method", sa.String(50), {"nullable": True, "server_default": "table"}),
            ("model_used", sa.String(100), {"nullable": True}),
            ("is_deleted", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
            ("field_sources", sa.JSON(), {"nullable": True}),
        ],
    }

    for table_name, cols in columns_to_check.items():
        if table_name in tables:
            existing_col_names = {c["name"] for c in inspector.get_columns(table_name)}
            with op.batch_alter_table(table_name) as batch_op:
                for col_name, col_type, col_kwargs in cols:
                    if col_name not in existing_col_names:
                        batch_op.add_column(sa.Column(col_name, col_type, **col_kwargs))

    # Add indices if missing
    if "projects" in tables:
        existing_indices = {i["name"] for i in inspector.get_indexes("projects")}
        with op.batch_alter_table("projects") as batch_op:
            if "ix_projects_status" not in existing_indices:
                batch_op.create_index(batch_op.f("ix_projects_status"), ["status"], unique=False)
            if "ix_projects_owner_id" not in existing_indices:
                batch_op.create_index(batch_op.f("ix_projects_owner_id"), ["owner_id"], unique=False)


def downgrade() -> None:
    pass
