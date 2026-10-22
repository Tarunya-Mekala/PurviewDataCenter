from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.utils.id_generator import generate_id


def get_utc_now():
    return datetime.now(timezone.utc)


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("exp_"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    export_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # "full" | "issues" | "vendor"
    vendor_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    checksum_sha256: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    run_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    line_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
    )
