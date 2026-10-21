<<<<<<< HEAD
import csv
import re
from datetime import datetime, timezone
=======
from __future__ import annotations

>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
from pathlib import Path
from typing import Any, Optional

<<<<<<< HEAD
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.extraction.column_map import (
    clean_part_number,
    detect_condition,
    map_headers,
    normalize_header,
)
from app.models.document import Document
from app.models.extracted_record import ExtractedRecord
from app.models.project import Project
from app.models.record_review_action import RecordReviewAction
from app.schemas.document import DocumentStatus
from app.schemas.record import (
    BatchReviewAction,
    BatchReviewRequest,
    DocumentExtractionStatusResponse,
    ExtractedRecordCreate,
    ExtractedRecordReview,
    ExtractedRecordUpdate,
    ExtractionJobResponse,
    RecordType,
    ReviewStatus,
    ReviewSummaryResponse,
=======
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.chains import extract_records_with_llm
from app.core.config import settings
from app.models.document import Document
from app.models.extracted_record import ExtractedRecord

from app.parsers.excel_parser import (
    parse_excel_file,
    excel_to_llm_text,
>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
)

from app.parsers.pdf_parser import (
    parse_pdf_file,
    pdf_to_llm_text,
)

from app.parsers.docx_parser import (
    parse_docx_file,
    docx_to_llm_text,
)

from app.parsers.image_parser import (
    parse_image_file,
    image_to_llm_text,
)

from app.schemas.inventory import (
    CanonicalInventoryDocument,
)

from app.utils.id_generator import generate_id
<<<<<<< HEAD
from app.utils.normalization import extract_vendor_from_text


def col_num_to_letter(col_idx: int) -> str:
    """Convert 0-indexed column integer to Excel column letter (0->A, 1->B, 26->AA)."""
    n = col_idx + 1
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def parse_quantity_strict(val: Any) -> Optional[float]:
    """Safely convert quantity to float if present; return None if empty/null/missing."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def record_to_values_dict(record: ExtractedRecord) -> Dict[str, Any]:
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
        "field_sources": record.field_sources,
    }

=======


EXCEL_EXTENSIONS = {
    ".xlsx",
    ".xlsm",
    ".xltx",
    ".xltm",
}

PDF_EXTENSIONS = {
    ".pdf",
}

DOCX_EXTENSIONS = {
    ".docx",
}

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}
>>>>>>> 2d848e6 (Improve AI extraction and document parsing)


class ExtractionService:

<<<<<<< HEAD
    @staticmethod
    def _parse_row_dict(
        headers: List[str],
        row_values: List[Any],
        source_sheet: Optional[str],
        row_idx: int,
        col_mapping: Optional[Dict[str, str]] = None,
        col_confidence: Optional[Dict[str, float]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Map a single row of tabular data into a structured record dictionary."""
        if col_mapping is None or col_confidence is None:
            col_mapping, col_confidence = map_headers(headers)

        record_data: Dict[str, Any] = {
            "source_sheet": source_sheet,
            "source_row": row_idx,
            "raw_data": {},
            "unmapped_columns": [],
            "field_sources": {},
        }

        # 1. Map columns to canonical fields or identify unmapped non-empty values
        for idx, (h, val) in enumerate(zip(headers, row_values)):
            col_label = (str(h).strip() if h is not None and str(h).strip() else f"Column {idx + 1}")
            val_str = str(val).strip() if val is not None else ""
            record_data["raw_data"][col_label] = val_str
            col_letter = col_num_to_letter(idx)

            canonical = col_mapping.get(h)
            if canonical:
                if canonical not in record_data or not record_data[canonical]:
                    record_data[canonical] = val_str
                    record_data["field_sources"][canonical] = {
                        "sheet": source_sheet or "Sheet1",
                        "row": row_idx,
                        "col": col_letter,
                        "header": col_label,
                    }
            else:
                # Unmapped column with non-empty content
                if val_str:
                    record_data["unmapped_columns"].append(col_label)

        # 2. Extract and clean part number
        part_number = record_data.get("part_number")

        if part_number:
            record_data["cleaned_part_number"] = clean_part_number(part_number)

        # 3. Model
        if not record_data.get("model") and record_data.get("cleaned_part_number"):
            record_data["model"] = record_data.get("cleaned_part_number")

        # Sync location and rack for backward compatibility
        if record_data.get("rack") and not record_data.get("location"):
            record_data["location"] = record_data.get("rack")
        elif record_data.get("location") and not record_data.get("rack"):
            record_data["rack"] = record_data.get("location")

        # 4. Strict quantity parsing (NEVER default to 1.0)
        raw_qty = record_data.get("quantity")
        record_data["quantity"] = parse_quantity_strict(raw_qty) if raw_qty else None
        if not record_data.get("quantity"):
            record_data["unit"] = None

        # 5. Detect condition and notes from DOA/test columns
        cond, cond_notes = detect_condition(record_data["raw_data"])
        if cond:
            record_data["condition"] = cond
        if cond_notes:
            existing_notes = record_data.get("condition_notes")
            record_data["condition_notes"] = (
                f"{existing_notes}; {cond_notes}"
                if existing_notes and existing_notes != cond_notes
                else cond_notes
            )

        # 6. Description & Part number fallback
        description = record_data.get("description")
        serial_number = record_data.get("serial_number")

        # If row has no part_number, no serial_number, no description, and no quantity: skip empty row
        if not part_number and not serial_number and not description and record_data.get("quantity") is None:
            return None

        # Infer vendor / manufacturer
        if not record_data.get("vendor"):
            inferred = extract_vendor_from_text(f"{part_number or ''} {description or ''}")
            if inferred:
                record_data["vendor"] = inferred
                record_data["manufacturer"] = inferred
        elif not record_data.get("manufacturer"):
            record_data["manufacturer"] = record_data.get("vendor")

        # 7. Strict float conversions for numeric fields
        if record_data.get("power_kw"):
            record_data["power_kw"] = parse_quantity_strict(record_data.get("power_kw"))
        if record_data.get("cable_length_m"):
            record_data["cable_length_m"] = parse_quantity_strict(record_data.get("cable_length_m"))

        # 8. Compute review_reason
        reasons = []
        if record_data.get("part_number") is None:
            reasons.append("missing_value")
        elif record_data.get("quantity") is None:
            reasons.append("missing_value")

        if record_data["unmapped_columns"]:
            reasons.append("unmapped_field")

        if col_confidence and any(conf < 0.9 for conf in col_confidence.values()):
            reasons.append("unclear_match")

        record_data["review_reason"] = reasons[0] if reasons else None

        # 9. Compute fine-grained confidence score (0.0 to 1.0)
        # Scale: 1.0 start; -0.3 if part_number missing; -0.2 if quantity missing;
        # -0.15 per non-empty unmapped value; -0.1 if loose match;
        # -0.2 if part_number has irregular format
        score = 1.0
        if not record_data.get("part_number"):
            score -= 0.30
        if record_data.get("quantity") is None:
            score -= 0.20
        if record_data["unmapped_columns"]:
            score -= min(0.30, len(record_data["unmapped_columns"]) * 0.15)
        if col_confidence and any(conf < 0.9 for conf in col_confidence.values()):
            score -= 0.10
        if part_number and re.search(r"[\s]{2,}|[?<>*!]", part_number):
            score -= 0.20

        record_data["confidence_score"] = round(max(0.05, min(1.0, score)), 2)

        # 10. Copy extracted canonical fields into immutable original_values
        record_data["original_values"] = {
            "part_number": record_data.get("part_number"),
            "cleaned_part_number": record_data.get("cleaned_part_number"),
            "model": record_data.get("model"),
            "serial_number": record_data.get("serial_number"),
            "condition": record_data.get("condition"),
            "condition_notes": record_data.get("condition_notes"),
            "description": record_data.get("description"),
            "quantity": record_data.get("quantity"),
            "unit": record_data.get("unit"),
            "vendor": record_data.get("vendor"),
            "manufacturer": record_data.get("manufacturer"),
            "location": record_data.get("location"),
            "rack": record_data.get("rack"),
            "u_position": record_data.get("u_position"),
            "source_device": record_data.get("source_device"),
            "source_port": record_data.get("source_port"),
            "target_device": record_data.get("target_device"),
            "target_port": record_data.get("target_port"),
            "cable_type": record_data.get("cable_type"),
            "power_kw": record_data.get("power_kw"),
            "cable_length_m": record_data.get("cable_length_m"),
            "field_sources": record_data.get("field_sources"),
        }

        return record_data

    @staticmethod
    def _extract_from_csv(file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """Parse CSV or TSV files using standard library csv module."""
        sep = "\t" if file_path.suffix.lower() == ".tsv" else ","
        records = []
        skipped_sheets = []
=======
    # =========================================================
    # SOURCE PARSING
    # =========================================================

    @staticmethod
    def get_source_content(
        file_path: Path,
    ) -> str:
        """
        Parse a source document while preserving structure.
>>>>>>> 2d848e6 (Improve AI extraction and document parsing)

        File extension determines HOW to read the file.

<<<<<<< HEAD
            if not headers:
                return [], []

            col_mapping, col_confidence = map_headers(headers)
            has_part_num = "part_number" in col_mapping.values()
            has_desc_qty = "description" in col_mapping.values() and "quantity" in col_mapping.values()

            if not has_part_num and not has_desc_qty:
                skipped_sheets.append({
                    "name": "default",
                    "reason": "No part number or (description + quantity) column found",
                })
                return [], skipped_sheets

            for row_idx, row in enumerate(reader, start=2):
                if not any(cell.strip() for cell in row):
                    continue
                parsed = ExtractionService._parse_row_dict(
                    headers=headers,
                    row_values=row,
                    source_sheet="default",
                    row_idx=row_idx,
                    col_mapping=col_mapping,
                    col_confidence=col_confidence,
                )
                if parsed:
                    records.append(parsed)

        return records, skipped_sheets

    @staticmethod
    def _extract_from_excel(file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """Parse Excel workbooks across all sheets using openpyxl with sheet skipping."""
        records = []
        skipped_sheets = []
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

                col_mapping, col_confidence = map_headers(headers)
                has_part_num = "part_number" in col_mapping.values()
                has_desc_qty = "description" in col_mapping.values() and "quantity" in col_mapping.values()

                # Problem 11: Require part-number column or (description + quantity), else skip sheet
                if not has_part_num and not has_desc_qty:
                    skipped_sheets.append({
                        "name": sheet_name,
                        "reason": "No part number or (description + quantity) column found",
                    })
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
                        col_mapping=col_mapping,
                        col_confidence=col_confidence,
                    )
                    if parsed:
                        records.append(parsed)
            wb.close()
        except ImportError:
            # Fallback to pandas if openpyxl not directly available
            try:
                import pandas as pd
                excel_file = pd.ExcelFile(file_path)
                for sheet_name in excel_file.sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str)
                    headers = [str(c) for c in df.columns]
                    col_mapping, col_confidence = map_headers(headers)
                    has_part_num = "part_number" in col_mapping.values()
                    has_desc_qty = "description" in col_mapping.values() and "quantity" in col_mapping.values()

                    if not has_part_num and not has_desc_qty:
                        skipped_sheets.append({
                            "name": sheet_name,
                            "reason": "No part number or (description + quantity) column found",
                        })
                        continue

                    for row_idx, row in df.iterrows():
                        row_vals = [str(v) if pd.notna(v) else "" for v in row]
                        parsed = ExtractionService._parse_row_dict(
                            headers=headers,
                            row_values=row_vals,
                            source_sheet=sheet_name,
                            row_idx=int(row_idx) + 1,
                            col_mapping=col_mapping,
                            col_confidence=col_confidence,
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

        return records, skipped_sheets

    @staticmethod
    def _extract_from_pdf(file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """Extract structured line items from PDF documents."""
        records = []
        skipped_sheets = []
        try:
            import importlib
            try:
                fitz = importlib.import_module("fitz")
            except ImportError:
                fitz = importlib.import_module("pymupdf")

            doc = fitz.open(file_path)
            for page_idx, page in enumerate(doc, start=1):
                tables = getattr(page, "find_tables", lambda: None)()
                if tables and tables.tables:
                    for t_idx, table in enumerate(tables.tables):
                        table_data = table.extract()
                        if table_data and len(table_data) > 1:
                            headers = [str(c).strip() if c else "" for c in table_data[0]]
                            col_mapping, col_confidence = map_headers(headers)
                            for r_idx, r in enumerate(table_data[1:], start=2):
                                row_str = [str(c).strip() if c else "" for c in r]
                                parsed = ExtractionService._parse_row_dict(
                                    headers=headers,
                                    row_values=row_str,
                                    source_sheet=f"Page_{page_idx}_Table_{t_idx + 1}",
                                    row_idx=r_idx,
                                    col_mapping=col_mapping,
                                    col_confidence=col_confidence,
                                )
                                if parsed:
                                    records.append(parsed)
                else:
                    text = page.get_text("text")
                    for line_idx, line in enumerate(text.splitlines(), start=1):
                        parts = line.strip().split()
                        if len(parts) >= 2 and any(char.isdigit() for char in line):
                            clean_pn = clean_part_number(parts[0])
                            records.append({
                                "source_sheet": f"Page_{page_idx}",
                                "source_row": line_idx,
                                "part_number": parts[0],
                                "cleaned_part_number": clean_pn,
                                "description": " ".join(parts[1:]),
                                "quantity": None,
                                "confidence_score": 0.60,
                                "review_reason": "missing_value",
                                "raw_data": {"line": line},
                                "original_values": {
                                    "part_number": parts[0],
                                    "cleaned_part_number": clean_pn,
                                    "description": " ".join(parts[1:]),
                                    "quantity": None,
                                },
                            })
            doc.close()
        except ImportError:
            clean_pn = "DOC-SUMMARY"
            records.append({
                "source_sheet": "PDF_Extraction",
                "source_row": 1,
                "part_number": clean_pn,
                "cleaned_part_number": clean_pn,
                "description": f"Extracted from {file_path.name}",
                "quantity": None,
                "confidence_score": 0.50,
                "review_reason": "missing_value",
                "raw_data": {"filename": file_path.name},
                "original_values": {
                    "part_number": clean_pn,
                    "cleaned_part_number": clean_pn,
                    "description": f"Extracted from {file_path.name}",
                    "quantity": None,
                },
            })
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to parse PDF document: {str(e)}",
            )
        return records, skipped_sheets

    @staticmethod
    def extract_document_text(file_path: Path) -> str:
        """Extract plain text lines from files for LLM prompt context."""
        ext = file_path.suffix.lower()
        if ext in [".csv", ".tsv", ".txt"]:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(50000)
        elif ext in [".xlsx", ".xls", ".xlsm"]:
            try:
                from app.parsers.excel_parser import parse_excel_file, excel_to_llm_text
                parsed = parse_excel_file(file_path)
                return excel_to_llm_text(parsed)
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
                lines = []
                for s in wb.sheetnames:
                    sheet = wb[s]
                    lines.append(f"--- SHEET: {s} ---")
                    for row in sheet.iter_rows(values_only=True):
                        non_empty = [str(c) for c in row if c is not None and str(c).strip()]
                        if non_empty:
                            lines.append(" | ".join(non_empty))
                wb.close()
                return "\n".join(lines[:1000])
            except Exception:
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
                from app.parsers.pdf_parser import extract_text_from_pdf
                return extract_text_from_pdf(file_path)
                import importlib
                try:
                    fitz = importlib.import_module("fitz")
                except ImportError:
                    fitz = importlib.import_module("pymupdf")
                doc = fitz.open(file_path)
                text = "\n".join(page.get_text("text") for page in doc)
                doc.close()
                return text[:50000]
            except Exception:
                return ""
        return ""

    @staticmethod
    def extract_document(
        db: Session,
        document_id: str,
        use_ai: bool = False,
        model: Optional[str] = None,
    ) -> ExtractionJobResponse:
        """Execute extraction pipeline for a specific document and store extracted records."""
        if use_ai:
            return ExtractionService.extract_document_with_ai(
                db=db,
                document_id=document_id,
                model=model,
                allow_fallback=True,
            )

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
        skipped_sheets: List[Dict[str, str]] = []

        try:
            if ext in [".csv", ".tsv"]:
                extracted_data, skipped_sheets = ExtractionService._extract_from_csv(file_path)
            elif ext in [".xlsx", ".xls", ".xlsm"]:
                extracted_data, skipped_sheets = ExtractionService._extract_from_excel(file_path)
            elif ext == ".pdf":
                extracted_data, skipped_sheets = ExtractionService._extract_from_pdf(file_path)
            else:
                extracted_data, skipped_sheets = ExtractionService._extract_from_csv(file_path)

            # Store skipped sheets in document metadata
            doc_meta = dict(doc.metadata_json or {})
            if skipped_sheets:
                doc_meta["skipped_sheets"] = skipped_sheets
            doc.metadata_json = doc_meta

            doc_type_mapping = {
                "bom": RecordType.BOM_ITEM.value,
                "purchase": RecordType.BOM_ITEM.value,
                "p2p": RecordType.CABLE_ITEM.value,
                "rack_layout": RecordType.RACK_ITEM.value,
                "power": RecordType.POWER_ITEM.value,
                "cable": RecordType.CABLE_ITEM.value,
            }
            default_record_type = doc_type_mapping.get(doc.document_type, RecordType.BOM_ITEM.value)

            # Problem 13: Deduplication and review status preservation on re-extract
            existing_records = db.execute(
                select(ExtractedRecord).where(
                    ExtractedRecord.document_id == document_id,
                    ExtractedRecord.is_deleted == False,
                )
            ).scalars().all()

            by_sheet_row = {
                (r.source_sheet, r.source_row): r
                for r in existing_records
                if r.source_row is not None
            }
            by_pn_ident = {
                (r.part_number, r.serial_number or r.location or r.rack): r
                for r in existing_records
                if r.part_number
            }

            matched_existing_ids = set()

            for item in extracted_data:
                # Find matching existing record
                match = by_sheet_row.get((item.get("source_sheet"), item.get("source_row")))
                if not match and item.get("part_number"):
                    ident_key = (
                        item.get("part_number"),
                        item.get("serial_number") or item.get("location") or item.get("rack"),
                    )
                    match = by_pn_ident.get(ident_key)

                if match:
                    matched_existing_ids.add(match.id)
                    # Check if core parsed values changed
                    values_changed = (
                        match.part_number != item.get("part_number")
                        or match.quantity != item.get("quantity")
                        or match.serial_number != item.get("serial_number")
                        or match.condition != item.get("condition")
                        or match.condition_notes != item.get("condition_notes")
                        or match.description != item.get("description")
                    )
                    if values_changed:
                        # Values changed: update and reset to pending_review
                        old_val = record_to_values_dict(match)
                        match.part_number = item.get("part_number")
                        match.cleaned_part_number = item.get("cleaned_part_number")
                        match.model = item.get("model")
                        match.serial_number = item.get("serial_number")
                        match.condition = item.get("condition")
                        match.condition_notes = item.get("condition_notes")
                        match.description = item.get("description")
                        match.quantity = item.get("quantity")
                        match.unit = item.get("unit")
                        match.vendor = item.get("vendor")
                        match.manufacturer = item.get("manufacturer")
                        match.location = item.get("location")
                        match.rack = item.get("rack")
                        match.u_position = item.get("u_position")
                        match.power_kw = item.get("power_kw")
                        match.cable_length_m = item.get("cable_length_m")
                        match.source_device = item.get("source_device")
                        match.target_device = item.get("target_device")
                        match.raw_data = item.get("raw_data")
                        match.unmapped_columns = item.get("unmapped_columns", [])
                        match.review_reason = item.get("review_reason")
                        match.confidence_score = item.get("confidence_score", 0.80)
                        match.review_status = ReviewStatus.PENDING_REVIEW.value
                        new_val = record_to_values_dict(match)

                        db.add(
                            RecordReviewAction(
                                id=generate_id("act_"),
                                record_id=match.id,
                                action="re_extract_changed",
                                old_values=old_val,
                                new_values=new_val,
                                reason="Values changed during re-extraction; reset to pending review",
                                reviewer_id="system",
                            )
                        )
                    else:
                        # Values unchanged: keep approvals and review state intact!
                        match.raw_data = item.get("raw_data")
                        match.unmapped_columns = item.get("unmapped_columns", [])
                else:
                    # New record
                    rec = ExtractedRecord(
                        id=generate_id("rec"),
                        project_id=doc.project_id,
                        document_id=doc.id,
                        record_type=default_record_type,
                        category=item.get("category"),
                        part_number=item.get("part_number"),
                        cleaned_part_number=item.get("cleaned_part_number"),
                        model=item.get("model"),
                        serial_number=item.get("serial_number"),
                        condition=item.get("condition"),
                        condition_notes=item.get("condition_notes"),
                        description=item.get("description"),
                        quantity=item.get("quantity"),
                        unit=item.get("unit"),
                        vendor=item.get("vendor"),
                        manufacturer=item.get("manufacturer"),
                        location=item.get("location"),
                        rack=item.get("rack"),
                        u_position=item.get("u_position"),
                        power_kw=item.get("power_kw"),
                        cable_length_m=item.get("cable_length_m"),
                        source_device=item.get("source_device"),
                        source_port=item.get("source_port"),
                        target_device=item.get("target_device"),
                        target_port=item.get("target_port"),
                        cable_type=item.get("cable_type"),
                        confidence_score=item.get("confidence_score", 0.80),
                        raw_data=item.get("raw_data"),
                        unmapped_columns=item.get("unmapped_columns", []),
                        review_reason=item.get("review_reason"),
                        original_values=item.get("original_values"),
                        extraction_method="table",
                        model_used=None,
                        source_sheet=item.get("source_sheet"),
                        source_row=item.get("source_row"),
                        field_sources=item.get("field_sources"),
                        review_status=ReviewStatus.PENDING_REVIEW.value,
                        is_manually_added=False,
                        is_deleted=False,
                    )
                    db.add(rec)

            # Mark missing records as removed
            for r in existing_records:
                if r.id not in matched_existing_ids:
                    r.is_deleted = True

            doc.status = DocumentStatus.EXTRACTED.value
            doc.error_message = None
            db.commit()

            return ExtractionJobResponse(
                document_id=doc.id,
                document_name=doc.filename,
                status="extracted",
                records_extracted=len(extracted_data),
                message=f"Successfully extracted {len(extracted_data)} records.",
                model_used=None,
                fallback=False,
            )

        except HTTPException:
            raise
        except Exception as e:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = f"Extraction failure: {str(e)}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Extraction failed: {str(e)}",
            )
=======
        Business category determines WHAT the AI extracts.
        """

        extension = (
            file_path.suffix.lower()
        )

        # -----------------------------------------------------
        # EXCEL
        # -----------------------------------------------------

        if extension in EXCEL_EXTENSIONS:

            parsed = parse_excel_file(
                file_path
            )

            return excel_to_llm_text(
                parsed
            )

        # -----------------------------------------------------
        # PDF
        # -----------------------------------------------------

        if extension in PDF_EXTENSIONS:

            parsed = parse_pdf_file(
                file_path
            )

            return pdf_to_llm_text(
                parsed
            )

        # -----------------------------------------------------
        # DOCX
        # -----------------------------------------------------

        if extension in DOCX_EXTENSIONS:

            parsed = parse_docx_file(
                file_path
            )

            return docx_to_llm_text(
                parsed
            )

        # -----------------------------------------------------
        # IMAGE
        # -----------------------------------------------------

        if extension in IMAGE_EXTENSIONS:

            parsed = parse_image_file(
                file_path
            )

            return image_to_llm_text(
                parsed
            )

        raise ValueError(
            f"Unsupported file type: "
            f"{extension}"
        )

    # =========================================================
    # AI EXTRACTION
    # =========================================================
>>>>>>> 2d848e6 (Improve AI extraction and document parsing)

    @staticmethod
    def extract_document_with_ai(
        db: Session,
        document_id: str,
        model: Optional[str] = None,
<<<<<<< HEAD
        allow_fallback: bool = False,
    ) -> ExtractionJobResponse:
        """Run AI LLM extraction on a document. Enforces 503 when Ollama offline (Problem 4)."""
        from app.ai.chains import extract_records_with_llm
        from app.ai.llm import ollama_client

        target_model = model or settings.LLM_MODEL

        # Problem 4: If Ollama offline, return 503 unless explicit fallback allowed
        if not ollama_client.is_available():
            if not allow_fallback:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI engine is not available",
                )
            fb = ExtractionService.extract_document(db, document_id)
            fb.model_used = None
            fb.fallback = True
            fb.message = f"{fb.message} (Note: AI engine offline, used heuristic table extraction fallback)"
            return fb

        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
=======
    ) -> dict[str, Any]:

        doc = db.execute(
            select(Document).where(
                Document.id == document_id
            )
        ).scalar_one_or_none()

