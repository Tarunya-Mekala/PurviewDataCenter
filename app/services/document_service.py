from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from collections import defaultdict
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.comparison_run import ComparisonRun
from app.models.document import Document
from app.models.extracted_record import ExtractedRecord
from app.models.project import Project
from app.models.record_review_action import RecordReviewAction
from app.models.vendor import Vendor
from app.schemas.document import (
    DocumentResponse,
    DocumentStatus,
    DocumentType,
    DocumentUpdate,
    DocumentUploadFailure,
    DocumentUploadResult,
)
from app.schemas.project import (
    ProjectCreate,
    ProjectDocumentCounts,
    ProjectLatestRunCounts,
    ProjectRecordCounts,
    ProjectResponse,
    ProjectUpdate,
)
from app.schemas.record import ReviewStatus
from app.utils.file_utils import (
    delete_file_safely,
    detect_document_type,
    detect_document_type_from_content,
    get_file_extension,
    get_mime_type_for_file,
    sanitize_filename,
    save_upload_file,
    validate_file_extension,
)
from app.utils.id_generator import generate_id


def record_to_values_dict(record: ExtractedRecord) -> dict:
    """Snapshot a record's current field values for audit history."""
    return {
        "record_type": record.record_type,
        "category": record.category,
        "part_number": record.part_number,
        "cleaned_part_number": record.cleaned_part_number,
        "model": record.model,
        "serial_number": record.serial_number,
        "condition": record.condition,
        "condition_notes": record.condition_notes,
        "description": record.description,
        "quantity": record.quantity,
        "unit": record.unit,
        "vendor": record.vendor,
        "manufacturer": record.manufacturer,
        "location": record.location,
        "rack": record.rack,
        "u_position": record.u_position,
        "power_kw": record.power_kw,
        "cable_length_m": record.cable_length_m,
        "source_device": record.source_device,
        "source_port": record.source_port,
        "target_device": record.target_device,
        "target_port": record.target_port,
        "cable_type": record.cable_type,
        "review_status": record.review_status,
        "review_notes": record.review_notes,
        "review_reason": record.review_reason,
        "unmapped_columns": record.unmapped_columns or [],
        "confidence_score": record.confidence_score,
    }


