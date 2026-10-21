from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default="global",
    )
    high_confidence_threshold: Mapped[float] = mapped_column(
        Float,
        default=0.90,
        nullable=False,
    )
    check_confidence_threshold: Mapped[float] = mapped_column(
        Float,
        default=0.70,
        nullable=False,
    )
    external_project_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    inactivity_days: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
        onupdate=get_utc_now,
    )