>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
        if not doc:

            raise HTTPException(
                status_code=(
                    status.HTTP_404_NOT_FOUND
                ),
                detail=(
                    f"Document '{document_id}' "
                    f"not found."
                ),
            )

        file_path = Path(
            doc.file_path
        )

        if not file_path.exists():

            raise HTTPException(
                status_code=(
                    status.HTTP_404_NOT_FOUND
                ),
                detail=(
                    "Source file does not exist: "
                    f"{file_path}"
                ),
            )

        doc.status = "extracting"
        doc.error_message = None

        db.commit()

        try:

            # -------------------------------------------------
            # CATEGORY
            # -------------------------------------------------

            document_category = (
                getattr(
                    doc,
                    "document_type",
                    None,
                )
                or "bom"
            )

<<<<<<< HEAD
            # Insert AI extracted records with audit
            for item in ai_records:
                pn = item.get("part_number")
                clean_pn = clean_part_number(pn) if pn else None
                qty = parse_quantity_strict(item.get("quantity"))

                orig_dict = {
                    "part_number": pn,
                    "cleaned_part_number": clean_pn,
                    "model": clean_pn,
                    "description": item.get("description"),
                    "quantity": qty,
                    "unit": item.get("unit"),
                    "vendor": item.get("vendor"),
                    "manufacturer": item.get("vendor"),
                    "location": item.get("location"),
                }

                rec = ExtractedRecord(
                    id=generate_id("rec"),
=======
            document_category = (
                document_category
                .strip()
                .lower()
            )

            # -------------------------------------------------
            # FILE TYPE
            # -------------------------------------------------

            source_file_type = (
                file_path.suffix.lower()
            )

            # -------------------------------------------------
            # PARSE COMPLETE DOCUMENT
            # -------------------------------------------------

            document_content = (
                ExtractionService.get_source_content(
                    file_path
                )
            )

            if not document_content.strip():

                raise HTTPException(
                    status_code=(
                        status.HTTP_422_UNPROCESSABLE_ENTITY
                    ),
                    detail=(
                        "No readable content "
                        "was found in the document."
                    ),
                )

            # -------------------------------------------------
            # AI SEMANTIC EXTRACTION
            # -------------------------------------------------

            canonical_document = (
                extract_records_with_llm(

                    document_content=(
                        document_content
                    ),

                    document_category=(
                        document_category
                    ),

                    source_file_name=(
                        doc.filename
                    ),

                    source_file_type=(
                        source_file_type
                    ),

                    model=model,
                )
            )

            # -------------------------------------------------
            # DELETE PREVIOUS EXTRACTION
            # -------------------------------------------------

            existing_records = db.execute(
                select(
                    ExtractedRecord
                ).where(
                    ExtractedRecord.document_id
                    == document_id
                )
            ).scalars().all()

            for record in existing_records:
                db.delete(record)

            db.flush()

            # -------------------------------------------------
            # SAVE NEW RECORDS
            # -------------------------------------------------

            records_saved = 0

            for item in (
                canonical_document.records
            ):

                provenance = {}

                if item.provenance:

                    provenance = (
                        item.provenance.model_dump(
                            exclude_none=True
                        )
                    )

                raw_data = {

                    "canonical_record": (
                        item.model_dump(
                            exclude={
                                "raw_data",
                                "provenance",
                            }
                        )
                    ),

                    "source_provenance": (
                        provenance
                    ),

                    "original_raw_data": (
                        item.raw_data
                    ),

                    "extra_fields": (
                        item.extra_fields
                    ),
                }

                record = ExtractedRecord(

                    id=generate_id(
                        "rec"
                    ),

>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
                    project_id=doc.project_id,

                    document_id=doc.id,
<<<<<<< HEAD
                    record_type=item.get("record_type", "bom_item"),
                    category=item.get("category"),
                    part_number=pn,
                    cleaned_part_number=clean_pn,
                    model=clean_pn,
                    description=item.get("description"),
                    quantity=qty,
                    unit=item.get("unit"),
                    vendor=item.get("vendor"),
                    manufacturer=item.get("vendor"),
                    location=item.get("location"),
                    source_device=item.get("source_device"),
                    source_port=item.get("source_port"),
                    target_device=item.get("target_device"),
                    target_port=item.get("target_port"),
                    cable_type=item.get("cable_type"),
                    confidence_score=item.get("confidence_score", 0.90),
                    raw_data=item.get("raw_data"),
                    original_values=orig_dict,
                    extraction_method="ai",
                    model_used=target_model,
                    source_sheet="AI_Extracted",
                    review_status=ReviewStatus.PENDING_REVIEW.value,
=======

                    record_type=(
                        item.record_type
                        or "inventory_item"
                    ),

                    category=(
                        item.category
                        or document_category
                    ),

                    equipment_name=(
                        item.equipment_name
                    ),

                    part_number=(
                        item.part_number
                    ),

                    description=(
                        item.description
                    ),

                    model=(
                        item.model
                    ),

                    manufacturer=(
                        item.manufacturer
                    ),

                    vendor=(
                        item.vendor
                    ),

                    quantity=(
                        item.quantity
                    ),

                    unit=(
                        item.unit
                    ),

                    rack_id=(
                        item.rack_id
                    ),

                    u_position=(
                        item.u_position
                    ),

                    location=(
                        item.rack_id
                    ),

                    source_device=(
                        item.source_device
                    ),

                    source_port=(
                        item.source_port
                    ),

                    target_device=(
                        item.target_device
                    ),

                    target_port=(
                        item.target_port
                    ),

                    cable_type=(
                        item.cable_type
                    ),

                    cable_length=(
                        item.length
                    ),

                    power_watts=(
                        item.power_watts
                    ),

                    dimensions=(
                        item.dimensions
                    ),

                    confidence_score=(
                        item.confidence_score
                    ),

                    raw_data=raw_data,

                    source_sheet=(
                        provenance.get(
                            "sheet_name"
                        )
                    ),

                    source_row=(
                        provenance.get(
                            "source_row"
                        )
                    ),

                    review_status=(
                        "pending_review"
                    ),

>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
                    is_manually_added=False,
                    is_deleted=False,
                )

                db.add(record)

                records_saved += 1

            # -------------------------------------------------
            # UPDATE DOCUMENT
            # -------------------------------------------------

            doc.status = "extracted"
            doc.error_message = None

            db.commit()

<<<<<<< HEAD
            return ExtractionJobResponse(
                document_id=doc.id,
                document_name=doc.filename,
                status="extracted",
                records_extracted=len(ai_records),
                model_used=target_model,
                message=f"Successfully extracted {len(ai_records)} records using {target_model}.",
                fallback=False,
            )
        except ConnectionError:
            if not allow_fallback:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI engine is not available",
                )
            fb = ExtractionService.extract_document(db, document_id)
            fb.model_used = None
            fb.fallback = True
            return fb
        except Exception as e:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = f"AI extraction error: {str(e)}"
            db.commit()
