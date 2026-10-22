import html
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extracted_record import ExtractedRecord
from app.models.project import Project
from app.schemas.record import ReviewStatus


class ReportService:
    """Service for generating professional Excel workbooks, previews, and HTML spreadsheets for extracted documents."""

    # ------------------------------------------------------------------
    # Excel Palette & Styling Constants
    # ------------------------------------------------------------------
    FONT_FAMILY = "Segoe UI"
    
    # Colors (HEX without # for openpyxl)
    COLOR_PRIMARY_NAVY = "1E293B"       # Slate 800 - Main Header
    COLOR_HEADER_TEXT = "FFFFFF"        # White
    COLOR_SUBHEADER_BG = "F1F5F9"       # Slate 100
    COLOR_ZEBRA_ROW = "F8FAFC"          # Slate 50
    COLOR_BORDER = "CBD5E1"             # Slate 300
    COLOR_ACCENT_GREEN = "107C41"       # Excel Green

    # Status badge colors (fill, text)
    STATUS_COLORS = {
        ReviewStatus.APPROVED.value: ("DCFCE7", "166534"),        # Emerald 100 / 800
        ReviewStatus.MODIFIED.value: ("FEF3C7", "92400E"),        # Amber 100 / 800
        ReviewStatus.REJECTED.value: ("FEE2E2", "991B1B"),        # Rose 100 / 800
        ReviewStatus.PENDING_REVIEW.value: ("F1F5F9", "475569"),   # Slate 100 / 600
    }

    @staticmethod
    def _get_thin_border() -> Border:
        thin_side = Side(border_style="thin", color=ReportService.COLOR_BORDER)
        return Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    @staticmethod
    def _get_double_bottom_border() -> Border:
        thin_side = Side(border_style="thin", color=ReportService.COLOR_BORDER)
        double_side = Side(border_style="double", color=ReportService.COLOR_PRIMARY_NAVY)
        return Border(left=thin_side, right=thin_side, top=thin_side, bottom=double_side)

    # ------------------------------------------------------------------
    # Document Excel Workbook Generation
    # ------------------------------------------------------------------
    @classmethod
    def generate_document_excel(
        cls,
        db: Session,
        document_id: str,
    ) -> Tuple[bytes, str]:
        """Generate an Excel workbook (.xlsx) containing all records extracted from a document."""
        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        records = db.execute(
            select(ExtractedRecord)
            .where(ExtractedRecord.document_id == document_id)
            .order_by(ExtractedRecord.created_at.asc())
        ).scalars().all()

        wb = openpyxl.Workbook()

        # Sheet 1: Extracted Records
        ws_records = wb.active
        ws_records.title = "Extracted Records"
        cls._populate_records_sheet(ws_records, records, doc_name=doc.filename)

        # Sheet 2: Document Overview & Metrics
        ws_overview = wb.create_sheet(title="Document Overview")
        cls._populate_document_overview_sheet(ws_overview, doc, records)

        # Save to in-memory bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # Safe filename
        safe_base = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in doc.filename)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        filename = f"Extracted_lines_-_internal_data_export_{safe_base}_{timestamp}.xlsx"

        return output.getvalue(), filename

    # ------------------------------------------------------------------
    # Project Excel Workbook Generation
    # ------------------------------------------------------------------
    @classmethod
    def generate_project_excel(
        cls,
        db: Session,
        project_id: str,
    ) -> Tuple[bytes, str]:
        """Generate a consolidated Excel workbook (.xlsx) containing all records extracted in a project."""
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        records = db.execute(
            select(ExtractedRecord)
            .where(ExtractedRecord.project_id == project_id)
            .order_by(ExtractedRecord.created_at.asc())
        ).scalars().all()

        docs = db.execute(
            select(Document).where(Document.project_id == project_id)
        ).scalars().all()

        wb = openpyxl.Workbook()

        # Sheet 1: All Records
        ws_records = wb.active
        ws_records.title = "All Project Records"
        cls._populate_records_sheet(ws_records, records, include_doc_col=True)

        # Sheet 2: Documents Summary
        ws_docs = wb.create_sheet(title="Documents Summary")
        cls._populate_project_documents_sheet(ws_docs, docs, records)

        # Sheet 3: Project Overview
        ws_overview = wb.create_sheet(title="Project Overview")
        cls._populate_project_overview_sheet(ws_overview, project, docs, records)

        # Save to in-memory bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        safe_base = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in project.name)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        filename = f"Extracted_lines_-_internal_data_export_{safe_base}_{timestamp}.xlsx"

        try:
            from app.api.audit import record_audit_log
            record_audit_log(
                db=db,
                action="export",
                resource_type="export",
                project_id=project_id,
                details={"filename": filename, "format": "excel", "total_records": len(records)},
            )
        except Exception:
            pass

        return output.getvalue(), filename

    # ------------------------------------------------------------------
    # Populate Records Sheet
    # ------------------------------------------------------------------
    @classmethod
    def _populate_records_sheet(
        cls,
        ws: Any,
        records: List[ExtractedRecord],
        doc_name: Optional[str] = None,
        include_doc_col: bool = False,
    ) -> None:
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Line #",
            "Record ID",
            "Part Number",
            "Description",
            "Quantity",
            "Unit",
            "Category",
            "Record Type",
            "Vendor",
            "Location / Rack RU",
            "Source Device",
            "Source Port",
            "Target Device",
            "Target Port",
            "Cable Type",
            "Confidence Score",
            "Review Status",
            "Reviewed By",
            "Reviewed At",
            "Review Notes",
            "Manually Added",
            "Source Sheet",
            "Source Row",
        ]

        if include_doc_col:
            headers.insert(2, "Document ID")

        ws.append(headers)

        header_font = Font(name=cls.FONT_FAMILY, size=11, bold=True, color=cls.COLOR_HEADER_TEXT)
        header_fill = PatternFill(start_color=cls.COLOR_PRIMARY_NAVY, end_color=cls.COLOR_PRIMARY_NAVY, fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws.row_dimensions[1].height = 28
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = cls._get_thin_border()

        thin_border = cls._get_thin_border()
        zebra_fill = PatternFill(start_color=cls.COLOR_ZEBRA_ROW, end_color=cls.COLOR_ZEBRA_ROW, fill_type="solid")
        white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        regular_font = Font(name=cls.FONT_FAMILY, size=10)
        bold_font = Font(name=cls.FONT_FAMILY, size=10, bold=True)

        for line_num, r in enumerate(records, start=1):
            row_idx = line_num + 1
            ws.row_dimensions[row_idx].height = 20

            # Determine background fill for alternating rows
            row_fill = zebra_fill if (line_num % 2 == 0) else white_fill

            reviewed_at_str = (
                r.reviewed_at.strftime("%Y-%m-%d %H:%M") if r.reviewed_at else ""
            )

            row_data = [
                line_num,
                r.id,
                r.part_number or "",
                r.description or "",
                r.quantity if r.quantity is not None else 1.0,
                r.unit or "pcs",
                r.category or "",
                r.record_type or "bom_item",
                r.vendor or "",
                r.location or "",
                r.source_device or "",
                r.source_port or "",
                r.target_device or "",
                r.target_port or "",
                r.cable_type or "",
                r.confidence_score if r.confidence_score is not None else 1.0,
                r.review_status or "pending_review",
                r.reviewed_by or "",
                reviewed_at_str,
                r.review_notes or "",
                "Yes" if r.is_manually_added else "No",
                r.source_sheet or "",
                r.source_row if r.source_row is not None else "",
            ]

            if include_doc_col:
                row_data.insert(2, r.document_id)

            ws.append(row_data)

            # Style each cell in data row
            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = regular_font
                cell.fill = row_fill
                cell.border = thin_border

                col_name = headers[col_idx - 1]

                # Part Number bold
                if col_name == "Part Number":
                    cell.font = bold_font
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                # Line #, Unit, Location, Ports centered
                elif col_name in ("Line #", "Unit", "Location / Rack RU", "Source Port", "Target Port", "Manually Added", "Source Row"):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                # Quantity formatted
                elif col_name == "Quantity":
                    cell.number_format = "#,##0.##"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                # Confidence Score formatted as percentage
                elif col_name == "Confidence Score":
                    cell.number_format = "0.0%"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                # Review Status badge coloring
                elif col_name == "Review Status":
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    status_val = str(val)
                    if status_val in cls.STATUS_COLORS:
                        fill_hex, text_hex = cls.STATUS_COLORS[status_val]
                        cell.fill = PatternFill(start_color=fill_hex, end_color=fill_hex, fill_type="solid")
                        cell.font = Font(name=cls.FONT_FAMILY, size=10, bold=True, color=text_hex)
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        # Summary / Totals Row if records exist
        total_rows = len(records)
        if total_rows > 0:
            summary_row_idx = total_rows + 2
            ws.row_dimensions[summary_row_idx].height = 24
            
            # Find column indices
            qty_col_letter = None
            conf_col_letter = None
            for idx, h in enumerate(headers, start=1):
                if h == "Quantity":
                    qty_col_letter = get_column_letter(idx)
                elif h == "Confidence Score":
                    conf_col_letter = get_column_letter(idx)

            summary_font = Font(name=cls.FONT_FAMILY, size=11, bold=True, color=cls.COLOR_PRIMARY_NAVY)
            summary_fill = PatternFill(start_color=cls.COLOR_SUBHEADER_BG, end_color=cls.COLOR_SUBHEADER_BG, fill_type="solid")
            double_border = cls._get_double_bottom_border()

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=summary_row_idx, column=col_idx)
                cell.fill = summary_fill
                cell.font = summary_font
                cell.border = double_border

            # Label in col 1 / 2
            label_cell = ws.cell(row=summary_row_idx, column=1)
            label_cell.value = f"Total Items: {total_rows}"
            label_cell.alignment = Alignment(horizontal="left", vertical="center")

            # Sum of quantities
            if qty_col_letter:
                qty_cell = ws.cell(row=summary_row_idx, column=headers.index("Quantity") + 1)
                qty_cell.value = f"=SUM({qty_col_letter}2:{qty_col_letter}{total_rows + 1})"
                qty_cell.number_format = "#,##0.##"
                qty_cell.alignment = Alignment(horizontal="right", vertical="center")

            # Average confidence
            if conf_col_letter:
                conf_cell = ws.cell(row=summary_row_idx, column=headers.index("Confidence Score") + 1)
                conf_cell.value = f"=AVERAGE({conf_col_letter}2:{conf_col_letter}{total_rows + 1})"
                conf_cell.number_format = "0.0%"
                conf_cell.alignment = Alignment(horizontal="right", vertical="center")

        # Enable Freeze Panes below header row
        ws.freeze_panes = "A2"

        # Enable AutoFilter across all headers
        last_col = get_column_letter(len(headers))
        last_row = max(len(records) + 1, 2)
        ws.auto_filter.ref = f"A1:{last_col}{last_row}"

        # Auto-adjust column widths with generous minimums
        cls._autofit_columns(ws, headers)

    # ------------------------------------------------------------------
    # Populate Document Overview Sheet
    # ------------------------------------------------------------------
    @classmethod
    def _populate_document_overview_sheet(
        cls,
        ws: Any,
        doc: Document,
        records: List[ExtractedRecord],
    ) -> None:
        ws.views.sheetView[0].showGridLines = True

        title_font = Font(name=cls.FONT_FAMILY, size=16, bold=True, color=cls.COLOR_PRIMARY_NAVY)
        section_font = Font(name=cls.FONT_FAMILY, size=12, bold=True, color=cls.COLOR_PRIMARY_NAVY)
        header_font = Font(name=cls.FONT_FAMILY, size=10, bold=True, color=cls.COLOR_HEADER_TEXT)
        header_fill = PatternFill(start_color=cls.COLOR_PRIMARY_NAVY, end_color=cls.COLOR_PRIMARY_NAVY, fill_type="solid")
        label_font = Font(name=cls.FONT_FAMILY, size=10, bold=True)
        val_font = Font(name=cls.FONT_FAMILY, size=10)
        thin_border = cls._get_thin_border()
        zebra_fill = PatternFill(start_color=cls.COLOR_ZEBRA_ROW, end_color=cls.COLOR_ZEBRA_ROW, fill_type="solid")

        # Title Banner
        ws.merge_cells("A1:D1")
        title_cell = ws["A1"]
        title_cell.value = f"Extracted lines – internal data export (Extraction Overview): {doc.filename}"
        title_cell.font = title_font
        title_cell.alignment = Alignment(vertical="center")
        ws.row_dimensions[1].height = 32

        # Metadata Block
        meta_items = [
            ("Document ID", doc.id),
            ("Filename", doc.filename),
            ("Document Type", doc.document_type.upper()),
            ("Extraction Status", doc.status.upper()),
            ("Project ID", doc.project_id),
            ("File Size", f"{doc.file_size / 1024:.1f} KB" if doc.file_size else "0 KB"),
            ("Uploaded At", doc.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if doc.created_at else ""),
            ("Total Records Extracted", len(records)),
            ("Export Timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")),
        ]

        current_row = 3
        ws.cell(row=current_row, column=1, value="Document Metadata").font = section_font
        current_row += 1

        for label, val in meta_items:
            cell_lbl = ws.cell(row=current_row, column=1, value=label)
            cell_lbl.font = label_font
            cell_lbl.border = thin_border
            cell_lbl.fill = zebra_fill

            cell_val = ws.cell(row=current_row, column=2, value=val)
            cell_val.font = val_font
            cell_val.border = thin_border
            current_row += 1

        # Review Status Breakdown Section
        current_row += 1
        ws.cell(row=current_row, column=1, value="Human Review Breakdown").font = section_font
        current_row += 1

        status_headers = ["Review Status", "Record Count", "Percentage of Total"]
        for col_idx, h in enumerate(status_headers, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        current_row += 1

        total_recs = len(records)
        statuses = [
            ("Pending Review", ReviewStatus.PENDING_REVIEW.value),
            ("Approved", ReviewStatus.APPROVED.value),
            ("Modified", ReviewStatus.MODIFIED.value),
            ("Rejected", ReviewStatus.REJECTED.value),
        ]

        for display_name, st_val in statuses:
            count = sum(1 for r in records if r.review_status == st_val)
            pct = (count / total_recs) if total_recs > 0 else 0.0

            c_status = ws.cell(row=current_row, column=1, value=display_name)
            c_status.font = label_font
            c_status.border = thin_border
            if st_val in cls.STATUS_COLORS:
                fill_hex, text_hex = cls.STATUS_COLORS[st_val]
                c_status.fill = PatternFill(start_color=fill_hex, end_color=fill_hex, fill_type="solid")
                c_status.font = Font(name=cls.FONT_FAMILY, size=10, bold=True, color=text_hex)

            c_count = ws.cell(row=current_row, column=2, value=count)
            c_count.font = val_font
            c_count.alignment = Alignment(horizontal="right", vertical="center")
            c_count.border = thin_border

            c_pct = ws.cell(row=current_row, column=3, value=pct)
            c_pct.font = val_font
            c_pct.number_format = "0.0%"
            c_pct.alignment = Alignment(horizontal="right", vertical="center")
            c_pct.border = thin_border

            current_row += 1

        # Vendor Distribution Section
        current_row += 1
        ws.cell(row=current_row, column=1, value="Top Hardware Vendors").font = section_font
        current_row += 1

        vendor_headers = ["Vendor / Manufacturer", "Count", "Share"]
        for col_idx, h in enumerate(vendor_headers, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        current_row += 1

        vendor_counts: Dict[str, int] = {}
        for r in records:
            v = r.vendor or "Unspecified"
            vendor_counts[v] = vendor_counts.get(v, 0) + 1

        sorted_vendors = sorted(vendor_counts.items(), key=lambda x: x[1], reverse=True)
        for v_name, count in sorted_vendors:
            pct = (count / total_recs) if total_recs > 0 else 0.0
            cv = ws.cell(row=current_row, column=1, value=v_name)
            cv.font = val_font
            cv.border = thin_border

            cc = ws.cell(row=current_row, column=2, value=count)
            cc.font = val_font
            cc.alignment = Alignment(horizontal="right", vertical="center")
            cc.border = thin_border

            cp = ws.cell(row=current_row, column=3, value=pct)
            cp.font = val_font
            cp.number_format = "0.0%"
            cp.alignment = Alignment(horizontal="right", vertical="center")
            cp.border = thin_border

            current_row += 1

        cls._autofit_columns(ws, ["Document Metadata Long Column", "Record Count Detail", "Percentage Long Header"])

    # ------------------------------------------------------------------
    # Populate Project Documents Sheet
    # ------------------------------------------------------------------
    @classmethod
    def _populate_project_documents_sheet(
        cls,
        ws: Any,
        docs: List[Document],
        records: List[ExtractedRecord],
    ) -> None:
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Document ID",
            "Filename",
            "Document Type",
            "Status",
            "File Size (KB)",
            "Extracted Records",
            "Approved",
            "Pending",
            "Modified",
            "Rejected",
            "Uploaded At",
        ]

        ws.append(headers)
        header_font = Font(name=cls.FONT_FAMILY, size=11, bold=True, color=cls.COLOR_HEADER_TEXT)
        header_fill = PatternFill(start_color=cls.COLOR_PRIMARY_NAVY, end_color=cls.COLOR_PRIMARY_NAVY, fill_type="solid")
        ws.row_dimensions[1].height = 26

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = cls._get_thin_border()

        thin_border = cls._get_thin_border()
        reg_font = Font(name=cls.FONT_FAMILY, size=10)
        zebra_fill = PatternFill(start_color=cls.COLOR_ZEBRA_ROW, end_color=cls.COLOR_ZEBRA_ROW, fill_type="solid")

        # Group records by doc id
        doc_records: Dict[str, List[ExtractedRecord]] = {}
        for r in records:
            doc_records.setdefault(r.document_id, []).append(r)

        for line_num, d in enumerate(docs, start=1):
            row_idx = line_num + 1
            ws.row_dimensions[row_idx].height = 20
            d_recs = doc_records.get(d.id, [])
            appr = sum(1 for r in d_recs if r.review_status == ReviewStatus.APPROVED.value)
            pend = sum(1 for r in d_recs if r.review_status == ReviewStatus.PENDING_REVIEW.value)
            mod = sum(1 for r in d_recs if r.review_status == ReviewStatus.MODIFIED.value)
            rej = sum(1 for r in d_recs if r.review_status == ReviewStatus.REJECTED.value)

            row_data = [
                d.id,
                d.filename,
                d.document_type.upper(),
                d.status.upper(),
                round(d.file_size / 1024, 1) if d.file_size else 0.0,
                len(d_recs),
                appr,
                pend,
                mod,
                rej,
                d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "",
            ]
            ws.append(row_data)

            row_fill = zebra_fill if (line_num % 2 == 0) else PatternFill(fill_type=None)
            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = reg_font
                cell.border = thin_border
                if row_fill.fill_type:
                    cell.fill = row_fill

        ws.freeze_panes = "A2"
        cls._autofit_columns(ws, headers)

    # ------------------------------------------------------------------
    # Populate Project Overview Sheet
    # ------------------------------------------------------------------
    @classmethod
    def _populate_project_overview_sheet(
        cls,
        ws: Any,
        project: Project,
        docs: List[Document],
        records: List[ExtractedRecord],
    ) -> None:
        ws.views.sheetView[0].showGridLines = True
        title_font = Font(name=cls.FONT_FAMILY, size=16, bold=True, color=cls.COLOR_PRIMARY_NAVY)
        section_font = Font(name=cls.FONT_FAMILY, size=12, bold=True, color=cls.COLOR_PRIMARY_NAVY)
        label_font = Font(name=cls.FONT_FAMILY, size=10, bold=True)
        val_font = Font(name=cls.FONT_FAMILY, size=10)
        thin_border = cls._get_thin_border()
        zebra_fill = PatternFill(start_color=cls.COLOR_ZEBRA_ROW, end_color=cls.COLOR_ZEBRA_ROW, fill_type="solid")

        ws.merge_cells("A1:C1")
        title_cell = ws["A1"]
        title_cell.value = f"Extracted lines – internal data export (Project Summary): {project.name}"
        title_cell.font = title_font
        ws.row_dimensions[1].height = 32

        meta_items = [
            ("Project ID", project.id),
            ("Project Name", project.name),
            ("Description", project.description or ""),
            ("Total Uploaded Documents", len(docs)),
            ("Total Extracted Records", len(records)),
            ("Created At", project.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if project.created_at else ""),
        ]

        current_row = 3
        for label, val in meta_items:
            cl = ws.cell(row=current_row, column=1, value=label)
            cl.font = label_font
            cl.fill = zebra_fill
            cl.border = thin_border

            cv = ws.cell(row=current_row, column=2, value=val)
            cv.font = val_font
            cv.border = thin_border
            current_row += 1

        cls._autofit_columns(ws, ["Project Metric Label", "Project Metric Long Description"])

    # ------------------------------------------------------------------
    # Auto-Fit Columns Helper
    # ------------------------------------------------------------------
    @staticmethod
    def _autofit_columns(ws: Any, headers: List[str]) -> None:
        """Calculate optimal column width based on max character length with generous padding."""
        for col_idx, col in enumerate(ws.columns, start=1):
            max_len = 0
            for cell in col:
                val = cell.value
                if val is not None:
                    # Ignore formula text length if it's long formula
                    val_str = str(val)
                    if not val_str.startswith("="):
                        max_len = max(max_len, len(val_str))
            col_letter = get_column_letter(col_idx)
            header_len = len(headers[col_idx - 1]) if col_idx - 1 < len(headers) else 10
            optimal_width = max(max_len + 4, header_len + 4, 12)
            ws.column_dimensions[col_letter].width = min(optimal_width, 60)

    # ------------------------------------------------------------------
    # Excel Grid Preview (JSON Structure)
    # ------------------------------------------------------------------
    @classmethod
    def get_document_excel_preview(
        cls,
        db: Session,
        document_id: str,
    ) -> Dict[str, Any]:
        """Return a structured spreadsheet representation for UI grid components."""
        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        records = db.execute(
            select(ExtractedRecord)
            .where(ExtractedRecord.document_id == document_id)
            .order_by(ExtractedRecord.created_at.asc())
        ).scalars().all()

        headers = [
            "Line #",
            "Part Number",
            "Description",
            "Quantity",
            "Unit",
            "Category",
            "Record Type",
            "Vendor",
            "Location",
            "Source Device",
            "Target Device",
            "Confidence Score",
            "Review Status",
            "Reviewed By",
            "Review Notes",
        ]

        rows = []
        for idx, r in enumerate(records, start=1):
            rows.append([
                idx,
                r.part_number or "",
                r.description or "",
                r.quantity if r.quantity is not None else 1.0,
                r.unit or "pcs",
                r.category or "",
                r.record_type or "bom_item",
                r.vendor or "",
                r.location or "",
                r.source_device or "",
                r.target_device or "",
                round(r.confidence_score * 100, 1) if r.confidence_score is not None else 100.0,
                r.review_status,
                r.reviewed_by or "",
                r.review_notes or "",
            ])

        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "document_type": doc.document_type,
            "status": doc.status,
            "total_records": len(records),
            "sheet_name": "Extracted Records",
            "columns": headers,
            "rows": rows,
            "summary": {
                "total": len(records),
                "approved": sum(1 for r in records if r.review_status in [ReviewStatus.APPROVED.value, "read_clearly"]),
                "read_clearly": sum(1 for r in records if r.review_status == "read_clearly"),
                "pending": sum(1 for r in records if r.review_status == ReviewStatus.PENDING_REVIEW.value),
                "modified": sum(1 for r in records if r.review_status == ReviewStatus.MODIFIED.value),
                "rejected": sum(1 for r in records if r.review_status == ReviewStatus.REJECTED.value),
                "avg_confidence": (
                    round(sum(r.confidence_score for r in records) / len(records) * 100, 1)
                    if records
                    else 0.0
                ),
            },
        }

    # ------------------------------------------------------------------
    # Project Excel Grid Preview (JSON Structure)
    # ------------------------------------------------------------------
    @classmethod
    def get_project_excel_preview(
        cls,
        db: Session,
        project_id: str,
    ) -> Dict[str, Any]:
        """Return structured project spreadsheet representation for UI grid components."""
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        records = db.execute(
            select(ExtractedRecord)
            .where(ExtractedRecord.project_id == project_id)
            .order_by(ExtractedRecord.created_at.asc())
        ).scalars().all()

        headers = [
            "Line #",
            "Document ID",
            "Part Number",
            "Description",
            "Quantity",
            "Unit",
            "Category",
            "Vendor",
            "Location",
            "Confidence Score",
            "Review Status",
        ]

        rows = []
        for idx, r in enumerate(records, start=1):
            rows.append([
                idx,
                r.document_id,
                r.part_number or "",
                r.description or "",
                r.quantity if r.quantity is not None else 1.0,
                r.unit or "pcs",
                r.category or "",
                r.vendor or "",
                r.location or "",
                round(r.confidence_score * 100, 1) if r.confidence_score is not None else 100.0,
                r.review_status,
            ])

        summary = {
            "total": len(records),
            "approved": sum(1 for r in records if r.review_status in [ReviewStatus.APPROVED.value, "read_clearly"]),
            "pending": sum(1 for r in records if r.review_status == ReviewStatus.PENDING_REVIEW.value),
            "modified": sum(1 for r in records if r.review_status == ReviewStatus.MODIFIED.value),
            "rejected": sum(1 for r in records if r.review_status == ReviewStatus.REJECTED.value),
            "read_clearly": sum(1 for r in records if r.review_status == "read_clearly"),
            "avg_confidence": (
                round(sum(r.confidence_score for r in records) / len(records) * 100, 1)
                if records
                else 0.0
            ),
        }

        return {
            "project_id": project.id,
            "project_name": project.name,
            "total_records": len(records),
            "sheet_name": "All Project Records",
            "columns": headers,
            "rows": rows,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Standalone Interactive HTML "Show as Excel" Spreadsheet View
    # ------------------------------------------------------------------
    @classmethod
    def render_excel_html_view(
        cls,
        db: Session,
        document_id: str,
        token: Optional[str] = None,
    ) -> str:
        """Render a complete, interactive spreadsheet web UI simulating Microsoft Excel in browser."""
        doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        records = db.execute(
            select(ExtractedRecord)
            .where(ExtractedRecord.document_id == document_id)
            .order_by(ExtractedRecord.created_at.asc())
        ).scalars().all()

        total = len(records)
        appr_count = sum(1 for r in records if r.review_status == ReviewStatus.APPROVED.value)
        pend_count = sum(1 for r in records if r.review_status == ReviewStatus.PENDING_REVIEW.value)
        mod_count = sum(1 for r in records if r.review_status == ReviewStatus.MODIFIED.value)
        rej_count = sum(1 for r in records if r.review_status == ReviewStatus.REJECTED.value)
        avg_conf = (
            round(sum(r.confidence_score for r in records) / total * 100, 1)
            if total > 0
            else 0.0
        )

        # Download button with short-lived signed link if token provided, otherwise omit
        download_btn_html = ""
        if token:
            download_url = f"/api/v1/documents/{document_id}/excel?token={token}"
            download_btn_html = f"""
            <a href="{download_url}" download class="btn btn-white" id="download-excel-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download .xlsx
            </a>
            """

        # Generate rows HTML
        rows_html = []
        for idx, r in enumerate(records, start=1):
            st = r.review_status or "pending_review"
            badge_class = {
                "approved": "badge-approved",
                "modified": "badge-modified",
                "rejected": "badge-rejected",
                "pending_review": "badge-pending",
            }.get(st, "badge-pending")

            conf_pct = f"{round(r.confidence_score * 100, 1)}%" if r.confidence_score is not None else "100%"
            qty_str = f"{r.quantity:g}" if r.quantity is not None else "1"

            rows_html.append(f"""
                <tr data-status="{html.escape(st)}" data-vendor="{html.escape(r.vendor or '')}" data-category="{html.escape(r.category or '')}">
                    <td class="col-row-num">{idx}</td>
                    <td class="col-part-number"><strong>{html.escape(r.part_number or '')}</strong></td>
                    <td class="col-desc" title="{html.escape(r.description or '')}">{html.escape(r.description or '')}</td>
                    <td class="col-qty text-right">{html.escape(qty_str)}</td>
                    <td class="col-unit text-center">{html.escape(r.unit or 'pcs')}</td>
                    <td class="col-vendor">{html.escape(r.vendor or '')}</td>
                    <td class="col-category">{html.escape(r.category or '')}</td>
                    <td class="col-loc text-center">{html.escape(r.location or '')}</td>
                    <td class="col-source">{html.escape(r.source_device or '')} {html.escape(r.source_port or '')}</td>
                    <td class="col-target">{html.escape(r.target_device or '')} {html.escape(r.target_port or '')}</td>
                    <td class="col-conf text-right">{html.escape(conf_pct)}</td>
                    <td class="col-status text-center"><span class="badge {badge_class}">{html.escape(st.replace('_', ' ').title())}</span></td>
                    <td class="col-notes">{html.escape(r.review_notes or '')}</td>
                </tr>
            """)

        records_rows_rendered = "\n".join(rows_html)

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Extracted lines – internal data export: {html.escape(doc.filename)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --excel-green: #107C41;
            --excel-green-hover: #0E6B37;
            --excel-green-light: #EBF8F0;
            --slate-900: #0F172A;
            --slate-800: #1E293B;
            --slate-700: #334155;
            --slate-600: #475569;
            --slate-500: #64748B;
            --slate-200: #E2E8F0;
            --slate-100: #F1F5F9;
            --slate-50: #F8FAFC;
            --emerald-bg: #DCFCE7;
            --emerald-text: #166534;
            --amber-bg: #FEF3C7;
            --amber-text: #92400E;
            --rose-bg: #FEE2E2;
            --rose-text: #991B1B;
            --blue-bg: #E0E7FF;
            --blue-text: #3730A3;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #F8FAFC;
            color: var(--slate-900);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        /* Ribbon & Top Navigation */
        .excel-ribbon {{
            background: linear-gradient(135deg, #107C41 0%, #0D6937 100%);
            color: #FFFFFF;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 12px rgba(16, 124, 65, 0.15);
        }}

        .ribbon-brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .excel-icon {{
            width: 32px;
            height: 32px;
            background: #FFFFFF;
            color: var(--excel-green);
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 18px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .ribbon-title h1 {{
            font-size: 18px;
            font-weight: 700;
            letter-spacing: -0.01em;
        }}

        .ribbon-title span {{
            font-size: 12px;
            opacity: 0.9;
        }}

        .ribbon-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.15s ease;
            border: none;
        }}

        .btn-white {{
            background: #FFFFFF;
            color: var(--excel-green);
            box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        }}
        .btn-white:hover {{
            background: #F1F5F9;
            transform: translateY(-1px);
        }}

        .btn-ghost {{
            background: rgba(255, 255, 255, 0.15);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }}
        .btn-ghost:hover {{
            background: rgba(255, 255, 255, 0.25);
        }}

        /* Metrics Bar */
        .metrics-bar {{
            background: #FFFFFF;
            border-bottom: 1px solid var(--slate-200);
            padding: 16px 24px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 16px;
        }}

        .metric-card {{
            background: var(--slate-50);
            border: 1px solid var(--slate-200);
            border-radius: 8px;
            padding: 12px 16px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .metric-label {{
            font-size: 12px;
            font-weight: 600;
            color: var(--slate-500);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .metric-value {{
            font-size: 22px;
            font-weight: 700;
            color: var(--slate-900);
        }}

        .metric-value.approved {{ color: var(--emerald-text); }}
        .metric-value.modified {{ color: var(--amber-text); }}
        .metric-value.rejected {{ color: var(--rose-text); }}
        .metric-value.pending {{ color: var(--slate-600); }}

        /* Toolbar */
        .toolbar {{
            background: #FFFFFF;
            border-bottom: 1px solid var(--slate-200);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            flex-wrap: wrap;
        }}

        .toolbar-group {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .search-box {{
            position: relative;
        }}

        .search-input {{
            padding: 8px 12px 8px 36px;
            border: 1px solid var(--slate-200);
            border-radius: 6px;
            font-size: 13px;
            width: 280px;
            outline: none;
            transition: all 0.2s;
        }}
        .search-input:focus {{
            border-color: var(--excel-green);
            box-shadow: 0 0 0 3px rgba(16, 124, 65, 0.12);
        }}

        .search-icon {{
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--slate-400);
            font-size: 14px;
        }}

        .select-filter {{
            padding: 8px 12px;
            border: 1px solid var(--slate-200);
            border-radius: 6px;
            font-size: 13px;
            background: #FFFFFF;
            outline: none;
            color: var(--slate-700);
            cursor: pointer;
        }}
        .select-filter:focus {{
            border-color: var(--excel-green);
        }}

        /* Spreadsheet Grid */
        .spreadsheet-container {{
            flex: 1;
            overflow: auto;
            background: #FFFFFF;
            position: relative;
        }}

        table.excel-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            white-space: nowrap;
        }}

        table.excel-table thead {{
            position: sticky;
            top: 0;
            z-index: 10;
        }}

        table.excel-table th {{
            background-color: var(--slate-800);
            color: #FFFFFF;
            font-weight: 600;
            padding: 10px 14px;
            text-align: left;
            border: 1px solid var(--slate-700);
            cursor: pointer;
            user-select: none;
        }}
        table.excel-table th:hover {{
            background-color: var(--slate-900);
        }}

        table.excel-table td {{
            padding: 8px 14px;
            border: 1px solid var(--slate-200);
            vertical-align: middle;
        }}

        table.excel-table tbody tr:nth-child(even) {{
            background-color: var(--slate-50);
        }}

        table.excel-table tbody tr:hover {{
            background-color: #F1F8F4;
        }}

        .col-row-num {{
            background-color: #F1F5F9;
            color: var(--slate-500);
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            text-align: center;
            width: 48px;
            border-right: 2px solid var(--slate-200) !important;
        }}

        .col-part-number {{
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            color: var(--slate-900);
        }}

        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}

        .badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}

        .badge-approved {{
            background-color: var(--emerald-bg);
            color: var(--emerald-text);
        }}

        .badge-modified {{
            background-color: var(--amber-bg);
            color: var(--amber-text);
        }}

        .badge-rejected {{
            background-color: var(--rose-bg);
            color: var(--rose-text);
        }}

        .badge-pending {{
            background-color: var(--slate-100);
            color: var(--slate-600);
        }}

        /* Bottom Sheet Tabs */
        .sheet-tabs {{
            background: #E2E8F0;
            border-top: 1px solid #CBD5E1;
            padding: 4px 16px 0 16px;
            display: flex;
            align-items: center;
            gap: 4px;
        }}

        .tab-btn {{
            padding: 8px 18px;
            border-radius: 6px 6px 0 0;
            font-size: 12px;
            font-weight: 600;
            background: #CBD5E1;
            color: var(--slate-700);
            border: 1px solid #94A3B8;
            border-bottom: none;
            cursor: pointer;
            transition: all 0.1s;
        }}

        .tab-btn.active {{
            background: #FFFFFF;
            color: var(--excel-green);
            border-color: #CBD5E1;
            border-bottom: 2px solid #FFFFFF;
            margin-bottom: -1px;
        }}

        /* Overview Panel */
        #overview-panel {{
            display: none;
            padding: 32px 24px;
            background: #FFFFFF;
            max-width: 900px;
            margin: 0 auto;
        }}

        .panel-card {{
            background: var(--slate-50);
            border: 1px solid var(--slate-200);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 24px;
        }}

        .panel-card h3 {{
            font-size: 15px;
            font-weight: 700;
            color: var(--slate-800);
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--slate-200);
        }}

        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            font-size: 13px;
        }}

        .meta-row {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px dashed var(--slate-200);
        }}

        .meta-row .label {{
            font-weight: 600;
            color: var(--slate-500);
        }}
    </style>
