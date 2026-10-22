from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, require_reviewer_or_admin_flexible
from app.models.user import User
from app.schemas.record import ExcelGridPreviewResponse
from app.services.report_service import ReportService

router = APIRouter(tags=["Reports & Excel Export"])

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _generate_download_token(user: User) -> str:
    """Generate a 15-minute signed token for direct browser file download links."""
    return create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "is_super_admin": user.is_super_admin,
        },
        expires_delta=timedelta(minutes=15),
    )


# ------------------------------------------------------------------
# Document-Level Excel Endpoints
# ------------------------------------------------------------------

@router.get(
    "/reports/documents/{document_id}/excel",
    summary="Download or view extracted document as Excel",
    description="Export extracted document records into a professionally styled Excel workbook (.xlsx) or HTML spreadsheet view.",
    responses={
        200: {
            "content": {
                EXCEL_MIME: {},
                "text/html": {},
            },
            "description": "Returns the generated Excel workbook (.xlsx) or HTML spreadsheet view.",
        }
    },
)
@router.get("/documents/{document_id}/excel", include_in_schema=True)
@router.get("/documents/{document_id}/export/excel", include_in_schema=True)
def export_document_excel(
    document_id: str,
    view: Optional[str] = Query(None, description="Set to 'html' to view interactive spreadsheet in browser"),
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser access"),
    accept: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin_flexible),
):
    # Check if caller wants the interactive web view
    if view == "html" or (accept and "text/html" in accept and "application" not in accept):
        signed_token = _generate_download_token(current_user)
        html_content = ReportService.render_excel_html_view(db, document_id, token=signed_token)
        return HTMLResponse(content=html_content, status_code=200)

    excel_bytes, filename = ReportService.generate_document_excel(db, document_id)
    return Response(
        content=excel_bytes,
        media_type=EXCEL_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get(
    "/reports/documents/{document_id}/excel/view",
    response_class=HTMLResponse,
    summary="Show extracted document as interactive Excel spreadsheet in browser",
    description="Renders a rich, responsive Excel spreadsheet interface directly in the browser with live search, filters, and download capabilities.",
)
@router.get("/documents/{document_id}/excel/view", response_class=HTMLResponse, include_in_schema=True)
def view_document_excel_html(
    document_id: str,
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser links"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin_flexible),
):
    signed_token = _generate_download_token(current_user)
    html_content = ReportService.render_excel_html_view(db, document_id, token=signed_token)
    return HTMLResponse(content=html_content, status_code=200)


@router.get(
    "/reports/documents/{document_id}/excel/preview",
    response_model=ExcelGridPreviewResponse,
    summary="Get extracted document as Excel spreadsheet grid JSON",
    description="Returns structured columns, rows, and summary metrics for client spreadsheet or data grid rendering.",
)
@router.get("/documents/{document_id}/excel/preview", response_model=ExcelGridPreviewResponse, include_in_schema=True)
def preview_document_excel_json(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin_flexible),
):
    return ReportService.get_document_excel_preview(db, document_id)


# ------------------------------------------------------------------
# Project-Level Excel Endpoints
# ------------------------------------------------------------------

@router.get(
    "/reports/projects/{project_id}/excel",
    summary="Download or view all project extracted documents as Excel",
    description="Export all extracted line items and document summaries across a project into a multi-sheet Excel workbook (.xlsx).",
    responses={
        200: {
            "content": {
                EXCEL_MIME: {},
                "text/html": {},
            },
            "description": "Returns the consolidated project Excel workbook (.xlsx) or HTML spreadsheet view.",
        }
    },
)
@router.get("/projects/{project_id}/excel", include_in_schema=True)
@router.get("/projects/{project_id}/export/excel", include_in_schema=True)
def export_project_excel(
    project_id: str,
    view: Optional[str] = Query(None, description="Set to 'html' to view interactive spreadsheet in browser"),
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser access"),
    accept: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin_flexible),
):
    if view == "html" or (accept and "text/html" in accept and "application" not in accept):
        signed_token = _generate_download_token(current_user)
        html_content = ReportService.render_project_excel_html_view(db, project_id, token=signed_token)
        return HTMLResponse(content=html_content, status_code=200)

    excel_bytes, filename = ReportService.generate_project_excel(db, project_id)
    return Response(
        content=excel_bytes,
        media_type=EXCEL_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get(
    "/reports/projects/{project_id}/excel/view",
    response_class=HTMLResponse,
    summary="Show project extracted records as interactive Excel spreadsheet in browser",
    description="Renders a responsive Excel spreadsheet interface for all extracted records across a project.",
)
@router.get("/projects/{project_id}/excel/view", response_class=HTMLResponse, include_in_schema=True)
def view_project_excel_html(
    project_id: str,
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser links"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin_flexible),
):
    signed_token = _generate_download_token(current_user)
    html_content = ReportService.render_project_excel_html_view(db, project_id, token=signed_token)
    return HTMLResponse(content=html_content, status_code=200)


@router.get(
    "/reports/projects/{project_id}/excel/preview",
    response_model=ExcelGridPreviewResponse,
    summary="Get project extracted records as Excel spreadsheet grid JSON",
    description="Returns structured columns and rows for all project records formatted as a spreadsheet table.",
)
@router.get("/projects/{project_id}/excel/preview", response_model=ExcelGridPreviewResponse, include_in_schema=True)
def preview_project_excel_json(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin_flexible),
):
    return ReportService.get_project_excel_preview(db, project_id)

