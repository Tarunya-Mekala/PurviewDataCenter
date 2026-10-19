from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_roles
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogListResponse, AuditLogResponse
from app.utils.id_generator import generate_id

router = APIRouter(tags=["Audit Logs"])


def record_audit_log(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user: Optional[User] = None,
    details: Optional[dict] = None,
) -> AuditLog:
    """Helper to record an append-only audit trail entry."""
    entry = AuditLog(
        id=generate_id("aud_"),
        project_id=project_id,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    )
    db.add(entry)
    db.commit()
    return entry


@router.get(
    "/projects/{project_id}/audit",
    response_model=AuditLogListResponse,
    summary="Get project audit logs",
    description="Retrieve append-only audit log events specifically for a project.",
)
def get_project_audit_logs(
    project_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = (
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.created_at.desc())
    )
    total = db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.project_id == project_id)
    ).scalar() or 0

    logs = db.execute(stmt.offset(skip).limit(limit)).scalars().all()
    return AuditLogListResponse(
        total=total,
        items=[AuditLogResponse.model_validate(log) for log in logs],
    )


@router.get(
    "/audit",
    response_model=AuditLogListResponse,
    summary="Search system audit logs",
    description="Query system-wide append-only audit log entries with filters.",
)
def get_system_audit_logs(
    project: Optional[str] = Query(None, description="Project ID filter"),
    user: Optional[str] = Query(None, description="User ID or email filter"),
    action: Optional[str] = Query(None, description="Action filter (e.g. upload, delete, review)"),
    from_date: Optional[str] = Query(None, alias="from", description="ISO format start date"),
    to_date: Optional[str] = Query(None, alias="to", description="ISO format end date"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["super_admin", "admin"])),
):
    stmt = select(AuditLog)

    if project:
        stmt = stmt.where(AuditLog.project_id == project)
    if user:
        stmt = stmt.where((AuditLog.user_id == user) | (AuditLog.user_email.ilike(f"%{user}%")))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if from_date:
        try:
            dt_from = datetime.fromisoformat(from_date)
            stmt = stmt.where(AuditLog.created_at >= dt_from)
        except Exception:
            pass
    if to_date:
        try:
            dt_to = datetime.fromisoformat(to_date)
            stmt = stmt.where(AuditLog.created_at <= dt_to)
        except Exception:
            pass

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    logs = (
        db.execute(stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit))
        .scalars()
        .all()
    )

    return AuditLogListResponse(
        total=total,
        items=[AuditLogResponse.model_validate(log) for log in logs],
    )
