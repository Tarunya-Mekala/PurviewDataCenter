from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

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

    quantity: Mapped[Optional[float]] = mapped_column(
        Float,
        default=1.0,
        nullable=True,
    )

    unit: Mapped[Optional[str]] = mapped_column(
        String(50),
        default="pcs",
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
    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
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

    confidence_score: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )

    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
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