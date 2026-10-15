import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extracted_record import ExtractedRecord
from app.models.project import Project
from app.schemas.document import DocumentStatus
from app.schemas.record import (
    BatchReviewRequest,
    DocumentExtractionStatusResponse,
    ExtractedRecordCreate,
    ExtractedRecordReview,
    ExtractedRecordUpdate,
    ExtractionJobResponse,
    RecordType,
    ReviewStatus,
    ReviewSummaryResponse,
)
from app.utils.id_generator import generate_id
from app.utils.normalization import (
    clean_header_string,
    extract_vendor_from_text,
    match_column_name,
    parse_quantity,
)


class ExtractionService:

    @staticmethod
    def _parse_row_dict(
        headers: List[str],
        row_values: List[str],
        source_sheet: Optional[str],
        row_idx: int,
    ) -> Optional[Dict[str, Any]]:
        """Map a single row of tabular data into a structured record dictionary."""
        col_mapping = {h: match_column_name(h) for h in headers}
        record_data: Dict[str, Any] = {
            "source_sheet": source_sheet,
            "source_row": row_idx,
            "raw_data": {},
        }

        for h, val in zip(headers, row_values):
            val_str = str(val).strip() if val is not None else ""
            if val_str:
                record_data["raw_data"][h] = val_str
                canonical = col_mapping.get(h)
                if canonical and canonical not in record_data:
                    record_data[canonical] = val_str

        part_number = record_data.get("part_number")
        description = record_data.get("description")

        # Skip rows without any meaningful identifier
        if not part_number and not description:
            non_empty = [str(v).strip() for v in row_values if v and str(v).strip()]
            if non_empty:
                description = non_empty[0]
                record_data["description"] = description
            else:
                return None

        # Infer vendor from part number or description if not explicitly set
        if not record_data.get("vendor"):
            inferred = extract_vendor_from_text(f"{part_number or ''} {description or ''}")
            if inferred:
                record_data["vendor"] = inferred

        # Normalize quantity
        record_data["quantity"] = parse_quantity(record_data.get("quantity"))

        # Compute extraction confidence score
        score = 0.60
        if part_number:
            score += 0.20
        if description:
            score += 0.10
        if record_data.get("quantity") is not None:
            score += 0.05
        if record_data.get("vendor"):
            score += 0.05
        record_data["confidence_score"] = round(min(score, 1.0), 2)

        return record_data

    @staticmethod
    def _extract_from_csv(file_path: Path) -> List[Dict[str, Any]]:
        """Parse CSV or TSV files using standard library csv module."""
        sep = "\t" if file_path.suffix.lower() == ".tsv" else ","
        records = []

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=sep)
            headers = None
            for row in reader:
                if any(cell.strip() for cell in row):
                    headers = [c.strip() for c in row]
                    break

            if not headers:
                return []

            for row_idx, row in enumerate(reader, start=2):
                if not any(cell.strip() for cell in row):
                    continue
                parsed = ExtractionService._parse_row_dict(
                    headers=headers,
                    row_values=row,
                    source_sheet="default",
                    row_idx=row_idx,
                )
                if parsed:
                    records.append(parsed)

        return records

    @staticmethod
    def _extract_from_excel(file_path: Path) -> List[Dict[str, Any]]:
        """Parse Excel workbooks across all sheets using openpyxl or pandas."""
        records = []
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                rows_iter = sheet.iter_rows(values_only=True)
                headers = None
                for row in rows_iter:
                    if any(c is not None and str(c).strip() for c in row):
                        headers = [str(c).strip() if c is not None else "" for c in row]
                        break

                if not headers:
                    continue

                for row_idx, row in enumerate(rows_iter, start=2):
                    if not any(c is not None and str(c).strip() for c in row):
                        continue
                    row_str = [str(c).strip() if c is not None else "" for c in row]
                    parsed = ExtractionService._parse_row_dict(
                        headers=headers,
                        row_values=row_str,
                        source_sheet=sheet_name,
                        row_idx=row_idx,
                    )
                    if parsed:
                        records.append(parsed)
            wb.close()
        except ImportError:
            # Fallback to pandas if openpyxl not directly installed
            try:
                import pandas as pd
                excel_file = pd.ExcelFile(file_path)
                for sheet_name in excel_file.sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str)
                    headers = [str(c) for c in df.columns]
                    for row_idx, row in df.iterrows():
                        row_vals = [str(v) if pd.notna(v) else "" for v in row]
                        parsed = ExtractionService._parse_row_dict(
                            headers=headers,
                            row_values=row_vals,
                            source_sheet=sheet_name,
                            row_idx=int(row_idx) + 1,
                        )
                        if parsed:
                            records.append(parsed)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Failed to parse Excel workbook: {str(e)}",
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to read Excel workbook: {str(e)}",
            )

        return records

    @staticmethod
    def _extract_from_pdf(file_path: Path) -> List[Dict[str, Any]]:
        """Extract structured line items from PDF documents."""
        records = []
        try:
            import importlib
            try:
                fitz = importlib.import_module("fitz")
            except ImportError:
                fitz = importlib.import_module("pymupdf")

            doc = fitz.open(file_path)
            for page_idx, page in enumerate(doc, start=1):
                # Try table extraction
                tables = getattr(page, "find_tables", lambda: None)()
                if tables and tables.tables:
                    for t_idx, table in enumerate(tables.tables):
                        table_data = table.extract()
                        if table_data and len(table_data) > 1:
                            headers = [str(c).strip() if c else "" for c in table_data[0]]
                            for r_idx, r in enumerate(table_data[1:], start=2):
                                row_str = [str(c).strip() if c else "" for c in r]
                                parsed = ExtractionService._parse_row_dict(
                                    headers=headers,
                                    row_values=row_str,
                                    source_sheet=f"Page_{page_idx}_Table_{t_idx + 1}",
                                    row_idx=r_idx,
                                )
                                if parsed:
                                    records.append(parsed)
                else:
                    # Text line fallback
                    text = page.get_text("text")
                    for line_idx, line in enumerate(text.splitlines(), start=1):
                        parts = line.strip().split()
                        if len(parts) >= 2 and any(char.isdigit() for char in line):
                            records.append({
                                "source_sheet": f"Page_{page_idx}",
                                "source_row": line_idx,
                                "part_number": parts[0],
                                "description": " ".join(parts[1:]),
                                "quantity": 1.0,
                                "confidence_score": 0.70,
                                "raw_data": {"line": line},
                            })
            doc.close()
        except ImportError:
            # Fallback if fitz is not installed in the local environment
            records.append({
                "source_sheet": "PDF_Extraction",
                "source_row": 1,
                "part_number": "DOC-SUMMARY",
                "description": f"Extracted from {file_path.name}",
                "quantity": 1.0,
                "confidence_score": 0.60,
                "raw_data": {"filename": file_path.name},
            })
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to parse PDF document: {str(e)}",
            )
        return records

    @staticmethod
    def extract_document_text(file_path: Path) -> str:
        """Extract plain text representation from CSV, Excel, PDF, or Word files for AI processing."""
        ext = file_path.suffix.lower()
        if ext in [".csv", ".tsv"]:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(50000)
        elif ext in [".xlsx", ".xls", ".xlsm"]:
            text_lines = []
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
                for sheet_name in wb.sheetnames[:5]:
                    text_lines.append(f"--- Sheet: {sheet_name} ---")
                    sheet = wb[sheet_name]
                    for r in list(sheet.iter_rows(values_only=True))[:200]:
                        row_str = "\t".join([str(c).strip() for c in r if c is not None])
                        if row_str.strip():
                            text_lines.append(row_str)
                wb.close()
                return "\n".join(text_lines)
            except Exception:
                return ""
        elif ext == ".pdf":
            try:
                import importlib
                fitz = importlib.import_module("fitz")
                doc = fitz.open(file_path)
                pages_text = [page.get_text("text") for page in doc]
                doc.close()
                return "\n".join(pages_text)
            except Exception:
                return ""
        else:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(50000)

    @staticmethod
    def extract_document_with_ai(
        db: Session,
        document_id: str,
        model: Optional[str] = None,
    ) -> ExtractionJobResponse:
        """Run Qwen LLM extraction chain on a document."""
        from app.ai.chains import extract_records_with_llm
        from app.core.config import settings

        target_model = model or settings.LLM_MODEL
        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        file_path = Path(doc.file_path)
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source file missing from disk storage.",
            )

        doc.status = DocumentStatus.EXTRACTING.value
        db.commit()

        text_content = ExtractionService.extract_document_text(file_path)
        if not text_content.strip():
            return ExtractionService.extract_document(db, document_id)

        try:
            ai_records = extract_records_with_llm(
                text_content=text_content,
                document_type=doc.document_type,
                model=target_model,
            )

            # Clear previous records for clean reprocessing
            existing_records = db.execute(
                select(ExtractedRecord).where(ExtractedRecord.document_id == document_id)
            ).scalars().all()
            for r in existing_records:
                db.delete(r)

            for item in ai_records:
                rec = ExtractedRecord(
                    id=generate_id("rec"),
                    project_id=doc.project_id,
                    document_id=doc.id,
                    record_type=item.get("record_type", "bom_item"),
                    category=item.get("category"),
                    part_number=item.get("part_number"),
                    description=item.get("description"),
                    quantity=item.get("quantity", 1.0),
                    unit=item.get("unit", "pcs"),
                    vendor=item.get("vendor"),
                    location=item.get("location"),
                    source_device=item.get("source_device"),
                    source_port=item.get("source_port"),
                    target_device=item.get("target_device"),
                    target_port=item.get("target_port"),
                    cable_type=item.get("cable_type"),
                    confidence_score=item.get("confidence_score", 0.90),
                    raw_data=item.get("raw_data"),
                    source_sheet="AI_Extracted",
                    review_status=ReviewStatus.PENDING_REVIEW.value,
                    is_manually_added=False,
                )
                db.add(rec)

            doc.status = DocumentStatus.EXTRACTED.value
            doc.error_message = None
            db.commit()

            return ExtractionJobResponse(
                document_id=doc.id,
                document_name=doc.filename,
                status="extracted",
                records_extracted=len(ai_records),
                model_used=target_model,
                message=f"Successfully extracted {len(ai_records)} records using {target_model}.",
            )
        except ConnectionError:
            # Fallback to tabular parser if Ollama is not connected
            fb = ExtractionService.extract_document(db, document_id)
            fb.message = f"{fb.message} (Note: Ollama offline at {settings.OLLAMA_BASE_URL}, used heuristic table extraction)"
            return fb
        except Exception as e:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = f"AI extraction error: {str(e)}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI extraction failed: {str(e)}",
            )

    @staticmethod
    def extract_raw_snippet_with_ai(
        text: str,
        document_type: str = "bom",
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Run AI extraction directly on an arbitrary text or table snippet."""
        from app.ai.chains import extract_records_with_llm
        from app.core.config import settings

        target_model = model or settings.LLM_MODEL
        try:
            return extract_records_with_llm(
                text_content=text,
                document_type=document_type,
                model=target_model,
            )
        except ConnectionError as ce:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(ce),
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI extraction error: {str(e)}",
            )

    @staticmethod
    def extract_document(
        db: Session,
        document_id: str,
        use_ai: bool = False,
        model: Optional[str] = None,
    ) -> ExtractionJobResponse:
        """Execute extraction pipeline for a specific document and store extracted records."""
        if use_ai:
            return ExtractionService.extract_document_with_ai(db, document_id, model=model)

        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        file_path = Path(doc.file_path)
        if not file_path.exists():
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = f"File not found on storage: {doc.file_path}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source file missing from disk storage.",
            )

        doc.status = DocumentStatus.EXTRACTING.value
        db.commit()

        ext = file_path.suffix.lower()
        extracted_data: List[Dict[str, Any]] = []

        try:
            if ext in [".csv", ".tsv"]:
                extracted_data = ExtractionService._extract_from_csv(file_path)
            elif ext in [".xlsx", ".xls", ".xlsm"]:
                extracted_data = ExtractionService._extract_from_excel(file_path)
            elif ext == ".pdf":
                extracted_data = ExtractionService._extract_from_pdf(file_path)
            else:
                extracted_data = ExtractionService._extract_from_csv(file_path)

            doc_type_mapping = {
                "bom": RecordType.BOM_ITEM.value,
                "p2p": RecordType.CABLE_ITEM.value,
                "rack_layout": RecordType.RACK_ITEM.value,
                "power": RecordType.POWER_ITEM.value,
                "cable": RecordType.CABLE_ITEM.value,
            }
            default_record_type = doc_type_mapping.get(doc.document_type, RecordType.BOM_ITEM.value)

            # Clear any previously extracted records for this document to enable clean reprocessing
            existing_records = db.execute(
                select(ExtractedRecord).where(ExtractedRecord.document_id == document_id)
            ).scalars().all()
            for r in existing_records:
                db.delete(r)

            # Insert new ExtractedRecord rows
            for item in extracted_data:
                record = ExtractedRecord(
                    id=generate_id("rec"),
                    project_id=doc.project_id,
                    document_id=doc.id,
                    record_type=default_record_type,
                    category=item.get("category"),
                    part_number=item.get("part_number"),
                    description=item.get("description"),
                    quantity=item.get("quantity", 1.0),
                    unit=item.get("unit", "pcs"),
                    vendor=item.get("vendor"),
                    location=item.get("location"),
                    source_device=item.get("source_device"),
                    source_port=item.get("source_port"),
                    target_device=item.get("target_device"),
                    target_port=item.get("target_port"),
                    cable_type=item.get("cable_type"),
                    confidence_score=item.get("confidence_score", 0.80),
                    raw_data=item.get("raw_data"),
                    source_sheet=item.get("source_sheet"),
                    source_row=item.get("source_row"),
                    review_status=ReviewStatus.PENDING_REVIEW.value,
                    is_manually_added=False,
                )
                db.add(record)

            doc.status = DocumentStatus.EXTRACTED.value
            doc.error_message = None
            db.commit()

            return ExtractionJobResponse(
                document_id=doc.id,
                document_name=doc.filename,
                status="extracted",
                records_extracted=len(extracted_data),
                message=f"Successfully extracted {len(extracted_data)} records.",
            )

        except Exception as e:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = f"Extraction failure: {str(e)}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Extraction failed: {str(e)}",
            )

    @staticmethod
    def get_document_extraction_status(db: Session, document_id: str) -> DocumentExtractionStatusResponse:
        """Get extraction progress and review breakdown for a document."""
        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )
        records = db.execute(
            select(ExtractedRecord).where(ExtractedRecord.document_id == document_id)
        ).scalars().all()

        counts = {
            "pending_review": sum(1 for r in records if r.review_status == ReviewStatus.PENDING_REVIEW.value),
            "approved": sum(1 for r in records if r.review_status == ReviewStatus.APPROVED.value),
            "modified": sum(1 for r in records if r.review_status == ReviewStatus.MODIFIED.value),
            "rejected": sum(1 for r in records if r.review_status == ReviewStatus.REJECTED.value),
        }

        return DocumentExtractionStatusResponse(
            document_id=doc.id,
            filename=doc.filename,
            document_type=doc.document_type,
            status=doc.status,
            total_records_extracted=len(records),
            review_status_counts=counts,
            error_message=doc.error_message,
        )

    @staticmethod
    def extract_all_project_documents(db: Session, project_id: str) -> List[ExtractionJobResponse]:
        """Trigger extraction on all pending or failed documents in a project."""
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        docs = db.execute(
            select(Document).where(Document.project_id == project_id)
        ).scalars().all()

        results = []
        for d in docs:
            try:
                res = ExtractionService.extract_document(db, d.id)
                results.append(res)
            except HTTPException as he:
                results.append(
                    ExtractionJobResponse(
                        document_id=d.id,
                        document_name=d.filename,
                        status="failed",
                        records_extracted=0,
                        message=str(he.detail),
                    )
                )
        return results

    @staticmethod
    def list_records(
        db: Session,
        project_id: str,
        document_id: Optional[str] = None,
        review_status: Optional[str] = None,
        record_type: Optional[str] = None,
        vendor: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[int, List[ExtractedRecord]]:
        """Query extracted records with full filtering, search, and pagination."""
        query = select(ExtractedRecord).where(ExtractedRecord.project_id == project_id)

        if document_id:
            query = query.where(ExtractedRecord.document_id == document_id)
        if review_status:
            query = query.where(ExtractedRecord.review_status == review_status)
        if record_type:
            query = query.where(ExtractedRecord.record_type == record_type)
        if vendor:
            query = query.where(func.lower(ExtractedRecord.vendor) == vendor.lower())
        if search:
            search_filter = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(ExtractedRecord.part_number).like(search_filter),
                    func.lower(ExtractedRecord.description).like(search_filter),
                    func.lower(ExtractedRecord.vendor).like(search_filter),
                    func.lower(ExtractedRecord.location).like(search_filter),
                )
            )

        total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
        records = db.execute(
            query.order_by(ExtractedRecord.created_at.asc()).offset(skip).limit(limit)
        ).scalars().all()

        return total, records

    @staticmethod
    def get_record(db: Session, record_id: str) -> ExtractedRecord:
        """Fetch a single extracted record by ID."""
        record = db.execute(
            select(ExtractedRecord).where(ExtractedRecord.id == record_id)
        ).scalar_one_or_none()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Extracted record '{record_id}' not found.",
            )
        return record

    @staticmethod
    def update_record(
        db: Session,
        record_id: str,
        update_data: ExtractedRecordUpdate,
        reviewer_email: str,
    ) -> ExtractedRecord:
        """Update fields on an extracted record and mark it as modified."""
        record = ExtractionService.get_record(db, record_id)

        data = update_data.model_dump(exclude_unset=True)
        review_notes = data.pop("review_notes", None)
        for key, val in data.items():
            if hasattr(record, key):
                setattr(record, key, val)

        record.review_status = ReviewStatus.MODIFIED.value
        record.reviewed_by = reviewer_email
        record.reviewed_at = datetime.now(timezone.utc)
        if review_notes:
            record.review_notes = review_notes

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def review_record(
        db: Session,
        record_id: str,
        review_data: ExtractedRecordReview,
        reviewer_email: str,
    ) -> ExtractedRecord:
        """Submit a human review decision (approve, reject, or modify)."""
        record = ExtractionService.get_record(db, record_id)

        if review_data.corrections:
            corrections = review_data.corrections.model_dump(exclude_unset=True)
            for k, v in corrections.items():
                if hasattr(record, k):
                    setattr(record, k, v)

        record.review_status = review_data.status.value
        record.review_notes = review_data.review_notes
        record.reviewed_by = reviewer_email
        record.reviewed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def batch_review(
        db: Session,
        project_id: str,
        request: BatchReviewRequest,
        reviewer_email: str,
    ) -> int:
        """Bulk approve or reject multiple records at once."""
        status_value = (
            ReviewStatus.APPROVED.value
            if request.action == "approve"
            else ReviewStatus.REJECTED.value
        )
        now = datetime.now(timezone.utc)

        records = db.execute(
            select(ExtractedRecord).where(
                ExtractedRecord.project_id == project_id,
                ExtractedRecord.id.in_(request.record_ids),
            )
        ).scalars().all()

        for r in records:
            r.review_status = status_value
            r.reviewed_by = reviewer_email
            r.reviewed_at = now
            if request.review_notes:
                r.review_notes = request.review_notes

        db.commit()
        return len(records)

    @staticmethod
    def create_manual_record(
        db: Session,
        document_id: str,
        create_data: ExtractedRecordCreate,
        reviewer_email: str,
    ) -> ExtractedRecord:
        """Manually insert an extracted record that was missed by automated extraction."""
        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        data = create_data.model_dump()
        review_notes = data.pop("review_notes", "Manually created by human reviewer")

        record = ExtractedRecord(
            id=generate_id("rec"),
            project_id=doc.project_id,
            document_id=doc.id,
            confidence_score=1.0,
            review_status=ReviewStatus.APPROVED.value,
            reviewed_by=reviewer_email,
            reviewed_at=datetime.now(timezone.utc),
            review_notes=review_notes,
            is_manually_added=True,
            **data,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def delete_record(db: Session, record_id: str) -> bool:
        """Delete an extracted record."""
        record = ExtractionService.get_record(db, record_id)
        db.delete(record)
        db.commit()
        return True

    @staticmethod
    def get_review_summary(db: Session, project_id: str) -> ReviewSummaryResponse:
        """Compute human review progress and extraction statistics for a project."""
        records = db.execute(
            select(ExtractedRecord).where(ExtractedRecord.project_id == project_id)
        ).scalars().all()

        total = len(records)
        pending = sum(1 for r in records if r.review_status == ReviewStatus.PENDING_REVIEW.value)
        approved = sum(1 for r in records if r.review_status == ReviewStatus.APPROVED.value)
        modified = sum(1 for r in records if r.review_status == ReviewStatus.MODIFIED.value)
        rejected = sum(1 for r in records if r.review_status == ReviewStatus.REJECTED.value)

        reviewed_count = approved + modified + rejected
        completion_pct = round((reviewed_count / total * 100), 1) if total > 0 else 0.0
        avg_conf = (
            round(sum(r.confidence_score for r in records) / total, 2)
            if total > 0
            else 0.0
        )

        by_type: Dict[str, int] = {}
        by_vendor: Dict[str, int] = {}
        for r in records:
            by_type[r.record_type] = by_type.get(r.record_type, 0) + 1
            v_key = r.vendor or "Unspecified"
            by_vendor[v_key] = by_vendor.get(v_key, 0) + 1

        return ReviewSummaryResponse(
            project_id=project_id,
            total_records=total,
            pending_review_count=pending,
            approved_count=approved,
            modified_count=modified,
            rejected_count=rejected,
            completion_percentage=completion_pct,
            average_confidence=avg_conf,
            by_record_type=by_type,
            by_vendor=by_vendor,
        )
