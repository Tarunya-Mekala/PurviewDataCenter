from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import fitz  # PyMuPDF


def extract_text_from_pdf(file_path: str | Path, max_pages: Optional[int] = None) -> str:
    """
    Extract text content from a PDF file page by page.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    text_parts: List[str] = []
    doc = fitz.open(str(file_path))
    try:
        total_pages = len(doc)
        pages_to_process = min(total_pages, max_pages) if max_pages else total_pages
        for page_idx in range(pages_to_process):
            page = doc[page_idx]
            page_text = page.get_text("text").strip()
            if page_text:
                text_parts.append(f"--- Page {page_idx + 1} ---\n{page_text}")
    finally:
        doc.close()

    return "\n\n".join(text_parts)


def parse_pdf_tables(file_path: str | Path) -> List[Dict[str, Any]]:
    """
    Extract structured table data from PDF pages if tables are detected.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    tables_found: List[Dict[str, Any]] = []
    doc = fitz.open(str(file_path))
    try:
        for page_idx, page in enumerate(doc, start=1):
            tables = getattr(page, "find_tables", lambda: None)()
            if tables and tables.tables:
                for t_idx, table in enumerate(tables.tables):
                    table_data = table.extract()
                    if table_data and len(table_data) > 1:
                        headers = [str(c).strip() if c else "" for c in table_data[0]]
                        tables_found.append({
                            "page": page_idx,
                            "table_index": t_idx + 1,
                            "headers": headers,
                            "rows": table_data[1:],
                        })
    finally:
        doc.close()

    return tables_found