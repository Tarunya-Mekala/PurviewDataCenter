from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

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


class ExtractionService:

    # =========================================================
    # SOURCE PARSING
    # =========================================================

    @staticmethod
    def get_source_content(
        file_path: Path,
    ) -> str:
        """
        Parse a source document while preserving structure.

        File extension determines HOW to read the file.

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

    @staticmethod
    def extract_document_with_ai(
        db: Session,
        document_id: str,
        model: Optional[str] = None,
    ) -> dict[str, Any]:

        doc = db.execute(
            select(Document).where(
                Document.id == document_id
            )
        ).scalar_one_or_none()

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

                    project_id=doc.project_id,

                    document_id=doc.id,

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

                    is_manually_added=False,
                )

                db.add(record)

                records_saved += 1

            # -------------------------------------------------
            # UPDATE DOCUMENT
            # -------------------------------------------------

            doc.status = "extracted"
            doc.error_message = None

            db.commit()

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

        return [
            record.model_dump()
            for record in result.records
        ]

    # =========================================================
    # STATUS
    # =========================================================

    @staticmethod
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
                )

        return results