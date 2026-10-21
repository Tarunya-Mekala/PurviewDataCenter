from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.audit import record_audit_log
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.export_record import ExportRecord
from app.models.project import Project
from app.models.user import User
from app.schemas.export import (
    ExportCreateRequest,
    ExportRecordListResponse,
    ExportRecordResponse,
)
from app.utils.id_generator import generate_id

router = APIRouter(tags=["Exports"])


@router.post(
    "/projects/{project_id}/exports",
    response_model=ExportRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an Excel export",
    description="Record when a user or frontend generates an Excel export file.",
)
def record_export(
    project_id: str,
    export_in: ExportCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    file_name = (
        export_in.file_name
        or f"export_{project_id}_{export_in.type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

    record = ExportRecord(
        id=generate_id("exp_"),
        project_id=project_id,
        export_type=export_in.type.lower().strip(),
        vendor_id=export_in.vendor_id,
        file_name=file_name,
        line_count=export_in.line_count or 0,
        created_by=current_user.full_name or current_user.email,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    record_audit_log(
        db=db,
        action="export",
        resource_type="export",
        resource_id=record.id,
        project_id=project_id,
        user=current_user,
        details={
            "type": record.export_type,
            "file_name": record.file_name,
            "line_count": record.line_count,
        },
    )

    return ExportRecordResponse.model_validate(record)


@router.get(
    "/exports",
    response_model=ExportRecordListResponse,
    summary="List all export records",
    description="Retrieve a list of generated exports across all projects.",
)
def list_exports(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(ExportRecord)
    if project_id:
        stmt = stmt.where(ExportRecord.project_id == project_id)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    records = (
        db.execute(stmt.order_by(ExportRecord.created_at.desc()).offset(skip).limit(limit))
        .scalars()
        .all()
    )

    return ExportRecordListResponse(
        total=total,
        items=[ExportRecordResponse.model_validate(r) for r in records],
    )
