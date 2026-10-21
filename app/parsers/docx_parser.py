from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document


DOCX_EXTENSIONS = {
    ".docx",
}


def parse_docx_file(
    file_path: Path,
) -> dict[str, Any]:
    """
    Parse the complete DOCX document.

    Preserves:

    - paragraphs
    - paragraph order
    - tables
    - all table rows
    - all table columns
    - cell text
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"DOCX not found: {file_path}"
        )

    document = Document(
        str(file_path)
    )

    paragraphs = []

    for paragraph_index, paragraph in enumerate(
        document.paragraphs,
        start=1,
    ):

        text = paragraph.text.strip()

        if text:

            paragraphs.append(
                {
                    "paragraph_number": paragraph_index,
                    "text": text,
                }
            )

    tables = []

    for table_index, table in enumerate(
        document.tables,
        start=1,
    ):

        rows = []

        for row_index, row in enumerate(
            table.rows,
            start=1,
        ):

            cells = []

            for column_index, cell in enumerate(
                row.cells,
                start=1,
            ):

                cells.append(
                    {
                        "column_position": column_index,
                        "text": cell.text.strip(),
                    }
                )

            rows.append(
                {
                    "row_number": row_index,
                    "cells": cells,
                }
            )

        tables.append(
            {
                "table_number": table_index,
                "rows": rows,
            }
        )

    return {
        "file_name": file_path.name,
        "file_type": file_path.suffix.lower(),
        "paragraphs": paragraphs,
        "tables": tables,
        "paragraph_count": len(
            paragraphs
        ),
        "table_count": len(
            tables
        ),
    }


def docx_to_llm_text(
    parsed_docx: dict[str, Any],
) -> str:
    """
    Convert DOCX structure to explicit LLM-readable text.
    """

    output: list[str] = []

    output.append(
        "===== DOCX DOCUMENT ====="
    )

    output.append(
        f"FILE: "
        f"{parsed_docx.get('file_name', '')}"
    )

    output.append(
        "\n===== PARAGRAPHS ====="
    )

    for paragraph in parsed_docx.get(
        "paragraphs",
        [],
    ):

        output.append(
            f"PARAGRAPH "
            f"{paragraph['paragraph_number']}: "
            f"{paragraph['text']}"
        )

    output.append(
        "\n===== TABLES ====="
    )

    for table in parsed_docx.get(
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

            values = [
                str(
                    cell.get(
                        "text",
                        "",
                    )
                )
                for cell in row.get(
                    "cells",
                    [],
                )
            ]

            output.append(
                f"ROW "
                f"{row['row_number']}: "
                + " | ".join(values)
            )

    return "\n".join(output)