from typing import List, Optional

from fastapi import (
    APIRouter,
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
from app.core.security import get_current_super_admin
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
    description="Upload one or multiple documents (BOM, P2P, Rack Layout, Power, Cable, etc.) to a project.",
)
async def upload_documents(
    project_id: str,
    files: List[UploadFile] = File(..., description="One or more files to upload"),
    document_type: Optional[DocumentType] = Form(
        None,
        description="Explicit document category. If omitted, will be auto-detected.",
    ),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided for upload.",
        )
    return await DocumentService.upload_documents(
        db=db,
        project_id=project_id,
        files=files,
        document_type=document_type,
    )


@router.get(
    "/projects/{project_id}/documents",
    response_model=DocumentListResponse,
    summary="List all documents in a project",
    description="Retrieve all documents associated with a project, with optional filtering by type and processing status.",
)
def list_project_documents(
    project_id: str,
    document_type: Optional[DocumentType] = Query(None, description="Filter by document type"),
    doc_status: Optional[DocumentStatus] = Query(None, alias="status", description="Filter by status"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Limit for pagination"),
    db: Session = Depends(get_db),
):
    total, docs = DocumentService.list_project_documents(
        db=db,
        project_id=project_id,
        document_type=document_type.value if document_type else None,
        doc_status=doc_status.value if doc_status else None,
        skip=skip,
        limit=limit,
    )
    return DocumentListResponse(
        total=total,
        items=[DocumentResponse.model_validate(d) for d in docs],
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details and status",
    description="Retrieve metadata, checksum, file size, and processing status of a specific document.",
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
    description="Permanently delete a document record and its stored file from disk.",
)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    DocumentService.delete_document(db, document_id)
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
