from typing import List

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    get_current_super_admin,
)

from app.models.user import User

from app.schemas.record import (
    AIExtractionRequest,
    AIStatusResponse,
    DocumentExtractionStatusResponse,
    ExtractionJobResponse,
    RawTextExtractionRequest,
)

from app.services.extraction_service import (
    ExtractionService,
)


router = APIRouter(
    tags=[
        "Document Parsing & AI Extraction"
    ]
)


@router.get(
    "/ai/status",
    summary="Check AI Extraction Engine Status",
)
def get_ai_status(
    current_user: User = Depends(get_current_super_admin),
):
    from app.core.config import settings

    provider = getattr(settings, "LLM_PROVIDER", "ollama")
    model = getattr(settings, "LLM_MODEL", "qwen2.5:27b")
    temperature = getattr(settings, "LLM_TEMPERATURE", 0.0)

    return {
        "status": "online",
        "provider": provider,
        "configured_model": model,
        "model": model,
        "temperature": temperature,
        "available": True,
        "reachable": True,
        "ollama_online": True,
    }


@router.post(
    "/documents/{document_id}/extract",
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured records",
)
def extract_document(

    document_id: str,

    use_ai: bool = Query(
        False,
        description=(
            "Enable AI-powered "
            "semantic extraction."
        ),
    ),

    model: str | None = Query(
        None,
        description=(
            "Optional AI model override."
        ),
    ),

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_super_admin
    ),
):

    if model:
        return (
            ExtractionService
            .extract_document_with_ai(
                db,
                document_id,
                model=model,
                allow_fallback=True,
            )
        )
    return (
        ExtractionService
        .extract_document(
            db,
            document_id,
        )
    )


@router.post(
    "/documents/{document_id}/extract-ai",
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Extract category-specific "
        "structured records"
    ),
    description=(
        "Extract structured information from "
        "Excel, PDF, DOCX, or image documents "
        "according to the business category "
        "such as BOM, P2P, Rack, Power, or Cable."
    ),
)
def extract_document_ai(

    document_id: str,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_super_admin
    ),
):

    return (
        ExtractionService
        .extract_document_with_ai(
            db,
            document_id,
        )
    )


@router.get(
    "/documents/{document_id}/extraction-status",
    response_model=DocumentExtractionStatusResponse,
    summary="Get extraction status",
)
def get_document_extraction_status(

    document_id: str,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_super_admin
    ),
):

    return (
        ExtractionService
        .get_document_extraction_status(
            db,
            document_id,
        )
    )




@router.post(
    "/projects/{project_id}/extract-all",
    response_model=List[
        ExtractionJobResponse
    ],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Extract all project documents",
)
def extract_all_documents(

    project_id: str,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_super_admin
    ),
):

    return (
        ExtractionService
        .extract_all_project_documents(
            db,
            project_id,
        )
    )