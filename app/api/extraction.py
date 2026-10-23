from typing import List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    Response,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    get_current_super_admin,
)

from app.models.user import User

from app.schemas.record import (
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
    current_user: User = Depends(
        get_current_super_admin
    ),
):

    from app.core.config import settings
    from app.ai.llm import llm_client

    available = llm_client.is_available()

    return {

        "status": "online" if available else "offline",

        "available": available,

        "reachable": available,

        "provider": (
            settings.LLM_PROVIDER
        ),

        "configured_model": (
            settings.LLM_MODEL
        ),

        "temperature": (
            settings.LLM_TEMPERATURE
        ),
         "api_base_url": settings.LLM_BASE_URL,
    }


@router.post(
    "/documents/{document_id}/extract",
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured records",
)
def extract_document(

    document_id: str,

    background_tasks: BackgroundTasks,

    response: Response,

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

    if use_ai:
        response.status_code = status.HTTP_202_ACCEPTED
        return ExtractionService.queue_document_ai_extraction(
            db,
            document_id,
            background_tasks,
            model=model,
        )
    return ExtractionService.extract_document(
        db,
        document_id,
        use_ai=False,
        model=model,
    )


@router.post(
    "/documents/{document_id}/extract-ai",
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
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

    background_tasks: BackgroundTasks,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_super_admin
    ),
):

    return (
        ExtractionService
        .queue_document_ai_extraction(
            db,
            document_id,
            background_tasks,
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
    "/extract/ai-snippet",
    summary="Extract records from raw text",
)
def extract_snippet_ai(

    request: RawTextExtractionRequest,

    current_user: User = Depends(
        get_current_super_admin
    ),
):

    return (
        ExtractionService
        .extract_raw_snippet_with_ai(

            text=request.text,

            document_type=(
                request.document_type
                or "bom"
            ),

            model=request.model,
        )
    )


@router.post(
    "/projects/{project_id}/extract-all",
    response_model=List[
        ExtractionJobResponse
    ],
    status_code=status.HTTP_200_OK,
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