from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber


def parse_pdf_file(
    file_path: Path,
) -> dict[str, Any]:
    """
    Parse the complete PDF.

    Preserves:

    - every page
    - page text
    - tables
    - table rows
    - table columns
    - words and coordinates
    - detected lines / rectangles
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {file_path}"
        )

    pages: list[dict[str, Any]] = []

    with pdfplumber.open(
        file_path
    ) as pdf:

        for page_number, page in enumerate(
            pdf.pages,
            start=1,
        ):

            page_text = (
                page.extract_text()
                or ""
            )

            words = page.extract_words(
                keep_blank_chars=False
            )

            tables = []

            try:
                extracted_tables = (
                    page.extract_tables()
                )

                for table_index, table in enumerate(
                    extracted_tables or [],
                    start=1,
                ):

                    rows = []

                    for row_index, row in enumerate(
                        table,
                        start=1,
                    ):

                        rows.append(
                            {
                                "row_number": row_index,
                                "cells": [
                                    {
                                        "column_position": column_index,
                                        "value": (
                                            str(cell).strip()
                                            if cell is not None
                                            else ""
                                        ),
                                    }
                                    for column_index, cell
                                    in enumerate(
                                        row,
                                        start=1,
                                    )
                                ],
                            }
                        )

                    tables.append(
                        {
                            "table_number": table_index,
                            "rows": rows,
                        }
                    )

            except Exception:
                tables = []

            lines = []

            for line in page.lines:

                lines.append(
                    {
                        "type": "line",
                        "x0": line.get("x0"),
                        "y0": line.get("y0"),
                        "x1": line.get("x1"),
                        "y1": line.get("y1"),
                    }
                )

            rectangles = []

            for rect in page.rects:

                rectangles.append(
                    {
                        "type": "rectangle",
                        "x0": rect.get("x0"),
                        "y0": rect.get("y0"),
                        "x1": rect.get("x1"),
                        "y1": rect.get("y1"),
                    }
                )

            pages.append(
                {
                    "page_number": page_number,

                    "width": page.width,

                    "height": page.height,

                    "text": page_text,

                    "words": words,

                    "tables": tables,

                    "lines": lines,

                    "rectangles": rectangles,
                }
            )

    return {
        "file_name": file_path.name,
        "file_type": file_path.suffix.lower(),
        "page_count": len(pages),
        "pages": pages,
    }


def pdf_to_llm_text(
    parsed_pdf: dict[str, Any],
) -> str:
    """
    Convert complete PDF structure into LLM-readable text.
    """

    output: list[str] = []

    output.append(
        "===== PDF DOCUMENT ====="
    )

    output.append(
        f"FILE: "
        f"{parsed_pdf.get('file_name', '')}"
    )

    output.append(
        f"PAGES: "
        f"{parsed_pdf.get('page_count', 0)}"
    )

    for page in parsed_pdf.get(
        "pages",
        [],
    ):

        page_number = page[
            "page_number"
        ]

        output.append(
            f"\n===== PAGE "
            f"{page_number} ====="
        )

        output.append(
            "\n--- PAGE TEXT ---"
        )

        output.append(
            page.get(
                "text",
                "",
            )
        )

        output.append(
            "\n--- TABLES ---"
        )

        for table in page.get(
            "tables",
            [],
        ):

            output.append(
                f"\nTABLE "
                f"{table['table_number']}:"
            )

            for row in table.get(
                "rows",
                [],
            ):

                output.append(
                    f"ROW "
                    f"{row['row_number']}: "
                    + " | ".join(
                        str(
                            cell.get(
                                "value",
                                "",
                            )
                        )
                        for cell in row.get(
                            "cells",
                            [],
                        )
                    )
                )

        output.append(
            "\n--- VISUAL LINES ---"
        )

        for line in page.get(
            "lines",
            [],
        ):

            output.append(
                str(line)
            )

        output.append(
            "\n--- VISUAL RECTANGLES ---"
        )

        for rectangle in page.get(
            "rectangles",
            [],
        ):

            output.append(
                str(rectangle)
            )

    return "\n".join(output)


def extract_text_from_pdf(
    file_path: Path,
) -> str:
    """
    Backward-compatible helper.
    """

    parsed = parse_pdf_file(
        file_path
    )

    return pdf_to_llm_text(
        parsed
    )