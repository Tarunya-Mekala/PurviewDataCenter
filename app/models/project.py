from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.id_generator import generate_id

if TYPE_CHECKING:
    from app.models.comparison_run import ComparisonRun
    from app.models.document import Document
    from app.models.extracted_record import ExtractedRecord
    from app.models.vendor import Vendor


def get_utc_now():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("proj"),
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="active",
        nullable=False,
        index=True,
    )  # "active" | "complete" | "archived"
    owner_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
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

    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="select",
    )
    extracted_records: Mapped[List["ExtractedRecord"]] = relationship(
        "ExtractedRecord",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="select",
    )
    vendors: Mapped[List["Vendor"]] = relationship(
        "Vendor",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="select",
    )
    comparison_runs: Mapped[List["ComparisonRun"]] = relationship(
        "ComparisonRun",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ComparisonRun.run_number.desc()",
    )

