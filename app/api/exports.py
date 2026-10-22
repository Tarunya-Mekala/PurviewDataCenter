import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.audit import record_audit_log
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    require_reviewer_or_admin,
    require_reviewer_or_admin_flexible,
    require_viewer_or_above,
)
from app.models.export_record import ExportRecord
from app.models.project import Project
from app.models.user import User
from app.schemas.export import (
    ExportCreateRequest,
    ExportRecordListResponse,
    ExportRecordResponse,
)
from app.services.backup_service import BackupService
from app.utils.file_utils import get_mime_type_for_file, sanitize_filename
from app.utils.id_generator import generate_id
from app.utils.storage_encryption import decrypt_file_bytes, encrypt_file_bytes

router = APIRouter(tags=["Exports"])


@router.post(
    "/projects/{project_id}/exports",
    response_model=ExportRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record and store an exported file",
    description=(
        "Accepts an exported file (multipart: file, type=full|issues|vendor, vendor_id, line_count, file_name, run_id) "
        "or JSON metadata. Encrypts file at rest and stores it with SHA-256 fingerprint, who, when, and run_id. "
        "Restricted to reviewer and admin only."
    ),
)
async def record_export(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin),
):
    project = db.get(Project, project_id)
    if not project or getattr(project, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    content_type = request.headers.get("content-type", "").lower()

    file_bytes: Optional[bytes] = None
    checksum_sha256: Optional[str] = None
    file_name: Optional[str] = None
    export_type: str = "full"
    vendor_id: Optional[str] = None
    line_count: int = 0
    run_id: Optional[str] = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            file_bytes = await uploaded_file.read()
            file_name = getattr(uploaded_file, "filename", None)

        raw_type = form.get("type") or form.get("export_type")
        if raw_type:
            export_type = str(raw_type).lower().strip()

        raw_vendor = form.get("vendor_id")
        if raw_vendor and str(raw_vendor).strip() not in ["", "none", "null"]:
            vendor_id = str(raw_vendor).strip()

        raw_line_count = form.get("line_count")
        if raw_line_count is not None:
            try:
                line_count = int(raw_line_count)
            except ValueError:
                line_count = 0

        form_file_name = form.get("file_name")
        if form_file_name and str(form_file_name).strip():
            file_name = str(form_file_name).strip()

        raw_run_id = form.get("run_id")
        if raw_run_id and str(raw_run_id).strip() not in ["", "none", "null"]:
            run_id = str(raw_run_id).strip()

    else:
        # JSON payload support for backward compatibility
        try:
            body = await request.json()
        except Exception:
            body = {}
        export_type = str(body.get("type") or body.get("export_type") or "full").lower().strip()
        raw_vendor = body.get("vendor_id")
        if raw_vendor and str(raw_vendor).strip() not in ["", "none", "null"]:
            vendor_id = str(raw_vendor).strip()
        line_count = int(body.get("line_count") or 0)
        file_name = body.get("file_name")
        raw_run_id = body.get("run_id")
        if raw_run_id and str(raw_run_id).strip() not in ["", "none", "null"]:
            run_id = str(raw_run_id).strip()

    # Determine fallback filename if not provided
    if not file_name:
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_name = f"export_{project_id}_{export_type}_{timestamp_str}.xlsx"

    user_identifier = current_user.email or current_user.full_name or "system"

    # Step 3 & 4: Every export record points to its run_id
    if not run_id:
        from app.models.comparison_run import ComparisonRun
        latest_run = db.execute(
            select(ComparisonRun)
            .where(ComparisonRun.project_id == project_id)
            .order_by(ComparisonRun.run_number.desc(), ComparisonRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_run:
            run_id = latest_run.id
        else:
            from app.services.comparison_service import ComparisonService
            cmp_res = ComparisonService.compare_project(
                db=db,
                project_id=project_id,
                persist_run=True,
                created_by=user_identifier,
            )
            run_id = cmp_res.run_id

    export_id = generate_id("exp_")
    stored_path_str: Optional[str] = None

    # Store file on disk (encrypted at rest) and compute SHA-256 fingerprint on original content
    if file_bytes is not None:
        hasher = hashlib.sha256()
        hasher.update(file_bytes)
        checksum_sha256 = hasher.hexdigest()

        exports_dir = Path(settings.REPORT_DIR) / "exports" / project_id
        exports_dir.mkdir(parents=True, exist_ok=True)

        clean_name = sanitize_filename(file_name)
        disk_filename = f"{export_id}_{clean_name}"
        full_dest = exports_dir / disk_filename

        # Encrypt file bytes at rest before writing to disk
        encrypted_bytes = encrypt_file_bytes(file_bytes, settings.JWT_SECRET_KEY)
        with open(full_dest, "wb") as f:
            f.write(encrypted_bytes)

        stored_path_str = str(full_dest)

    record = ExportRecord(
        id=export_id,
        project_id=project_id,
        export_type=export_type,
        vendor_id=vendor_id,
        file_name=file_name,
        file_path=stored_path_str,
        checksum_sha256=checksum_sha256,
        run_id=run_id,
        line_count=line_count,
        created_by=user_identifier,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Write audit entry for every export (who, vendor, run, file name, fingerprint)
    record_audit_log(
        db=db,
        action="export",
        resource_type="export",
        resource_id=record.id,
        project_id=project_id,
        user=current_user,
        details={
            "who": user_identifier,
            "vendor": record.vendor_id,
            "vendor_id": record.vendor_id,
            "run": record.run_id,
            "run_id": record.run_id,
            "file_name": record.file_name,
            "fingerprint": record.checksum_sha256,
            "checksum_sha256": record.checksum_sha256,
            "type": record.export_type,
            "line_count": record.line_count,
            "has_file": file_bytes is not None,
            "encrypted_at_rest": True,
        },
    )

    return ExportRecordResponse.model_validate(record)


@router.get(
    "/exports/{export_id}/file",
    summary="Download the exact stored export file",
    description="Returns the stored export file unchanged, decrypted on-the-fly with SHA-256 verification. Reviewer/Admin only.",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "text/csv": {},
                "application/octet-stream": {},
            },
            "description": "Returns the exact stored file unchanged.",
        },
        403: {"description": "Access forbidden: Reviewer or Admin privileges required."},
        404: {"description": "Export record or stored file not found."},
    },
)
def get_export_file(
    export_id: str,
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser links"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin_flexible),
):
    record = db.get(ExportRecord, export_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export record '{export_id}' not found.",
        )

    if not record.file_path or not os.path.exists(record.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored export file not found on disk.",
        )

    with open(record.file_path, "rb") as f:
        stored_bytes = f.read()

    # Transparently decrypt file bytes stored encrypted at rest
    decrypted_bytes = decrypt_file_bytes(stored_bytes, settings.JWT_SECRET_KEY)

    # Verify SHA-256 fingerprint integrity
    if record.checksum_sha256:
        calculated_sha = hashlib.sha256(decrypted_bytes).hexdigest()
        if calculated_sha != record.checksum_sha256:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored file integrity verification failed (SHA-256 checksum mismatch)",
            )

    media_type = get_mime_type_for_file(record.file_name)

    return Response(
        content=decrypted_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{record.file_name}"',
            "Access-Control-Expose-Headers": "Content-Disposition, X-Checksum-SHA256",
            "X-Checksum-SHA256": record.checksum_sha256 or "",
        },
    )


@router.get(
    "/exports/retention-policy",
    summary="Get export retention policy and backup configuration",
    description="Returns the retention period (7 years / 2555 days), backup directory, and storage encryption specifications.",
)
def get_export_retention_policy(
    current_user: User = Depends(require_viewer_or_above),
):
    """Return the data retention policy and backup details for stored exports."""
    return BackupService.get_retention_policy()


@router.get(
    "/exports",
    response_model=ExportRecordListResponse,
    summary="List all export records (viewers read-only)",
    description="Retrieve a list of generated exports across all projects. Viewers, engineers, reviewers, and admins permitted.",
)
def list_exports(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer_or_above),
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

