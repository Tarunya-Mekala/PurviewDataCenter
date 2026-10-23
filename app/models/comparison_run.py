from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.utils.id_generator import generate_id

if TYPE_CHECKING:
    from app.models.project import Project


def get_utc_now():
    return datetime.now(timezone.utc)


class ComparisonRun(Base):
    __tablename__ = "comparison_runs"
    __table_args__ = (
        Index("idx_comparison_runs_proj_run", "project_id", "run_number"),
    )

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("run_"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="completed",
        nullable=False,
    )
    rule_set_version: Mapped[str] = mapped_column(
        String(50),
        default="1.0",
        nullable=False,
    )
    total_expected: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    total_found: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    matches_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    discrepancies_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    exceptions_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    document_versions: Mapped[Optional[Any]] = mapped_column(
        JSON,
        nullable=True,
    )
    is_frozen: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="comparison_runs",
    )
    results: Mapped[list["ComparisonResultItem"]] = relationship(
        "ComparisonResultItem",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    issue_groups: Mapped[list["IssueGroup"]] = relationship(
        "IssueGroup",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IssueGroup(Base):
    __tablename__ = "issue_groups"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("grp_"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("comparison_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    vendor_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    cause: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    total_lines: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
    )

    run: Mapped["ComparisonRun"] = relationship(
        "ComparisonRun",
        back_populates="issue_groups",
    )


class ComparisonResultItem(Base):
    __tablename__ = "comparison_results"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_id("res_"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("comparison_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rack: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    vendor_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    vendor_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    item: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    part_number: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    field: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    expected: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=None,
    )
    found: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=None,
    )
    expected_text: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    found_text: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    difference: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    result: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # "match" | "discrepancy" | "exception"
    action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    cause: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    issue_group_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    issue_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    expected_source: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    found_source: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    rule_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    condition_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    condition_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
    )

    run: Mapped["ComparisonRun"] = relationship(
        "ComparisonRun",
        back_populates="results",
    )
