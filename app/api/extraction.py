from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_super_admin
from app.models.user import User
from app.schemas.record import (
    DocumentExtractionStatusResponse,
    ExtractionJobResponse,
)
from app.services.extraction_service import ExtractionService

router = APIRouter(tags=["Document Parsing & Extraction"])


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
