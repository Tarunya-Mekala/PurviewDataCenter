from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_super_admin, get_current_super_admin_flexible
from app.models.user import User
from app.schemas.record import (
    AIExtractionRequest,
    DocumentExtractionStatusResponse,
    ExtractionJobResponse,
    RawTextExtractionRequest,
)
from app.services.extraction_service import ExtractionService

router = APIRouter(tags=["Document Parsing & AI Extraction"])


# ---------------------------------------------------------
# AI Status & Model Inspection
# ---------------------------------------------------------

@router.get(
    "/ai/status",
    summary="Check AI LLM Engine Status",
    description="Inspect Ollama connection health, active default model (e.g. Qwen 2.5 27B), and installed models.",
)
def get_ai_status(
    current_user: User = Depends(get_current_super_admin),
):
    from app.ai.llm import ollama_client
    from app.core.config import settings

    is_online = ollama_client.is_available()
    models = ollama_client.list_models() if is_online else []
    return {
        "ollama_online": is_online,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "configured_model": settings.LLM_MODEL,
        "installed_models": models,
        "recommended_model": "qwen2.5:27b",
    }


# ---------------------------------------------------------
# Document Extraction & AI Triggers
# ---------------------------------------------------------

@router.post(
    "/documents/{document_id}/extract",
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured records from document",
    description="Parse tabular sheets, PDF tables, or CSV data into structured equipment records. Supports optional AI LLM parsing.",
)
def extract_document(
    document_id: str,
    use_ai: bool = Query(False, description="Enable Qwen LLM AI-powered extraction"),
    model: Optional[str] = Query(None, description="Specify LLM model (e.g. 'qwen2.5:27b')"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.extract_document(db, document_id, use_ai=use_ai, model=model)


@router.post(
    "/documents/{document_id}/extract-ai",
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract document using AI LLM (Qwen 2.5 27B)",
    description="Dedicated AI LLM extraction endpoint for reading complex hardware BOMs, PDF tables, and cable schedules.",
)
def extract_document_ai(
    document_id: str,
    request: Optional[AIExtractionRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    model_override = request.model if request else None
    return ExtractionService.extract_document_with_ai(db, document_id, model=model_override)


@router.get(
    "/documents/{document_id}/extraction-status",
    response_model=DocumentExtractionStatusResponse,
    summary="Get document extraction progress",
    description="Check processing state, number of records extracted, and review decision breakdown.",
)
def get_document_extraction_status(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.get_document_extraction_status(db, document_id)


@router.post(
    "/extract/ai-snippet",
    summary="Extract records from raw text snippet using AI",
    description="Directly parse an arbitrary snippet of hardware BOM text, email notes, or table into structured records without uploading a file.",
)
def extract_snippet_ai(
    request: RawTextExtractionRequest,
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.extract_raw_snippet_with_ai(
        text=request.text,
        document_type=request.document_type or "bom",
        model=request.model,
    )


@router.post(
    "/projects/{project_id}/extract-all",
    response_model=List[ExtractionJobResponse],
    status_code=status.HTTP_200_OK,
    summary="Extract all documents in project",
    description="Run the extraction pipeline on all uploaded documents within a project.",
)
def extract_all_documents(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.extract_all_project_documents(db, project_id)


# ---------------------------------------------------------
# Excel Representation & Export Endpoints
# ---------------------------------------------------------

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/documents/{document_id}/excel",
    summary="Show or download extracted document as Excel",
    description="Export extracted document records into an Excel workbook (.xlsx) or view as interactive spreadsheet (with ?view=html).",
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
@router.get(
    "/documents/{document_id}/export/excel",
    summary="Download extracted document as Excel workbook (.xlsx)",
    description="Direct download endpoint for the styled Excel workbook (.xlsx) of an extracted document.",
    responses={
        200: {
            "content": {
                EXCEL_MIME: {},
            },
            "description": "Returns the generated Excel workbook (.xlsx).",
        }
    },
)
def get_document_excel(
    document_id: str,
    view: Optional[str] = Query(None, description="Set to 'html' to view interactive spreadsheet in browser"),
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser access"),
    accept: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_flexible),
):
    if view == "html" or (accept and "text/html" in accept and "application" not in accept):
        html_content = ExtractionService.render_excel_html_view(db, document_id, token=token)
        return HTMLResponse(content=html_content, status_code=200)

    excel_bytes, filename = ExtractionService.export_document_to_excel(db, document_id)
    return Response(
        content=excel_bytes,
        media_type=EXCEL_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get(
    "/documents/{document_id}/excel/view",
    response_class=HTMLResponse,
    summary="Show extracted document as interactive Excel spreadsheet in browser",
    description="Renders a rich Excel spreadsheet interface in the browser with live search, filters, and download capabilities.",
)
def view_document_excel_html(
    document_id: str,
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser access"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_flexible),
):
    html_content = ExtractionService.render_excel_html_view(db, document_id, token=token)
    return HTMLResponse(content=html_content, status_code=200)


@router.get(
    "/documents/{document_id}/excel/preview",
    summary="Get extracted document as Excel spreadsheet grid JSON",
    description="Returns structured columns, rows, and summary metrics for client spreadsheet or data grid rendering.",
)
def preview_document_excel_json(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_flexible),
):
    return ExtractionService.get_document_excel_preview(db, document_id)


@router.get(
    "/projects/{project_id}/excel",
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
@router.get(
    "/projects/{project_id}/export/excel",
    summary="Download all project extracted documents as Excel (.xlsx)",
    description="Direct download endpoint for consolidated project Excel workbook.",
    responses={
        200: {
            "content": {
                EXCEL_MIME: {},
            },
            "description": "Returns the consolidated project Excel workbook (.xlsx).",
        }
    },
)
def get_project_excel(
    project_id: str,
    view: Optional[str] = Query(None, description="Set to 'html' to view interactive spreadsheet in browser"),
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser access"),
    accept: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_flexible),
):
    if view == "html" or (accept and "text/html" in accept and "application" not in accept):
        html_content = ExtractionService.render_project_excel_html_view(db, project_id, token=token)
        return HTMLResponse(content=html_content, status_code=200)

    excel_bytes, filename = ExtractionService.export_project_to_excel(db, project_id)
    return Response(
        content=excel_bytes,
        media_type=EXCEL_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get(
    "/projects/{project_id}/excel/view",
    response_class=HTMLResponse,
    summary="Show project extracted records as interactive Excel spreadsheet in browser",
    description="Renders a responsive Excel spreadsheet interface for all extracted records across a project.",
)
def view_project_excel_html(
    project_id: str,
    token: Optional[str] = Query(None, description="Optional JWT authentication token for direct browser access"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_flexible),
):
    html_content = ExtractionService.render_project_excel_html_view(db, project_id, token=token)
    return HTMLResponse(content=html_content, status_code=200)


@router.get(
    "/projects/{project_id}/excel/preview",
    summary="Get project extracted records as Excel spreadsheet grid JSON",
    description="Returns structured columns and rows for all project records formatted as a spreadsheet table.",
)
def preview_project_excel_json(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_flexible),
):
    return ExtractionService.get_project_excel_preview(db, project_id)
