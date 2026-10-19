from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.utils.id_generator import generate_id


def get_utc_now():
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("aud_"),
        index=True,
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    user_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )  # "upload", "delete", "extract", "review", "export", "settings_change", "compare"
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )  # "document", "record", "project", "settings", "vendor"
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
        index=True,
    )
