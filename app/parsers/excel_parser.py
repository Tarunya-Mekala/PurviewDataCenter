from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl


SUPPORTED_EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm"}


def _clean_value(value: Any) -> Any:
    """
    Convert Excel values into JSON-friendly values.
    """
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        return value if value else None

    # Handle datetime/date/time without importing them explicitly.
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    return value


def _make_unique_headers(headers: list[Any]) -> list[str]:
    """
    Preserve original header names while making duplicate/blank
    headers safe for dictionary usage.
    """
    result: list[str] = []
    used: dict[str, int] = {}

    for index, value in enumerate(headers, start=1):
        if value is None or str(value).strip() == "":
            base = f"column_{index}"
        else:
            base = str(value).strip()

        if base not in used:
            used[base] = 1
            result.append(base)
        else:
            used[base] += 1
            result.append(f"{base}__{used[base]}")

    return result


def _detect_header_row(
    rows: list[list[Any]],
    max_scan_rows: int = 30,
) -> int:
    """
    Detect a likely header row without assuming a fixed row number.
    """
    if not rows:
        return 0

    best_index = 0
    best_score = -1.0
    scan_limit = min(len(rows), max_scan_rows)

    for row_index in range(scan_limit):
        row = rows[row_index]
        non_empty = [
            value for value in row
            if value is not None and str(value).strip() != ""
        ]
        if not non_empty:
            continue

        unique_values = {
            str(value).strip().lower()
            for value in non_empty
        }
        text_values = sum(
            isinstance(value, str)
            for value in non_empty
        )
        non_empty_count = len(non_empty)

        score = (
            min(non_empty_count, 20) * 2.0
            + text_values * 1.5
            + len(unique_values) * 0.5
        )

        if non_empty_count == 1:
            score -= 5

        if score > best_score:
            best_score = score
            best_index = row_index

    return best_index


def parse_excel_file(file_path: str | Path) -> dict[str, Any]:
    """
    Parse an Excel workbook while preserving worksheets, original headers,
    column positions, and populated rows.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    if file_path.suffix.lower() not in SUPPORTED_EXCEL_EXTENSIONS:
        raise ValueError(f"Unsupported Excel extension: {file_path.suffix}")

    workbook = openpyxl.load_workbook(
        filename=file_path,
        read_only=True,
        data_only=True,
    )

    sheets: list[dict[str, Any]] = []

    try:
        for worksheet in workbook.worksheets:
            raw_rows: list[list[Any]] = []
            for row in worksheet.iter_rows(values_only=True):
                cleaned_row = [_clean_value(value) for value in row]
                if any(value is not None for value in cleaned_row):
                    raw_rows.append(cleaned_row)

            if not raw_rows:
                sheets.append(
                    {
                        "sheet_name": worksheet.title,
                        "header_row": None,
                        "headers": [],
                        "rows": [],
                    }
                )
                continue

            header_index = _detect_header_row(raw_rows)
            original_headers = raw_rows[header_index]
            headers = _make_unique_headers(original_headers)
            data_rows = raw_rows[header_index + 1:]

            structured_rows: list[dict[str, Any]] = []

            for relative_row_index, row in enumerate(
                data_rows,
                start=header_index + 2,
            ):
                padded_row = list(row)
                if len(padded_row) < len(headers):
                    padded_row.extend([None] * (len(headers) - len(padded_row)))

                if not any(value is not None for value in padded_row):
                    continue

                values: dict[str, Any] = {}
                for column_index, header in enumerate(headers):
                    values[header] = (
                        padded_row[column_index]
                        if column_index < len(padded_row)
                        else None
                    )

                structured_rows.append(
                    {
                        "source_row": relative_row_index,
                        "values": values,
                        "cells": [
                            {
                                "column_index": column_index + 1,
                                "column_name": headers[column_index],
                                "value": (
                                    padded_row[column_index]
                                    if column_index < len(padded_row)
                                    else None
                                ),
                            }
                            for column_index in range(len(headers))
                        ],
                    }
                )

            sheets.append(
                {
                    "sheet_name": worksheet.title,
                    "header_row": header_index + 1,
                    "headers": headers,
                    "rows": structured_rows,
                }
            )

    finally:
        workbook.close()

    total_rows = sum(len(sheet["rows"]) for sheet in sheets)

    return {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "file_type": file_path.suffix.lower(),
        "sheet_count": len(sheets),
        "total_rows": total_rows,
        "sheets": sheets,
    }


def excel_to_llm_text(parsed_workbook: dict[str, Any]) -> str:
    """
    Convert the structured Excel representation into a clear text representation for the LLM.
    """
    output: list[str] = []
    output.append(f"FILE: {parsed_workbook['file_name']}")
    output.append(f"TOTAL SHEETS: {parsed_workbook['sheet_count']}")

    for sheet in parsed_workbook["sheets"]:
        output.append("")
        output.append(f"===== SHEET: {sheet['sheet_name']} =====")

        if sheet["header_row"] is None:
            output.append("EMPTY SHEET")
            continue

        output.append(f"HEADER ROW: {sheet['header_row']}")
        output.append(
            "COLUMNS: "
            + " | ".join(
                f"{index + 1}:{header}"
                for index, header in enumerate(sheet["headers"])
            )
        )

        for row in sheet["rows"]:
            output.append(f"ROW {row['source_row']}:")
            for cell in row["cells"]:
                output.append(
                    f"  COLUMN {cell['column_index']} "
                    f"({cell['column_name']}) = "
                    f"{cell['value']}"
                )

    return "\n".join(output)