</head>
<body>

    <!-- Excel Ribbon -->
    <header class="excel-ribbon">
        <div class="ribbon-brand">
            <div class="excel-icon">X</div>
            <div class="ribbon-title">
                <h1>Extracted lines – internal data export</h1>
                <span>Document: {html.escape(doc.filename)} &bull; ID: {html.escape(doc.id)} &bull; Type: {html.escape(doc.document_type.upper())}</span>
            </div>
        </div>
        <div class="ribbon-actions">
            {download_btn_html}
            <button onclick="window.print()" class="btn btn-ghost">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
                Print
            </button>
        </div>
    </header>

    <!-- Metrics Bar -->
    <section class="metrics-bar">
        <div class="metric-card">
            <span class="metric-label">Total Line Items</span>
            <span class="metric-value" id="count-total">{total}</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">Approved</span>
            <span class="metric-value approved" id="count-approved">{appr_count}</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">Pending Review</span>
            <span class="metric-value pending" id="count-pending">{pend_count}</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">Modified</span>
            <span class="metric-value modified" id="count-modified">{mod_count}</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">Rejected</span>
            <span class="metric-value rejected" id="count-rejected">{rej_count}</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">Avg AI Confidence</span>
            <span class="metric-value">{avg_conf}%</span>
        </div>
    </section>

    <!-- Filter Toolbar -->
    <div class="toolbar">
        <div class="toolbar-group">
            <div class="search-box">
                <span class="search-icon">&#128269;</span>
                <input type="text" id="filter-search" class="search-input" placeholder="Search part number, desc, vendor...">
            </div>
            <select id="filter-status" class="select-filter">
                <option value="">All Review Statuses</option>
                <option value="pending_review">Pending Review</option>
                <option value="approved">Approved</option>
                <option value="modified">Modified</option>
                <option value="rejected">Rejected</option>
            </select>
        </div>
        <div class="toolbar-group">
            <span style="font-size: 12px; color: var(--slate-500);" id="visible-rows-counter">Showing {total} records</span>
        </div>
    </div>

    <!-- Main Table View -->
    <div class="spreadsheet-container" id="grid-container">
        <table class="excel-table" id="records-table">
            <thead>
                <tr>
                    <th class="col-row-num">#</th>
                    <th onclick="sortTable(1)">Part Number &#x25B4;&#x25BE;</th>
                    <th onclick="sortTable(2)">Description &#x25B4;&#x25BE;</th>
                    <th class="text-right" onclick="sortTable(3, true)">Qty &#x25B4;&#x25BE;</th>
                    <th class="text-center">Unit</th>
                    <th onclick="sortTable(5)">Vendor &#x25B4;&#x25BE;</th>
                    <th onclick="sortTable(6)">Category &#x25B4;&#x25BE;</th>
                    <th class="text-center">Rack RU</th>
                    <th>Source Device / Port</th>
                    <th>Target Device / Port</th>
                    <th class="text-right" onclick="sortTable(10, true)">Confidence &#x25B4;&#x25BE;</th>
                    <th class="text-center" onclick="sortTable(11)">Status &#x25B4;&#x25BE;</th>
                    <th>Review Notes</th>
                </tr>
            </thead>
            <tbody id="table-body">
                {records_rows_rendered}
            </tbody>
        </table>
    </div>

    <!-- Overview & Statistics Panel -->
    <div id="overview-panel">
        <div class="panel-card">
            <h3>Document Summary & Metadata</h3>
            <div class="meta-grid">
                <div class="meta-row"><span class="label">Document ID</span><span>{html.escape(doc.id)}</span></div>
                <div class="meta-row"><span class="label">Filename</span><span>{html.escape(doc.filename)}</span></div>
                <div class="meta-row"><span class="label">Document Type</span><span>{html.escape(doc.document_type.upper())}</span></div>
                <div class="meta-row"><span class="label">Status</span><span>{html.escape(doc.status.upper())}</span></div>
                <div class="meta-row"><span class="label">File Size</span><span>{round(doc.file_size / 1024, 1) if doc.file_size else 0} KB</span></div>
                <div class="meta-row"><span class="label">Project ID</span><span>{html.escape(doc.project_id)}</span></div>
                <div class="meta-row"><span class="label">Uploaded Date</span><span>{doc.created_at.strftime('%Y-%m-%d %H:%M') if doc.created_at else ''}</span></div>
                <div class="meta-row"><span class="label">Total Records</span><span>{total}</span></div>
            </div>
        </div>
    </div>

    <!-- Bottom Sheet Tabs -->
    <nav class="sheet-tabs">
        <button class="tab-btn active" id="tab-records" onclick="switchTab('records')">Extracted Records ({total})</button>
        <button class="tab-btn" id="tab-overview" onclick="switchTab('overview')">Document Overview & Metrics</button>
    </nav>

    <script>
        function switchTab(tabName) {{
            const gridContainer = document.getElementById('grid-container');
            const overviewPanel = document.getElementById('overview-panel');
            const tabRecords = document.getElementById('tab-records');
            const tabOverview = document.getElementById('tab-overview');

            if (tabName === 'records') {{
                gridContainer.style.display = 'block';
                overviewPanel.style.display = 'none';
                tabRecords.classList.add('active');
                tabOverview.classList.remove('active');
            }} else {{
                gridContainer.style.display = 'none';
                overviewPanel.style.display = 'block';
                tabRecords.classList.remove('active');
                tabOverview.classList.add('active');
            }}
        }}

        // Live Filtering
        const searchInput = document.getElementById('filter-search');
        const statusSelect = document.getElementById('filter-status');
        const tableBody = document.getElementById('table-body');
        const rows = tableBody.getElementsByTagName('tr');
        const counterSpan = document.getElementById('visible-rows-counter');

        function filterTable() {{
            const query = searchInput.value.toLowerCase().trim();
            const statusFilter = statusSelect.value;
            let visibleCount = 0;

            for (let i = 0; i < rows.length; i++) {{
                const row = rows[i];
                const text = row.textContent.toLowerCase();
                const rowStatus = row.getAttribute('data-status') || '';

                const matchesQuery = !query || text.includes(query);
                const matchesStatus = !statusFilter || rowStatus === statusFilter;

                if (matchesQuery && matchesStatus) {{
                    row.style.display = '';
                    visibleCount++;
                }} else {{
                    row.style.display = 'none';
                }}
            }}
            counterSpan.textContent = `Showing ${{visibleCount}} of ${{rows.length}} records`;
        }}

        searchInput.addEventListener('input', filterTable);
        statusSelect.addEventListener('change', filterTable);

        // Column Sorting
        let sortDirections = {{}};
        function sortTable(colIndex, isNumeric = false) {{
            const currentDir = sortDirections[colIndex] || 'asc';
            const newDir = currentDir === 'asc' ? 'desc' : 'asc';
            sortDirections[colIndex] = newDir;

            const rowsArray = Array.from(rows);
            rowsArray.sort((a, b) => {{
                let aVal = a.cells[colIndex].textContent.trim();
                let bVal = b.cells[colIndex].textContent.trim();

                if (isNumeric) {{
                    const aNum = parseFloat(aVal.replace(/[^0-9.-]/g, '')) || 0;
                    const bNum = parseFloat(bVal.replace(/[^0-9.-]/g, '')) || 0;
                    return newDir === 'asc' ? aNum - bNum : bNum - aNum;
                }} else {{
                    return newDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                }}
            }});

            rowsArray.forEach(row => tableBody.appendChild(row));
        }}
    </script>