=======
            return {

                "document_id": doc.id,

                "document_name": (
                    doc.filename
                ),

                "category": (
                    document_category
                ),

                "file_type": (
                    source_file_type
                ),

                "status": "extracted",

                "records_extracted": (
                    records_saved
                ),

                "model_used": (
                    model
                    or settings.LLM_MODEL
                ),

                "message": (
                    f"Successfully extracted "
                    f"{records_saved} records."
                ),
            }

        except HTTPException:

            db.rollback()

            raise

        except Exception as exc:

            db.rollback()

            try:

                failed_doc = db.execute(
                    select(Document).where(
                        Document.id == document_id
                    )
                ).scalar_one_or_none()

                if failed_doc:

                    failed_doc.status = "failed"

                    failed_doc.error_message = (
                        f"AI extraction error: "
                        f"{str(exc)}"
                    )

                    db.commit()

            except Exception:

                db.rollback()

>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
            raise HTTPException(
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                detail=(
                    f"AI extraction failed: "
                    f"{str(exc)}"
                ),
            )

    # =========================================================
    # RAW TEXT EXTRACTION
    # =========================================================

    @staticmethod
    def extract_raw_snippet_with_ai(
        text: str,
        document_type: str = "bom",
        model: Optional[str] = None,
    ) -> list[dict[str, Any]]:

        result = extract_records_with_llm(

<<<<<<< HEAD
    @staticmethod
    def run_background_extraction(document_id: str) -> None:
        """Background task worker for single document extraction."""
        from app.core.database import SessionLocal
        with SessionLocal() as db:
            try:
                ExtractionService.extract_document(db, document_id)
            except Exception as e:
                db.rollback()
                doc = db.get(Document, document_id)
                if doc:
                    doc.status = DocumentStatus.FAILED.value
                    doc.error_message = f"Extraction failed: {str(e)}"
                    db.commit()

    @staticmethod
    def queue_extract_all_project_documents(
        db: Session,
        project_id: str,
        background_tasks: BackgroundTasks,
    ) -> List[Dict[str, str]]:
        """Problem 12: Queue background extraction and return 202 immediately."""
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        docs = db.execute(
            select(Document).where(Document.project_id == project_id)
        ).scalars().all()

        queued_list = []
        for d in docs:
            d.status = DocumentStatus.EXTRACTING.value
            background_tasks.add_task(ExtractionService.run_background_extraction, d.id)
            queued_list.append({"document_id": d.id, "status": "queued"})

        db.commit()
        return queued_list
=======
            document_content=text,

            document_category=(
                document_type
            ),

            source_file_name=(
                "raw_snippet.txt"
            ),

            source_file_type=".txt",

            model=model,
        )
