import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.project import Project
from app.schemas.document import (
    DocumentResponse,
    DocumentStatus,
    DocumentType,
    DocumentUpdate,
    DocumentUploadFailure,
    DocumentUploadResult,
)
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.utils.file_utils import (
    delete_file_safely,
    detect_document_type,
    get_file_extension,
    get_mime_type_for_file,
    sanitize_filename,
    save_upload_file,
    validate_file_extension,
)
from app.utils.id_generator import generate_id


class DocumentService:
    @staticmethod
    def create_project(db: Session, project_in: ProjectCreate) -> Project:
        # Check if project name already exists
        existing = db.execute(
            select(Project).where(Project.name == project_in.name)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with name '{project_in.name}' already exists.",
            )

        project = Project(
            id=generate_id("proj"),
            name=project_in.name,
            description=project_in.description,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def get_project(db: Session, project_id: str) -> Project:
        project = db.execute(
            select(Project).where(Project.id == project_id)
        ).scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )
        return project

    @staticmethod
    def list_projects(
        db: Session, skip: int = 0, limit: int = 100
    ) -> Tuple[int, List[ProjectResponse]]:
        total = db.execute(select(func.count(Project.id))).scalar() or 0
        projects = (
            db.execute(
                select(Project)
                .order_by(Project.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            .scalars()
            .all()
        )

        results = []
        for p in projects:
            doc_count = db.execute(
                select(func.count(Document.id)).where(Document.project_id == p.id)
            ).scalar() or 0
            results.append(
                ProjectResponse(
                    id=p.id,
                    name=p.name,
                    description=p.description,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    document_count=doc_count,
                )
            )
        return total, results

    @staticmethod
    def delete_project(db: Session, project_id: str) -> bool:
        project = DocumentService.get_project(db, project_id)
        # Delete associated files on disk
        for doc in project.documents:
            delete_file_safely(Path(doc.file_path))

        db.delete(project)
        db.commit()
        return True

    @staticmethod
    async def upload_documents(
        db: Session,
        project_id: str,
        files: List[UploadFile],
        document_type: Optional[DocumentType] = None,
    ) -> DocumentUploadResult:
        # Validate project exists
        DocumentService.get_project(db, project_id)

        successful: List[DocumentResponse] = []
        failed: List[DocumentUploadFailure] = []

        project_upload_dir = Path(settings.UPLOAD_DIR) / project_id
        project_upload_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            orig_filename = file.filename or "unnamed_document"
            try:
                # 1. Validate extension
                ext = validate_file_extension(orig_filename)
                clean_name = sanitize_filename(orig_filename)

                # 2. Determine document type
                resolved_type = (
                    document_type.value
                    if document_type and document_type != DocumentType.OTHER
                    else detect_document_type(clean_name).value
                )

                # 3. Create unique file path
                doc_id = generate_id("doc")
                stored_filename = f"{doc_id}_{clean_name}"
                dest_path = project_upload_dir / stored_filename

                # 4. Save file & compute SHA-256
                file_size, sha256 = await save_upload_file(
                    upload_file=file,
                    dest_path=dest_path,
                    max_size_mb=settings.MAX_UPLOAD_SIZE_MB,
                )

                # 5. Create database record
                doc = Document(
                    id=doc_id,
                    project_id=project_id,
                    filename=orig_filename,
                    stored_filename=stored_filename,
                    file_path=str(dest_path),
                    file_type=ext.lstrip("."),
                    file_size=file_size,
                    document_type=resolved_type,
                    status=DocumentStatus.PENDING.value,
                    checksum_sha256=sha256,
                    metadata_json={
                        "content_type": file.content_type,
                        "relative_storage_path": f"{project_id}/{stored_filename}",
                    },
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)

                successful.append(DocumentResponse.model_validate(doc))

            except HTTPException as he:
                failed.append(
                    DocumentUploadFailure(
                        filename=orig_filename,
                        reason=he.detail,
                    )
                )
            except Exception as e:
                failed.append(
                    DocumentUploadFailure(
                        filename=orig_filename,
                        reason=f"Upload error: {str(e)}",
                    )
                )

        return DocumentUploadResult(successful=successful, failed=failed)

    @staticmethod
    def get_document(db: Session, document_id: str) -> Document:
        doc = db.execute(
            select(Document).where(Document.id == document_id)
        ).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )
        return doc

    @staticmethod
    def list_project_documents(
        db: Session,
        project_id: str,
        document_type: Optional[str] = None,
        doc_status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[int, List[Document]]:
        # Verify project exists
        DocumentService.get_project(db, project_id)

        query = select(Document).where(Document.project_id == project_id)
        count_query = select(func.count(Document.id)).where(
            Document.project_id == project_id
        )

        if document_type:
            query = query.where(Document.document_type == document_type)
            count_query = count_query.where(Document.document_type == document_type)

        if doc_status:
            query = query.where(Document.status == doc_status)
            count_query = count_query.where(Document.status == doc_status)

        total = db.execute(count_query).scalar() or 0
        documents = (
            db.execute(
                query.order_by(Document.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            .scalars()
            .all()
        )

        return total, list(documents)

    @staticmethod
    def update_document(
        db: Session, document_id: str, update_in: DocumentUpdate
    ) -> Document:
        doc = DocumentService.get_document(db, document_id)
        if update_in.document_type is not None:
            doc.document_type = update_in.document_type.value
        if update_in.status is not None:
            doc.status = update_in.status.value
        if update_in.metadata_json is not None:
            existing = doc.metadata_json or {}
            existing.update(update_in.metadata_json)
            doc.metadata_json = existing

        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def delete_document(db: Session, document_id: str) -> bool:
        doc = DocumentService.get_document(db, document_id)
        # Delete file from filesystem
        delete_file_safely(Path(doc.file_path))

        db.delete(doc)
        db.commit()
        return True

    @staticmethod
    def reprocess_document(db: Session, document_id: str) -> Document:
        doc = DocumentService.get_document(db, document_id)
        if not Path(doc.file_path).exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Original document file '{doc.filename}' is missing from storage.",
            )

        doc.status = DocumentStatus.PENDING.value
        doc.error_message = None
        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def get_document_file_path(
        db: Session, document_id: str
    ) -> Tuple[Path, str, str]:
        doc = DocumentService.get_document(db, document_id)
        file_path = Path(doc.file_path)
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original document file for '{doc.filename}' was not found on disk.",
            )
        mime_type = get_mime_type_for_file(file_path)
        return file_path, doc.filename, mime_type
