from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_super_admin, verify_evidence_token
from app.models.user import User
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentType,
    DocumentUpdate,
    DocumentUploadResult,
)
from app.services.document_service import DocumentService

router = APIRouter(tags=["Documents"], dependencies=[Depends(get_current_super_admin)])


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentUploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload documents to a project",
    description="Upload one or multiple documents (BOM, Purchase/P2P, Rack Layout, Power, Cable, etc.) to a project. Maximum file size: 50 MB per file. Accepted types: .xlsx, .xls, .xlsm, .csv, .tsv, .pdf, .docx, .png, .jpg, .jpeg, .tiff.",
)
async def upload_documents(
    project_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(
        ...,
        description="Select one or more files to upload (Excel, CSV, PDF, Word, etc.)",
    ),
    document_type: Optional[DocumentType] = Form(
        None,
        description="Explicit document category. If omitted, will be auto-detected.",
    ),
    source: str = Form(
        "plan",
        description="Document source side: 'plan' (expected) or 'vendor' (delivered)",
    ),
    vendor_id: Optional[str] = Form(
        None,
        description="Vendor ID associated with this delivery document (required when source is 'vendor')",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided for upload.",
        )
    result = await DocumentService.upload_documents(
        db=db,
        project_id=project_id,
        files=files,
        document_type=document_type,
        source=source,
        vendor_id=vendor_id,
        uploader_email=current_user.email,
    )
    # Trigger background parsing so documents move from pending -> parsing -> parsed
    for doc in result.successful:
        background_tasks.add_task(DocumentService.process_document_after_upload, doc.id)

    return result


@router.post(
    "/projects/{project_id}/documents/batch",
    response_model=DocumentUploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Batch upload multiple documents to a project",
    description="Upload multiple documents simultaneously (alias to /documents).",
    include_in_schema=False,
)
async def batch_upload_documents(
    project_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="Select one or more files to upload"),
    document_type: Optional[DocumentType] = Form(
        None,
        description="Explicit document category. If omitted, will be auto-detected.",
    ),
    source: str = Form("plan", description="'plan' or 'vendor'"),
    vendor_id: Optional[str] = Form(None, description="Vendor ID if source is vendor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided for batch upload.",
        )
    result = await DocumentService.upload_documents(
        db=db,
        project_id=project_id,
        files=files,
        document_type=document_type,
        source=source,
        vendor_id=vendor_id,
        uploader_email=current_user.email,
    )
    for doc in result.successful:
        background_tasks.add_task(DocumentService.process_document_after_upload, doc.id)
    return result


@router.put(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Replace document file in place",
    description="Upload a new revision for a document. Keeps the same document ID, increments version (+1), resets status to pending, and triggers re-parsing.",
)
async def replace_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Replacement document file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    doc = await DocumentService.replace_document(
        db=db,
        document_id=document_id,
        file=file,
        uploader_email=current_user.email,
    )
    background_tasks.add_task(DocumentService.process_document_after_upload, doc.id)
    return DocumentResponse.model_validate(doc)


@router.get(
    "/projects/{project_id}/documents",
    response_model=DocumentListResponse,
    summary="List documents for a project",
    description="Retrieve all uploaded documents for a project with optional filtering by type or status.",
)
def list_documents(
    project_id: str,
    document_type: Optional[str] = Query(None, description="Filter by document type (bom, purchase, rack_layout, etc.)"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Limit for pagination"),
    db: Session = Depends(get_db),
):
    total, documents = DocumentService.list_project_documents(
        db=db,
        project_id=project_id,
        document_type=document_type,
        doc_status=status,
        skip=skip,
        limit=limit,
    )
    return DocumentListResponse(
        total=total,
        items=[DocumentResponse.model_validate(doc) for doc in documents],
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
    description="Fetch document metadata, parsing state, and file properties.",
)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    doc = DocumentService.get_document(db, document_id)
    return DocumentResponse.model_validate(doc)


@router.get(
    "/documents/{document_id}/download",
    summary="Download original document",
    description="Download the raw source file for the specified document ID.",
)
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    file_path, filename, mime_type = DocumentService.get_document_file_path(db, document_id)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=mime_type,
    )


@router.get(
    "/documents/{document_id}/evidence-image",
    summary="Serve short-lived signed document image preview",
    description="Securely serve document page or image evidence via short-lived signed token without public directory exposure.",
)
def get_document_evidence_image(
    document_id: str,
    token: str = Query(..., description="Short-lived HMAC/JWT evidence token"),
    db: Session = Depends(get_db),
):
    verified_doc_id = verify_evidence_token(token)
    if verified_doc_id != document_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token mismatch for requested document")
    file_path, filename, mime_type = DocumentService.get_document_file_path(db, document_id)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=mime_type,
    )


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Update document metadata",
    description="Update document category (e.g. reclassify BOM to P2P) or metadata.",
)
def update_document(
    document_id: str,
    update_in: DocumentUpdate,
    db: Session = Depends(get_db),
):
    doc = DocumentService.update_document(db, document_id, update_in)
    return DocumentResponse.model_validate(doc)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="Permanently delete a document record, remove source file from disk, soft-delete its records, and write an audit history entry per record.",
)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    DocumentService.delete_document(db, document_id, reviewer_email=current_user.email)
    return None


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentResponse,
    summary="Reprocess a document",
    description="Reset a document's status to pending to trigger re-parsing or re-extraction.",
)
def reprocess_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    doc = DocumentService.reprocess_document(db, document_id)
    return DocumentResponse.model_validate(doc)
