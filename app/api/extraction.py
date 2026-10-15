from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_super_admin
from app.models.user import User
from app.schemas.record import (
    AIExtractionRequest,
    BatchReviewRequest,
    DocumentExtractionStatusResponse,
    ExtractedRecordCreate,
    ExtractedRecordResponse,
    ExtractedRecordReview,
    ExtractedRecordUpdate,
    ExtractionJobResponse,
    RawTextExtractionRequest,
    RecordListResponse,
    RecordType,
    ReviewStatus,
    ReviewSummaryResponse,
)
from app.services.extraction_service import ExtractionService

router = APIRouter(tags=["Extraction & Human Review"])


# ---------------------------------------------------------
# AI Status & Model Inspection
# ---------------------------------------------------------

@router.get(
    "/ai/status",
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
    return {
        "ollama_online": is_online,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "configured_model": settings.LLM_MODEL,
        "installed_models": models,
        "recommended_model": "qwen2.5:27b",
    }


# ---------------------------------------------------------
# Extraction Pipeline Triggers
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
# Extracted Records Queries
# ---------------------------------------------------------

@router.get(
    "/projects/{project_id}/records",
    response_model=RecordListResponse,
    summary="List extracted records for a project",
    description="Retrieve all extracted records for human review, with filters for review status, category, vendor, and keyword search.",
)
def list_project_records(
    project_id: str,
    document_id: Optional[str] = Query(None, description="Filter by specific document ID"),
    review_status: Optional[ReviewStatus] = Query(None, description="Filter by review status"),
    record_type: Optional[RecordType] = Query(None, description="Filter by record category"),
    vendor: Optional[str] = Query(None, description="Filter by manufacturer/vendor"),
    search: Optional[str] = Query(None, description="Search part number, description, vendor, or rack location"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Limit for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    total, records = ExtractionService.list_records(
        db=db,
        project_id=project_id,
        document_id=document_id,
        review_status=review_status.value if review_status else None,
        record_type=record_type.value if record_type else None,
        vendor=vendor,
        search=search,
        skip=skip,
        limit=limit,
    )
    return RecordListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[ExtractedRecordResponse.model_validate(r) for r in records],
    )


@router.get(
    "/documents/{document_id}/records",
    response_model=RecordListResponse,
    summary="List extracted records for a document",
    description="Retrieve all records extracted from a specific document.",
)
def list_document_records(
    document_id: str,
    review_status: Optional[ReviewStatus] = Query(None, description="Filter by review status"),
    record_type: Optional[RecordType] = Query(None, description="Filter by record category"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Limit for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    from app.services.document_service import DocumentService
    doc = DocumentService.get_document(db, document_id)

    total, records = ExtractionService.list_records(
        db=db,
        project_id=doc.project_id,
        document_id=document_id,
        review_status=review_status.value if review_status else None,
        record_type=record_type.value if record_type else None,
        skip=skip,
        limit=limit,
    )
    return RecordListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[ExtractedRecordResponse.model_validate(r) for r in records],
    )


@router.get(
    "/records/{record_id}",
    response_model=ExtractedRecordResponse,
    summary="Get single extracted record details",
    description="Retrieve full record information, raw extracted metadata, confidence score, and review history.",
)
def get_record_detail(
    record_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    rec = ExtractionService.get_record(db, record_id)
    return ExtractedRecordResponse.model_validate(rec)


# ---------------------------------------------------------
# Human Review & Verification Actions
# ---------------------------------------------------------

@router.post(
    "/records/{record_id}/review",
    response_model=ExtractedRecordResponse,
    summary="Submit human review decision",
    description="Approve, reject, or mark a record as modified, with optional field corrections and feedback notes.",
)
def review_record(
    record_id: str,
    review_data: ExtractedRecordReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    rec = ExtractionService.review_record(
        db=db,
        record_id=record_id,
        review_data=review_data,
        reviewer_email=current_user.email,
    )
    return ExtractedRecordResponse.model_validate(rec)


@router.patch(
    "/records/{record_id}",
    response_model=ExtractedRecordResponse,
    summary="Edit / correct extracted record",
    description="Update part number, quantity, vendor, or connection fields on an extracted record.",
)
def update_record(
    record_id: str,
    update_data: ExtractedRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    rec = ExtractionService.update_record(
        db=db,
        record_id=record_id,
        update_data=update_data,
        reviewer_email=current_user.email,
    )
    return ExtractedRecordResponse.model_validate(rec)


@router.post(
    "/projects/{project_id}/records/batch-review",
    summary="Batch approve or reject records",
    description="Review multiple records simultaneously (e.g. bulk approval).",
)
def batch_review_records(
    project_id: str,
    request: BatchReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    updated_count = ExtractionService.batch_review(
        db=db,
        project_id=project_id,
        request=request,
        reviewer_email=current_user.email,
    )
    return {
        "project_id": project_id,
        "action": request.action.value,
        "records_reviewed": updated_count,
        "status": "success",
    }


@router.post(
    "/documents/{document_id}/records",
    response_model=ExtractedRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add an extracted record",
    description="Add a missing hardware or cable line item directly into the document review set.",
)
def add_manual_record(
    document_id: str,
    create_data: ExtractedRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    rec = ExtractionService.create_manual_record(
        db=db,
        document_id=document_id,
        create_data=create_data,
        reviewer_email=current_user.email,
    )
    return ExtractedRecordResponse.model_validate(rec)


@router.delete(
    "/records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an extracted record",
    description="Remove an invalid or duplicated record from the project review set.",
)
def delete_record(
    record_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    ExtractionService.delete_record(db, record_id)
    return None


# ---------------------------------------------------------
# Human Review Progress & Metrics
# ---------------------------------------------------------

@router.get(
    "/projects/{project_id}/review-summary",
    response_model=ReviewSummaryResponse,
    summary="Get human review progress summary",
    description="Provides completion percentage, counts of pending vs approved vs modified vs rejected records, and breakdown by vendor.",
)
def get_project_review_summary(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ExtractionService.get_review_summary(db, project_id)
