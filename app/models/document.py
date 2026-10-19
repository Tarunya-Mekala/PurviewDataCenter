from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.id_generator import generate_id

if TYPE_CHECKING:
    from app.models.extracted_record import ExtractedRecord
    from app.models.project import Project
    from app.models.vendor import Vendor


def get_utc_now():
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("doc"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    file_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(
        String(50),
        default="other",
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )
    checksum_sha256: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        default="plan",
        nullable=False,
        index=True,
    )  # "plan" or "vendor"
    vendor_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="documents",
    )
    vendor_rel: Mapped[Optional["Vendor"]] = relationship(
        "Vendor",
        back_populates="documents",
    )
    extracted_records: Mapped[List["ExtractedRecord"]] = relationship(
        "ExtractedRecord",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
