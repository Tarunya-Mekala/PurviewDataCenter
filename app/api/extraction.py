from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_super_admin
from app.models.user import User
from app.schemas.record import (
    AIExtractionRequest,
    AIStatusResponse,
    DocumentExtractionStatusResponse,
    ExtractionJobResponse,
)
from app.services.extraction_service import ExtractionService

router = APIRouter(tags=["Document Parsing & Extraction"])

# ---------------------------------------------------------
# AI Status & Model Inspection
# ---------------------------------------------------------

@router.get(
    "/ai/status",
    response_model=AIStatusResponse,
    summary="Check AI LLM Engine Status",
    description="Inspect Ollama connection health, active default model, and installed models.",
)
def get_ai_status(
    current_user: User = Depends(get_current_super_admin),
):
    from app.ai.llm import ollama_client
    from app.core.config import settings

    is_online = ollama_client.is_available()
    models = ollama_client.list_models() if is_online else []
    return AIStatusResponse(
        available=is_online,
        reachable=is_online,
        ollama_online=is_online,
        model=settings.LLM_MODEL,
        configured_model=settings.LLM_MODEL,
        installed_models=models,
        recommended_model="qwen2.5:27b",
        message="Ollama LLM engine online" if is_online else "Ollama service offline or unreachable",
    )


# ---------------------------------------------------------
# Document Extraction & Triggers
# ---------------------------------------------------------

@router.post(
    "/documents/{document_id}/extract",
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured records from document",
    description="Parse tabular sheets, PDF tables, or CSV data into structured equipment records.",
)
def extract_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.extract_document(db, document_id)


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
    return ExtractionService.extract_document_with_ai(
        db, document_id, model=model_override, allow_fallback=True
    )


@router.post(
    "/extract-ai",
    summary="AI extraction endpoint for documents or text snippets",
    description="Direct endpoint to trigger AI extraction by document_id or raw text.",
)
def extract_ai_generic(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    doc_id = payload.get("document_id") or payload.get("id")
    if doc_id:
        return ExtractionService.extract_document_with_ai(
            db=db,
            document_id=doc_id,
            model=payload.get("model"),
            allow_fallback=True,
        )
    text = payload.get("text") or payload.get("content")
    if text:
        from app.ai.chains import extract_records_with_llm
        from app.core.config import settings
        records = extract_records_with_llm(
            text_content=text,
            document_type=payload.get("document_type", "bom"),
            model=payload.get("model") or settings.LLM_MODEL,
        )
        return {
            "records": records,
            "count": len(records),
            "model_used": payload.get("model") or settings.LLM_MODEL,
        }
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="document_id or text is required")


@router.get(
    "/documents/{document_id}/extraction-status",
    response_model=DocumentExtractionStatusResponse,
    summary="Get extraction status",
)
def get_document_extraction_status(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.get_document_extraction_status(db, document_id)


@router.post(
    "/projects/{project_id}/extract-all",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Extract all documents in project in background",
    description="Run the extraction pipeline asynchronously on all documents within a project. Returns HTTP 202 immediately.",
)
def extract_all_documents(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.queue_extract_all_project_documents(db, project_id, background_tasks)
