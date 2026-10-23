from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.id_generator import generate_id

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.project import Project


def get_utc_now():
    return datetime.now(timezone.utc)


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        Index("idx_vendors_proj_name", "project_id", "name"),
    )

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("vnd"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    contact_person: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    contact_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    contact_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
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


    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="vendors",
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="vendor_rel",
        cascade="all, delete-orphan",
        lazy="select",
    )