>>>>>>> 2d848e6 (Improve AI extraction and document parsing)

        return [
            record.model_dump()
            for record in result.records
        ]

    # =========================================================
    # STATUS
    # =========================================================

    @staticmethod
<<<<<<< HEAD
    def extract_all_project_documents(db: Session, project_id: str) -> List[ExtractionJobResponse]:
        """Synchronous version for test backward compatibility."""
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
=======
    def get_document_extraction_status(
        db: Session,
        document_id: str,
    ):

        doc = db.execute(
            select(Document).where(
                Document.id == document_id
            )
        ).scalar_one_or_none()

        if not doc:

>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
            raise HTTPException(
                status_code=(
                    status.HTTP_404_NOT_FOUND
                ),
                detail="Document not found.",
            )

        record_count = db.execute(
            select(
                ExtractedRecord
            ).where(
                ExtractedRecord.document_id
                == document_id
            )
        ).scalars().all()

        return {
            "document_id": doc.id,
            "document_name": doc.filename,
            "status": doc.status,
            "records_extracted": len(
                record_count
            ),
            "error_message": (
                doc.error_message
            ),
        }

    # =========================================================
    # PROJECT EXTRACTION
    # =========================================================

    @staticmethod
    def extract_all_project_documents(
        db: Session,
        project_id: str,
    ):

        documents = db.execute(
            select(Document).where(
                Document.project_id
                == project_id
            )
        ).scalars().all()

        results = []

        for document in documents:

            try:

                result = (
                    ExtractionService
                    .extract_document_with_ai(
                        db,
                        document.id,
                    )
                )