</body>
</html>
"""
        return html_template

    # ------------------------------------------------------------------
    # Standalone Interactive HTML "Show as Excel" for Project
    # ------------------------------------------------------------------
    @classmethod
    def render_project_excel_html_view(
        cls,
        db: Session,
        project_id: str,
        token: Optional[str] = None,
    ) -> str:
        """Render a complete, interactive spreadsheet web UI for all records in a project."""
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        records = db.execute(
            select(ExtractedRecord)
            .where(ExtractedRecord.project_id == project_id)
            .order_by(ExtractedRecord.created_at.asc())
        ).scalars().all()

        total = len(records)
        appr_count = sum(1 for r in records if r.review_status == ReviewStatus.APPROVED.value)
        pend_count = sum(1 for r in records if r.review_status == ReviewStatus.PENDING_REVIEW.value)
        mod_count = sum(1 for r in records if r.review_status == ReviewStatus.MODIFIED.value)
        rej_count = sum(1 for r in records if r.review_status == ReviewStatus.REJECTED.value)
        avg_conf = (
            round(sum(r.confidence_score for r in records) / total * 100, 1)
            if total > 0
            else 0.0
        )

        download_btn_html = ""
        if token:
            download_url = f"/api/v1/projects/{project_id}/excel?token={token}"
            download_btn_html = f"""
            <a href="{download_url}" download class="btn btn-white" id="download-excel-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download Project .xlsx
            </a>
            """

        rows_html = []
        for idx, r in enumerate(records, start=1):
            st = r.review_status or "pending_review"
            badge_class = {
                "approved": "badge-approved",
                "modified": "badge-modified",
                "rejected": "badge-rejected",
                "pending_review": "badge-pending",
            }.get(st, "badge-pending")

            conf_pct = f"{round(r.confidence_score * 100, 1)}%" if r.confidence_score is not None else "100%"
            qty_str = f"{r.quantity:g}" if r.quantity is not None else "1"

            rows_html.append(f"""
                <tr data-status="{html.escape(st)}" data-vendor="{html.escape(r.vendor or '')}">
                    <td class="col-row-num">{idx}</td>
                    <td class="col-part-number"><strong>{html.escape(r.part_number or '')}</strong></td>
                    <td class="col-desc" title="{html.escape(r.description or '')}">{html.escape(r.description or '')}</td>
                    <td class="col-qty text-right">{html.escape(qty_str)}</td>
                    <td class="col-unit text-center">{html.escape(r.unit or 'pcs')}</td>
                    <td class="col-vendor">{html.escape(r.vendor or '')}</td>
                    <td class="col-category">{html.escape(r.category or '')}</td>
                    <td class="col-loc text-center">{html.escape(r.location or '')}</td>
                    <td class="col-doc" style="font-size: 11px; color: var(--slate-500);">{html.escape(r.document_id)}</td>
                    <td class="col-conf text-right">{html.escape(conf_pct)}</td>
                    <td class="col-status text-center"><span class="badge {badge_class}">{html.escape(st.replace('_', ' ').title())}</span></td>
                    <td class="col-notes">{html.escape(r.review_notes or '')}</td>
                </tr>
            """)

        records_rows_rendered = "\n".join(rows_html)

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Extracted lines – internal data export: {html.escape(project.name)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --excel-green: #107C41;
            --excel-green-hover: #0E6B37;
            --slate-900: #0F172A;
            --slate-800: #1E293B;
            --slate-700: #334155;
            --slate-500: #64748B;
            --slate-200: #E2E8F0;
            --slate-100: #F1F5F9;
            --slate-50: #F8FAFC;
            --emerald-bg: #DCFCE7;
            --emerald-text: #166534;
            --amber-bg: #FEF3C7;
            --amber-text: #92400E;
            --rose-bg: #FEE2E2;
            --rose-text: #991B1B;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: #F8FAFC;
            color: var(--slate-900);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        .excel-ribbon {{
            background: linear-gradient(135deg, #107C41 0%, #0D6937 100%);
            color: #FFFFFF;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .ribbon-brand {{ display: flex; align-items: center; gap: 12px; }}
        .excel-icon {{
            width: 32px; height: 32px; background: #FFFFFF; color: var(--excel-green);
            border-radius: 6px; display: flex; align-items: center; justify-content: center;
            font-weight: 800; font-size: 18px;
        }}
        .ribbon-title h1 {{ font-size: 18px; font-weight: 700; }}
        .ribbon-title span {{ font-size: 12px; opacity: 0.9; }}
        .btn {{
            display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px;
            border-radius: 6px; font-size: 13px; font-weight: 600; text-decoration: none;
            cursor: pointer; border: none;
        }}
        .btn-white {{ background: #FFFFFF; color: var(--excel-green); }}
        .btn-white:hover {{ background: #F1F5F9; }}
        .metrics-bar {{
            background: #FFFFFF; border-bottom: 1px solid var(--slate-200);
            padding: 16px 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px;
        }}
        .metric-card {{
            background: var(--slate-50); border: 1px solid var(--slate-200);
            border-radius: 8px; padding: 12px 16px; display: flex; flex-direction: column; gap: 4px;
        }}
        .metric-label {{ font-size: 12px; font-weight: 600; color: var(--slate-500); text-transform: uppercase; }}
        .metric-value {{ font-size: 22px; font-weight: 700; }}
        .metric-value.approved {{ color: var(--emerald-text); }}
        .metric-value.modified {{ color: var(--amber-text); }}
        .metric-value.rejected {{ color: var(--rose-text); }}
        .toolbar {{
            background: #FFFFFF; border-bottom: 1px solid var(--slate-200);
            padding: 12px 24px; display: flex; align-items: center; justify-content: space-between;
        }}
        .search-input {{
            padding: 8px 14px; border: 1px solid var(--slate-200); border-radius: 6px;
            font-size: 13px; width: 320px; outline: none;
        }}
        .spreadsheet-container {{ flex: 1; overflow: auto; background: #FFFFFF; }}
        table.excel-table {{ width: 100%; border-collapse: collapse; font-size: 13px; white-space: nowrap; }}
        table.excel-table thead {{ position: sticky; top: 0; z-index: 10; }}
        table.excel-table th {{
            background: var(--slate-800); color: #FFFFFF; font-weight: 600;
            padding: 10px 14px; text-align: left; border: 1px solid var(--slate-700); cursor: pointer;
        }}
        table.excel-table td {{ padding: 8px 14px; border: 1px solid var(--slate-200); }}
        table.excel-table tbody tr:nth-child(even) {{ background: var(--slate-50); }}
        table.excel-table tbody tr:hover {{ background: #F1F8F4; }}
        .col-row-num {{ background: #F1F5F9; color: var(--slate-500); font-family: 'JetBrains Mono', monospace; text-align: center; }}
        .col-part-number {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; }}
        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}
        .badge {{ padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; }}
        .badge-approved {{ background: var(--emerald-bg); color: var(--emerald-text); }}
        .badge-modified {{ background: var(--amber-bg); color: var(--amber-text); }}
        .badge-rejected {{ background: var(--rose-bg); color: var(--rose-text); }}
        .badge-pending {{ background: var(--slate-100); color: var(--slate-500); }}
    </style>
</head>
<body>
    <header class="excel-ribbon">
        <div class="ribbon-brand">
            <div class="excel-icon">X</div>
            <div class="ribbon-title">
                <h1>Extracted lines – internal data export</h1>
                <span>Project: {html.escape(project.name)} &bull; Consolidated Project Records &bull; ID: {html.escape(project.id)}</span>
            </div>
        </div>
        <div>
            {download_btn_html}
        </div>
    </header>

    <section class="metrics-bar">
        <div class="metric-card"><span class="metric-label">Total Records</span><span class="metric-value">{total}</span></div>
        <div class="metric-card"><span class="metric-label">Approved</span><span class="metric-value approved">{appr_count}</span></div>
        <div class="metric-card"><span class="metric-label">Pending</span><span class="metric-value">{pend_count}</span></div>
        <div class="metric-card"><span class="metric-label">Modified</span><span class="metric-value modified">{mod_count}</span></div>
        <div class="metric-card"><span class="metric-label">Rejected</span><span class="metric-value rejected">{rej_count}</span></div>
        <div class="metric-card"><span class="metric-label">Avg Confidence</span><span class="metric-value">{avg_conf}%</span></div>
    </section>

    <div class="toolbar">
        <input type="text" id="filter-search" class="search-input" placeholder="Search project records...">
        <span style="font-size: 12px; color: var(--slate-500);">Showing {total} total records</span>
    </div>

    <div class="spreadsheet-container">
        <table class="excel-table" id="records-table">
            <thead>
                <tr>
                    <th class="col-row-num">#</th>
                    <th>Part Number</th>
                    <th>Description</th>
                    <th class="text-right">Qty</th>
                    <th class="text-center">Unit</th>
                    <th>Vendor</th>
                    <th>Category</th>
                    <th class="text-center">Location</th>
                    <th>Document</th>
                    <th class="text-right">Confidence</th>
                    <th class="text-center">Status</th>
                    <th>Review Notes</th>
                </tr>
            </thead>
            <tbody id="table-body">
                {records_rows_rendered}
            </tbody>
        </table>
    </div>

    <script>
        const searchInput = document.getElementById('filter-search');
        const rows = document.getElementById('table-body').getElementsByTagName('tr');
        searchInput.addEventListener('input', () => {{
            const q = searchInput.value.toLowerCase().trim();
            for (let i = 0; i < rows.length; i++) {{
                rows[i].style.display = !q || rows[i].textContent.toLowerCase().includes(q) ? '' : 'none';
            }}
        }});
    </script>
</body>
</html>
"""
        return html_template
