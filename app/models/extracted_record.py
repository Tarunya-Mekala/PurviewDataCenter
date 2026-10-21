from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.id_generator import generate_id


if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.project import Project
    from app.models.record_review_action import RecordReviewAction


def get_utc_now():
    return datetime.now(timezone.utc)


class ExtractedRecord(Base):
    __tablename__ = "extracted_records"

    # =========================================================
    # Primary Key
    # =========================================================

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("rec"),
        index=True,
    )

    # =========================================================
    # Relationships / Foreign Keys
    # =========================================================

    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "projects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # =========================================================
    # Classification & Category
    # =========================================================

    record_type: Mapped[str] = mapped_column(
        String(50),
        default="bom_item",
        nullable=False,
        index=True,
    )

    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # =========================================================
    # Canonical Equipment / Inventory Fields
    # =========================================================

    equipment_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    part_number: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    cleaned_part_number: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    model: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    serial_number: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    condition: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )  # "ok" | "failed" | null
    condition_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    model: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    manufacturer: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    vendor: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Problem 5: Never default to 1 or pcs when not present in file!
    quantity: Mapped[Optional[float]] = mapped_column(
        Float,
        default=None,
        nullable=True,
    )

    unit: Mapped[Optional[str]] = mapped_column(
        String(50),
        default=None,
        nullable=True,
    )

    # =========================================================
    # Rack Information
    # =========================================================

    rack_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    u_position: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Existing generic location field
    manufacturer: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    vendor: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )  # kept for frontend backward compatibility

    # Physical Location & Rack fields
    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    rack: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    u_position: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    power_kw: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    cable_length_m: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    # =========================================================
    # Connectivity / P2P / Cabling Fields
    # =========================================================

    source_device: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    source_port: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    target_device: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    target_port: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    cable_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    cable_length: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # =========================================================
    # Power / Physical Information
    # =========================================================

    power_watts: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    dimensions: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # =========================================================
    # AI Extraction Metadata
    # =========================================================

    # Extraction Metadata & Method
    confidence_score: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )

    extraction_method: Mapped[str] = mapped_column(
        String(50),
        default="table",
        nullable=False,
    )  # "table" | "ai"
    model_used: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    unmapped_columns: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        default=list,
        nullable=True,
    )
    review_reason: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )  # "missing_value" | "unmapped_field" | "unclear_match" | etc.

    # Problem 8: Original frozen snapshot at creation
    original_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )

    source_sheet: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    source_row: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    field_sources: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )


    # =========================================================
    # Human Review & Verification
    # =========================================================

    review_status: Mapped[str] = mapped_column(
        String(50),
        default="pending_review",
        nullable=False,
        index=True,
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    is_manually_added: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # =========================================================
    # Problem 9: Soft delete
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    # Timestamps
    # =========================================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
        onupdate=get_utc_now,
        nullable=False,
    )

    # =========================================================
    # Relationships
    # =========================================================

    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="extracted_records",
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="extracted_records",
    )
    history: Mapped[List["RecordReviewAction"]] = relationship(
        "RecordReviewAction",
        back_populates="record",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RecordReviewAction.created_at.asc()",
    )