<<<<<<< HEAD
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
        """Query active extracted records with full filtering, search, and pagination."""
        query = select(ExtractedRecord).where(
            ExtractedRecord.project_id == project_id,
            ExtractedRecord.is_deleted == False,
        )

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
                    func.lower(ExtractedRecord.cleaned_part_number).like(search_filter),
                    func.lower(ExtractedRecord.description).like(search_filter),
                    func.lower(ExtractedRecord.vendor).like(search_filter),
                    func.lower(ExtractedRecord.location).like(search_filter),
                    func.lower(ExtractedRecord.rack).like(search_filter),
=======
                results.append(result)

            except HTTPException as exc:

                results.append(
                    {
                        "document_id": (
                            document.id
                        ),
                        "document_name": (
                            document.filename
                        ),
                        "status": "failed",
                        "error": str(
                            exc.detail
                        ),
                    }
>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
                )

<<<<<<< HEAD
        total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
        records = db.execute(
            query.order_by(ExtractedRecord.created_at.asc()).offset(skip).limit(limit)
        ).scalars().all()

        return total, records

    @staticmethod
    def get_record(db: Session, record_id: str) -> ExtractedRecord:
        """Fetch a single extracted record by ID."""
        record = db.execute(
            select(ExtractedRecord).where(
                ExtractedRecord.id == record_id,
                ExtractedRecord.is_deleted == False,
            )
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
        """Problem 9: Update fields, log to audit trail, reset approved record to pending_review."""
        record = ExtractionService.get_record(db, record_id)
        old_state = record_to_values_dict(record)

        data = update_data.model_dump(exclude_unset=True)
        review_notes = data.pop("review_notes", None)

        for key, val in data.items():
            if hasattr(record, key):
                setattr(record, key, val)

        # Re-compute cleaned part number if part number was updated
        if "part_number" in data and record.part_number:
            record.cleaned_part_number = clean_part_number(record.part_number)

        # Problem 9: PATCH on approved/modified record sets status back to pending_review
        # (or requires review_notes and sets modified)
        if review_notes and len(review_notes.strip()) >= 3:
            record.review_status = ReviewStatus.MODIFIED.value
        elif record.review_status in [ReviewStatus.APPROVED.value, ReviewStatus.MODIFIED.value]:
            record.review_status = ReviewStatus.PENDING_REVIEW.value

        record.reviewed_by = reviewer_email
        record.reviewed_at = datetime.now(timezone.utc)
        if review_notes:
            record.review_notes = review_notes

        new_state = record_to_values_dict(record)

        audit = RecordReviewAction(
            id=generate_id("act_"),
            record_id=record.id,
            action="patch",
            old_values=old_state,
            new_values=new_state,
            reason=review_notes or "Record patched via API",
            reviewer_id=reviewer_email,
        )
        db.add(audit)
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
        """Problem 8: Human review decision, audit trail, and original values restoration on undo."""
        record = ExtractionService.get_record(db, record_id)
        old_state = record_to_values_dict(record)

        action_type = "review"
        if review_data.status == ReviewStatus.PENDING_REVIEW:
            # Undo / reset action: restore original values
            action_type = "undo"
            if record.original_values:
                for k, v in record.original_values.items():
                    if hasattr(record, k):
                        setattr(record, k, v)
            record.review_status = ReviewStatus.PENDING_REVIEW.value
            record.reviewed_by = None
            record.reviewed_at = None
            record.review_notes = review_data.review_notes
        else:
            if review_data.corrections:
                corrections = review_data.corrections.model_dump(exclude_unset=True)
                for k, v in corrections.items():
                    if hasattr(record, k):
                        setattr(record, k, v)
                if "part_number" in corrections and record.part_number:
                    record.cleaned_part_number = clean_part_number(record.part_number)

            record.review_status = review_data.status.value
            record.review_notes = review_data.review_notes
            record.reviewed_by = reviewer_email
            record.reviewed_at = datetime.now(timezone.utc)

        new_state = record_to_values_dict(record)

        audit = RecordReviewAction(
            id=generate_id("act_"),
            record_id=record.id,
            action=action_type,
            old_values=old_state,
            new_values=new_state,
            reason=review_data.review_notes,
            reviewer_id=reviewer_email,
        )
        db.add(audit)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def batch_review(
        db: Session,
        project_id: str,
        request: BatchReviewRequest,
        reviewer_email: str,
    ) -> Tuple[int, List[Dict[str, str]]]:
        """Problem 20: Bulk review with min_confidence validation, refusal of unvetted records, and audit."""
        status_value = (
            ReviewStatus.APPROVED.value
            if request.action == BatchReviewAction.APPROVE
            else ReviewStatus.REJECTED.value
        )
        now = datetime.now(timezone.utc)

        records = db.execute(
            select(ExtractedRecord).where(
                ExtractedRecord.project_id == project_id,
                ExtractedRecord.id.in_(request.record_ids),
                ExtractedRecord.is_deleted == False,
            )
        ).scalars().all()

        updated_count = 0
        skipped: List[Dict[str, str]] = []

        for r in records:
            if request.action == BatchReviewAction.APPROVE and request.min_confidence is not None:
                if r.confidence_score < request.min_confidence:
                    skipped.append({
                        "id": r.id,
                        "reason": f"Confidence score ({r.confidence_score}) is below minimum required {request.min_confidence}",
                    })
                    continue
                if r.review_reason:
                    skipped.append({
                        "id": r.id,
                        "reason": f"Record requires individual human review: flagged with '{r.review_reason}'",
                    })
                    continue
                if not r.part_number:
                    skipped.append({
                        "id": r.id,
                        "reason": "Missing part number; cannot be batch-approved",
                    })
                    continue

            old_state = record_to_values_dict(r)
            r.review_status = status_value
            r.reviewed_by = reviewer_email
            r.reviewed_at = now
            if request.review_notes:
                r.review_notes = request.review_notes
            new_state = record_to_values_dict(r)

            db.add(
                RecordReviewAction(
                    id=generate_id("act_"),
                    record_id=r.id,
                    action="batch_review",
                    old_values=old_state,
                    new_values=new_state,
                    reason=request.review_notes or f"Batch {request.action.value}",
                    reviewer_id=reviewer_email,
                )
            )
            updated_count += 1

        db.commit()
        return updated_count, skipped

    @staticmethod
    def get_record_evidence(db: Session, record_id: str) -> Dict[str, Any]:
        """Problem 18: Retrieve highlighted cell or image coordinate evidence for a record."""
        from app.core.security import create_evidence_token
        record = ExtractionService.get_record(db, record_id)
        doc = db.get(Document, record.document_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated document not found")

        file_path = Path(doc.file_path)
        ext = file_path.suffix.lower()

        # Excel evidence
        if ext in [".xlsx", ".xls", ".xlsm"]:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
                sheet_name = record.source_sheet if record.source_sheet and record.source_sheet in wb.sheetnames else wb.sheetnames[0]
                sheet = wb[sheet_name]
                all_rows = list(sheet.iter_rows(values_only=True))
                wb.close()

                target_row = record.source_row or 2
                start_row = max(1, target_row - 5)
                end_row = min(len(all_rows), target_row + 5)

                headers = [str(c) if c is not None else "" for c in all_rows[0]] if all_rows else []
                sliced_rows = [
                    [str(c) if c is not None else "" for c in row]
                    for row in all_rows[start_row - 1 : end_row]
                ]

                highlight_col = "A"
                if record.field_sources and isinstance(record.field_sources, dict):
                    if "part_number" in record.field_sources:
                        highlight_col = record.field_sources["part_number"].get("col", "A")

                return {
                    "record_id": record.id,
                    "document_id": doc.id,
                    "document_name": doc.filename,
                    "evidence_type": "excel",
                    "evidence": {
                        "type": "excel",
                        "sheet": sheet_name,
                        "headers": headers,
                        "startRow": start_row,
                        "rows": sliced_rows,
                        "highlight": {
                            "row": target_row,
                            "col": highlight_col,
                        },
                    },
                }
            except Exception:
                pass

        # CSV / TSV evidence
        if ext in [".csv", ".tsv"]:
            try:
                sep = "\t" if ext == ".tsv" else ","
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    reader = list(csv.reader(f, delimiter=sep))
                headers = reader[0] if reader else []
                target_row = record.source_row or 2
                start_row = max(1, target_row - 5)
                end_row = min(len(reader), target_row + 5)
                sliced_rows = reader[start_row - 1 : end_row]

                highlight_col = "A"
                if record.field_sources and isinstance(record.field_sources, dict):
                    if "part_number" in record.field_sources:
                        highlight_col = record.field_sources["part_number"].get("col", "A")

                return {
                    "record_id": record.id,
                    "document_id": doc.id,
                    "document_name": doc.filename,
                    "evidence_type": "excel",
                    "evidence": {
                        "type": "excel",
                        "sheet": record.source_sheet or "default",
                        "headers": headers,
                        "startRow": start_row,
                        "rows": sliced_rows,
                        "highlight": {
                            "row": target_row,
                            "col": highlight_col,
                        },
                    },
                }
            except Exception:
                pass

        # PDF or Image evidence
        token = create_evidence_token(doc.id)
        return {
            "record_id": record.id,
            "document_id": doc.id,
            "document_name": doc.filename,
            "evidence_type": "image",
            "evidence": {
                "type": "image",
                "imageUrl": f"/api/v1/documents/{doc.id}/evidence-image?token={token}",
                "width": 2480,
                "height": 3508,
                "boundingBox": [0.1, 0.1, 0.9, 0.2],
                "ocrText": record.description or record.part_number or "",
                "confidence": record.confidence_score,
            },
        }

    @staticmethod
    def create_manual_record(
        db: Session,
        document_id: str,
        create_data: ExtractedRecordCreate,
        reviewer_email: str,
    ) -> ExtractedRecord:
        """Manually insert an extracted record and log creation audit."""
        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        data = create_data.model_dump()
        review_notes = data.pop("review_notes", "Manually created by human reviewer")

        pn = data.get("part_number")
        clean_pn = clean_part_number(pn) if pn else None
        if clean_pn and not data.get("cleaned_part_number"):
            data["cleaned_part_number"] = clean_pn
        if clean_pn and not data.get("model"):
            data["model"] = clean_pn

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
            is_deleted=False,
            original_values=dict(data),
            **data,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        db.add(
            RecordReviewAction(
                id=generate_id("act_"),
                record_id=record.id,
                action="create_manual",
                old_values=None,
                new_values=record_to_values_dict(record),
                reason=review_notes,
                reviewer_id=reviewer_email,
            )
        )
        db.commit()
        return record

    @staticmethod
    def delete_record(db: Session, record_id: str, reviewer_email: Optional[str] = None) -> bool:
        """Soft delete an extracted record and record audit action."""
        record = ExtractionService.get_record(db, record_id)
        old_state = record_to_values_dict(record)

        record.is_deleted = True
        audit = RecordReviewAction(
            id=generate_id("act_"),
            record_id=record.id,
            action="delete",
            old_values=old_state,
            new_values=None,
            reason="Soft deleted via API",
            reviewer_id=reviewer_email,
        )
        db.add(audit)
        db.commit()
        return True

    @staticmethod
    def get_record_history(db: Session, record_id: str) -> List[RecordReviewAction]:
        """Problem 8: Retrieve audit history actions for a record."""
        # Check record exists
        ExtractionService.get_record(db, record_id)
        stmt = (
            select(RecordReviewAction)
            .where(RecordReviewAction.record_id == record_id)
            .order_by(RecordReviewAction.created_at.desc())
        )
        return db.execute(stmt).scalars().all()

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
            select(ExtractedRecord).where(
                ExtractedRecord.document_id == document_id,
                ExtractedRecord.is_deleted == False,
            )
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
    def get_review_summary(db: Session, project_id: str) -> ReviewSummaryResponse:
        """Problem 21: Compute review summary, grouping by_vendor by supplier and by_manufacturer by brand."""
        from app.models.vendor import Vendor
        records = db.execute(
            select(ExtractedRecord).where(
                ExtractedRecord.project_id == project_id,
                ExtractedRecord.is_deleted == False,
            )
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

        docs = db.execute(select(Document).where(Document.project_id == project_id)).scalars().all()
        doc_vendor_map = {}
        vendors = {v.id: v.name for v in db.execute(select(Vendor).where(Vendor.project_id == project_id)).scalars().all()}
        for d in docs:
            if d.vendor_id and d.vendor_id in vendors:
                doc_vendor_map[d.id] = vendors[d.vendor_id]
            elif d.source == "plan":
                doc_vendor_map[d.id] = "Plan (Purview)"
            else:
                doc_vendor_map[d.id] = "Unspecified Supplier"

        by_type: Dict[str, int] = {}
        by_vendor: Dict[str, int] = {}
        by_manufacturer: Dict[str, int] = {}
        for r in records:
            by_type[r.record_type] = by_type.get(r.record_type, 0) + 1
            # Supplier name from document / vendor
            supplier_name = doc_vendor_map.get(r.document_id, r.vendor or "Unspecified Supplier")
            by_vendor[supplier_name] = by_vendor.get(supplier_name, 0) + 1
            # Brand / maker
            mfg_name = r.manufacturer or r.vendor or "Unspecified Manufacturer"
            by_manufacturer[mfg_name] = by_manufacturer.get(mfg_name, 0) + 1

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
            by_manufacturer=by_manufacturer,
        )

=======
        return results
>>>>>>> 2d848e6 (Improve AI extraction and document parsing)