class DocumentService:
    @staticmethod
    def create_project(db: Session, project_in: ProjectCreate, creator_email: Optional[str] = None) -> Project:
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
            status="active",
            created_by=creator_email,
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
    def update_project(db: Session, project_id: str, project_in: ProjectUpdate) -> Project:
        project = DocumentService.get_project(db, project_id)
        if project_in.name is not None:
            project.name = project_in.name
        if project_in.description is not None:
            project.description = project_in.description
        if project_in.status is not None:
            project.status = project_in.status.lower().strip()
        project.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def _build_project_responses(
        db: Session, projects: List[Project]
    ) -> List[ProjectResponse]:
        if not projects:
            return []

        project_ids = [p.id for p in projects]

        # 1. Bulk load document counts grouped by project and status
        doc_counts_by_project = defaultdict(dict)
        doc_rows = db.execute(
            select(Document.project_id, Document.status, func.count(Document.id))
            .where(Document.project_id.in_(project_ids))
            .group_by(Document.project_id, Document.status)
        ).all()
        for pid, st, cnt in doc_rows:
            doc_counts_by_project[pid][st] = cnt

        # 2. Bulk load record counts (total and pending review) in a single query
        record_counts_by_project = {}
        rec_rows = db.execute(
            select(
                ExtractedRecord.project_id,
                func.count(ExtractedRecord.id),
                func.sum(
                    case(
                        (ExtractedRecord.review_status == ReviewStatus.PENDING_REVIEW.value, 1),
                        else_=0,
                    )
                ),
            )
            .where(
                ExtractedRecord.project_id.in_(project_ids),
                ExtractedRecord.is_deleted == False,
            )
            .group_by(ExtractedRecord.project_id)
        ).all()
        for pid, total_cnt, pending_cnt in rec_rows:
            record_counts_by_project[pid] = {
                "total": total_cnt or 0,
                "pending_review": pending_cnt or 0,
            }

        # 3. Bulk load vendor names for each project
        vendors_by_project = defaultdict(list)
        vendor_rows = db.execute(
            select(Vendor.project_id, Vendor.name)
            .where(Vendor.project_id.in_(project_ids))
            .order_by(Vendor.name.asc())
        ).all()
        for pid, vname in vendor_rows:
            if vname and vname not in vendors_by_project[pid]:
                vendors_by_project[pid].append(vname)

        # 4. Bulk load latest comparison run and counts for each project
        latest_runs_by_project = {}
        rn_subq = (
            select(
                ComparisonRun.id.label("run_id"),
                ComparisonRun.project_id,
                ComparisonRun.run_number,
                ComparisonRun.status,
                ComparisonRun.total_expected,
                ComparisonRun.total_found,
                ComparisonRun.matches_count,
                ComparisonRun.discrepancies_count,
                ComparisonRun.exceptions_count,
                ComparisonRun.started_at,
                ComparisonRun.finished_at,
                func.row_number()
                .over(
                    partition_by=ComparisonRun.project_id,
                    order_by=(ComparisonRun.run_number.desc(), ComparisonRun.started_at.desc()),
                )
                .label("rn"),
            )
            .where(ComparisonRun.project_id.in_(project_ids))
            .subquery()
        )
        run_rows = db.execute(select(rn_subq).where(rn_subq.c.rn == 1)).all()
        for row in run_rows:
            expected = float(row.total_expected or 0.0)
            matches = int(row.matches_count or 0)
            discrepancies = int(row.discrepancies_count or 0)
            exceptions = int(row.exceptions_count or 0)
            total_items = matches + discrepancies + exceptions

            if expected > 0:
                rate = round((matches / expected) * 100, 2)
            elif total_items > 0:
                rate = round((matches / total_items) * 100, 2)
            else:
                rate = 100.0 if row.status == "completed" else 0.0

            latest_runs_by_project[row.project_id] = ProjectLatestRunCounts(
                run_id=row.run_id,
                run_number=row.run_number,
                status=row.status or "completed",
                total_expected=expected,
                total_found=float(row.total_found or 0.0),
                matches_count=matches,
                discrepancies_count=discrepancies,
                exceptions_count=exceptions,
                match_rate_percentage=rate,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )

        # Build responses
        results = []
        for p in projects:
            p_doc_counts_dict = doc_counts_by_project.get(p.id, {})
            doc_counts = ProjectDocumentCounts(
                pending=p_doc_counts_dict.get("pending", 0),
                parsing=p_doc_counts_dict.get("parsing", 0),
                parsed=p_doc_counts_dict.get("parsed", 0),
                extracting=p_doc_counts_dict.get("extracting", 0),
                extracted=p_doc_counts_dict.get("extracted", 0),
                failed=p_doc_counts_dict.get("failed", 0),
            )
            p_rec_counts_dict = record_counts_by_project.get(p.id, {})
            rec_counts = ProjectRecordCounts(
                total=p_rec_counts_dict.get("total", 0),
                pending_review=p_rec_counts_dict.get("pending_review", 0),
            )
            v_list = vendors_by_project.get(p.id, [])
            l_run = latest_runs_by_project.get(p.id)

            results.append(
                ProjectResponse(
                    id=p.id,
                    name=p.name,
                    description=p.description,
                    status=p.status or "active",
                    owner_id=p.owner_id,
                    created_by=p.created_by,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    document_count=sum(p_doc_counts_dict.values()),
                    document_counts=doc_counts,
                    record_counts=rec_counts,
                    vendor_names=v_list,
                    vendors=v_list,
                    latest_run=l_run,
                    latest_run_counts=l_run,
                )
            )
        return results

    @staticmethod
    def get_project_response(db: Session, project_id: str) -> ProjectResponse:
        project = DocumentService.get_project(db, project_id)
        responses = DocumentService._build_project_responses(db, [project])
        return responses[0]

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
        results = DocumentService._build_project_responses(db, projects)
        return total, results

    @staticmethod
    def delete_project(db: Session, project_id: str, reviewer_email: Optional[str] = None) -> bool:
        project = DocumentService.get_project(db, project_id)
        # Problem 19: Soft delete all project records and create audit action entries
        docs = db.execute(select(Document).where(Document.project_id == project_id)).scalars().all()
        for doc in docs:
            records = db.execute(
                select(ExtractedRecord).where(
                    ExtractedRecord.document_id == doc.id,
                    ExtractedRecord.is_deleted == False,
                )
            ).scalars().all()
            for r in records:
                old_val = record_to_values_dict(r)
                r.is_deleted = True
                audit = RecordReviewAction(
                    id=generate_id("act_"),
                    record_id=r.id,
                    action="project_deleted",
                    old_values=old_val,
                    new_values=None,
                    reason=f"Project '{project.name}' deleted",
                    reviewer_id=reviewer_email or "system",
                )
                db.add(audit)
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
        source: str = "plan",
        vendor_id: Optional[str] = None,
        uploader_email: Optional[str] = None,
    ) -> DocumentUploadResult:
        # Validate project exists
        DocumentService.get_project(db, project_id)

        # Validate source and vendor_id
        source_clean = (source or "plan").lower().strip()
        if source_clean not in ["plan", "vendor"]:
            source_clean = "plan"

        # Refuse delivery on plan source
        doc_type_val = getattr(document_type, "value", document_type)
        if doc_type_val == "delivery" and source_clean == "plan":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Document type 'delivery' is for vendor side only; cannot be uploaded as plan source.",
            )

        if source_clean == "vendor":
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="vendor_id is required when source is 'vendor'",
                )
            from app.models.vendor import Vendor
            vendor = db.get(Vendor, vendor_id)
            if not vendor or vendor.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Vendor '{vendor_id}' not found in project '{project_id}'",
                )

        successful: List[DocumentResponse] = []
        failed: List[DocumentUploadFailure] = []

        project_upload_dir = Path(settings.UPLOAD_DIR) / project_id
        project_upload_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            orig_filename = file.filename or "unnamed_document"
            try:
                # Problem 24: Max upload limit check (50 MB)
                if file.size and file.size > 50 * 1024 * 1024:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File '{orig_filename}' exceeds maximum allowed limit of 50 MB.",
                    )

                # 1. Validate extension
                ext = validate_file_extension(orig_filename)
                clean_name = sanitize_filename(orig_filename)

                # 2. Create unique file path
                doc_id = generate_id("doc")
                stored_filename = f"{doc_id}_{clean_name}"
                dest_path = project_upload_dir / stored_filename

                # 3. Save file & compute SHA-256
                file_size, sha256 = await save_upload_file(
                    upload_file=file,
                    dest_path=dest_path,
                    max_size_mb=50,
                )

                # 4. Determine document type (explicit or auto-detect from content/filename)
                if document_type and document_type != DocumentType.OTHER:
                    resolved_type = getattr(document_type, "value", document_type)
                else:
                    resolved_type = detect_document_type_from_content(dest_path, clean_name).value

                # Delivery documents are vendor-side only
                if resolved_type == "delivery" and source_clean == "plan":
                    delete_file_safely(dest_path)
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Document type 'delivery' is for vendor side only; cannot be uploaded as plan source.",
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
                    source=source_clean,
                    vendor_id=vendor_id if source_clean == "vendor" else None,
                    version=1,
                    uploaded_by=uploader_email,
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
                if he.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY and "delivery" in str(he.detail).lower():
                    raise he
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
        if successful:
            try:
                from app.api.audit import record_audit_log
                record_audit_log(
                    db=db,
                    action="upload",
                    resource_type="document",
                    project_id=project_id,
                    details={
                        "count": len(successful),
                        "files": [d.filename for d in successful],
                    },
                )
            except Exception:
                pass

        return DocumentUploadResult(successful=successful, failed=failed)

    @staticmethod
    def process_document_after_upload(document_id: str) -> None:
        """Problem 17: Background worker parses document from pending -> parsing -> parsed."""
        from app.core.database import SessionLocal
        with SessionLocal() as db:
            doc = db.get(Document, document_id)
            if not doc or doc.status not in [DocumentStatus.PENDING.value, DocumentStatus.PARSING.value]:
                return
            doc.status = DocumentStatus.PARSING.value
            db.commit()
            try:
                file_path = Path(doc.file_path)
                if not file_path.exists():
                    doc.status = DocumentStatus.FAILED.value
                    doc.error_message = f"File missing from disk storage: {doc.file_path}"
                    db.commit()
                    return

                doc.status = DocumentStatus.PARSED.value
                doc.error_message = None
                db.commit()
            except Exception as e:
                doc.status = DocumentStatus.FAILED.value
                doc.error_message = f"Parsing error: {str(e)}"
                db.commit()

    @staticmethod
    async def replace_document(
        db: Session,
        document_id: str,
        file: UploadFile,
        uploader_email: Optional[str] = None,
    ) -> Document:
        """Problem 26: Replace document file in place, increment version, reset to pending."""
        doc = DocumentService.get_document(db, document_id)
        orig_filename = file.filename or doc.filename
        ext = validate_file_extension(orig_filename)
        clean_name = sanitize_filename(orig_filename)

        if file.size and file.size > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{orig_filename}' exceeds maximum allowed limit of 50 MB.",
            )

        project_upload_dir = Path(settings.UPLOAD_DIR) / doc.project_id
        project_upload_dir.mkdir(parents=True, exist_ok=True)

        new_version = (doc.version or 1) + 1
        stored_filename = f"{doc.id}_v{new_version}_{clean_name}"
        dest_path = project_upload_dir / stored_filename

        file_size, sha256 = await save_upload_file(
            upload_file=file,
            dest_path=dest_path,
            max_size_mb=50,
        )

        doc.filename = orig_filename
        doc.stored_filename = stored_filename
        doc.file_path = str(dest_path)
        doc.file_type = ext.lstrip(".")
        doc.file_size = file_size
        doc.checksum_sha256 = sha256
        doc.version = new_version
        doc.status = DocumentStatus.PENDING.value
        doc.error_message = None
        if uploader_email:
            doc.uploaded_by = uploader_email

        db.commit()
        db.refresh(doc)

        try:
            from app.api.audit import record_audit_log
            record_audit_log(
                db=db,
                action="upload",
                resource_type="document",
                resource_id=doc.id,
                project_id=doc.project_id,
                details={"filename": doc.filename, "version": doc.version, "action": "replace"},
            )
        except Exception:
            pass

        return doc

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
        target_type = (
            getattr(update_in.document_type, "value", update_in.document_type)
            if update_in.document_type is not None
            else doc.document_type
        )
        target_source = (
            update_in.source.lower().strip()
            if update_in.source is not None
            else doc.source
        )
        if target_type == "delivery" and target_source == "plan":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Document type 'delivery' is for vendor side only; cannot be associated with plan source.",
            )

        if update_in.document_type is not None:
            doc.document_type = target_type
        if update_in.source is not None:
            doc.source = target_source
        if update_in.vendor_id is not None:
            doc.vendor_id = update_in.vendor_id
        if update_in.status is not None:
            doc.status = getattr(update_in.status, "value", update_in.status)
        if update_in.metadata_json is not None:
            existing = doc.metadata_json or {}
            existing.update(update_in.metadata_json)
            doc.metadata_json = existing

        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def delete_document(db: Session, document_id: str, reviewer_email: Optional[str] = None) -> bool:
        """Problem 19: Deleting a document removes (soft delete) its records and writes history."""
        doc = DocumentService.get_document(db, document_id)
        records = db.execute(
            select(ExtractedRecord).where(
                ExtractedRecord.document_id == document_id,
                ExtractedRecord.is_deleted == False,
            )
        ).scalars().all()

        for r in records:
            old_val = record_to_values_dict(r)
            r.is_deleted = True
            audit = RecordReviewAction(
                id=generate_id("act_"),
                record_id=r.id,
                action="document_deleted",
                old_values=old_val,
                new_values=None,
                reason=f"Document '{doc.filename}' deleted",
                reviewer_id=reviewer_email or "system",
            )
            db.add(audit)

        delete_file_safely(Path(doc.file_path))
        db.delete(doc)
        db.commit()
        return True

    @staticmethod
    def reprocess_document(db: Session, document_id: str) -> Document:
        doc = DocumentService.get_document(db, document_id)
        # Ensure file actually exists in storage
        DocumentService.get_document_file_path(db, document_id)

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
            # Fallback relative to current settings.UPLOAD_DIR
            alt_path = Path(settings.UPLOAD_DIR) / doc.project_id / doc.stored_filename
            if alt_path.exists():
                file_path = alt_path
            else:
                matches = list(Path(settings.UPLOAD_DIR).glob(f"**/{doc.stored_filename}"))
                if matches:
                    file_path = matches[0]
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Original document file for '{doc.filename}' was not found on disk.",
                    )
        mime_type = get_mime_type_for_file(file_path)
        return file_path, doc.filename, mime_type
