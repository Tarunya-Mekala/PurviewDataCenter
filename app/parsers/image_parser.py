from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytesseract

from PIL import Image
from pytesseract import Output


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _group_words_into_rows(
    words: list[dict[str, Any]],
    y_tolerance: int = 12,
) -> list[list[dict[str, Any]]]:
    """
    Group OCR words using their Y coordinates.

    This allows an image table such as:

        NAME   PART   QTY

        Server DL380  4

    to be reconstructed as rows.
    """

    rows: list[list[dict[str, Any]]] = []

    sorted_words = sorted(
        words,
        key=lambda item: (
            item["top"],
            item["left"],
        ),
    )

    for word in sorted_words:

        placed = False

        for row in rows:

            average_top = sum(
                item["top"]
                for item in row
            ) / len(row)

            if abs(
                word["top"]
                - average_top
            ) <= y_tolerance:

                row.append(word)
                placed = True
                break

        if not placed:
            rows.append([word])

    for row in rows:
        row.sort(
            key=lambda item: item["left"]
        )

    rows.sort(
        key=lambda row: min(
            item["top"]
            for item in row
        )
    )

    return rows


def _detect_lines(
    image: np.ndarray,
) -> list[dict[str, Any]]:
    """
    Detect horizontal and vertical lines.

    These can help identify:
        - tables
        - boxes
        - architecture diagrams
        - connections
    """

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )

    threshold = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11,
        2,
    )

    height, width = gray.shape

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (
            max(10, width // 30),
            1,
        ),
    )

    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (
            1,
            max(10, height // 30),
        ),
    )

    horizontal = cv2.morphologyEx(
        threshold,
        cv2.MORPH_OPEN,
        horizontal_kernel,
    )

    vertical = cv2.morphologyEx(
        threshold,
        cv2.MORPH_OPEN,
        vertical_kernel,
    )

    lines: list[dict[str, Any]] = []

    contours, _ = cv2.findContours(
        horizontal,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        if w < 20:
            continue

        lines.append(
            {
                "orientation": "horizontal",
                "x": x,
                "y": y,
                "width": w,
                "height": h,
            }
        )

    contours, _ = cv2.findContours(
        vertical,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        if h < 20:
            continue

        lines.append(
            {
                "orientation": "vertical",
                "x": x,
                "y": y,
                "width": w,
                "height": h,
            }
        )

    return lines


def parse_image_file(
    file_path: Path,
) -> dict[str, Any]:
    """
    Extract structured information from an image.

    Unlike simple image_to_string(), this preserves
    OCR coordinates and visual line information.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Image not found: {file_path}"
        )

    if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported image extension: "
            f"{file_path.suffix}"
        )

    image = cv2.imread(
        str(file_path)
    )

    if image is None:
        raise ValueError(
            f"Unable to read image: "
            f"{file_path}"
        )

    height, width = image.shape[:2]

    pil_image = Image.open(
        file_path
    )

    try:
        ocr_data = pytesseract.image_to_data(
            pil_image,
            output_type=Output.DICT,
            config="--psm 6",
        )
    except Exception:
        ocr_data = {"text": []}

    words: list[dict[str, Any]] = []

    total_items = len(
        ocr_data["text"]
    )

    for index in range(total_items):

        text = _safe_text(
            ocr_data["text"][index]
        )

        if not text:
            continue

        try:
            confidence = float(
                ocr_data["conf"][index]
            )
        except (
            TypeError,
            ValueError,
        ):
            confidence = 0.0

        word = {
            "text": text,
            "confidence": confidence,
            "left": int(
                ocr_data["left"][index]
            ),
            "top": int(
                ocr_data["top"][index]
            ),
            "width": int(
                ocr_data["width"][index]
            ),
            "height": int(
                ocr_data["height"][index]
            ),
            "block_num": int(
                ocr_data["block_num"][index]
            ),
            "par_num": int(
                ocr_data["par_num"][index]
            ),
            "line_num": int(
                ocr_data["line_num"][index]
            ),
        }

        words.append(word)

    rows = _group_words_into_rows(
        words
    )

    structured_rows = []

    for row_index, row in enumerate(
        rows,
        start=1,
    ):

        structured_rows.append(
            {
                "row_number": row_index,
                "cells": [
                    {
                        "column_position": cell_index,
                        "text": word["text"],
                        "left": word["left"],
                        "top": word["top"],
                        "width": word["width"],
                        "height": word["height"],
                        "confidence": word[
                            "confidence"
                        ],
                    }
                    for cell_index, word
                    in enumerate(
                        row,
                        start=1,
                    )
                ],
            }
        )

    lines = _detect_lines(
        image
    )

    try:
        full_text = pytesseract.image_to_string(
            pil_image,
            config="--psm 6",
        ).strip()
    except Exception:
        full_text = ""

    return {
        "file_name": file_path.name,
        "file_type": file_path.suffix.lower(),

        "image": {
            "width": width,
            "height": height,
        },

        "full_text": full_text,

        "ocr_words": words,

        "rows": structured_rows,

        "detected_lines": lines,

        "document_understanding": {
            "has_text": bool(words),
            "has_rows": bool(
                structured_rows
            ),
            "has_lines": bool(lines),
            "possible_table": (
                len(lines) >= 2
                and len(structured_rows) >= 2
            ),
            "possible_architecture": (
                len(words) >= 2
                and len(lines) >= 1
            ),
        },
    }


def image_to_llm_text(
    parsed_image: dict[str, Any],
) -> str:
    """
    Convert image structure into explicit LLM-readable text.
    """

    output: list[str] = []

    output.append(
        "===== IMAGE DOCUMENT ====="
    )

    output.append(
        f"FILE: "
        f"{parsed_image.get('file_name', '')}"
    )

    image_info = parsed_image.get(
        "image",
        {},
    )

    output.append(
        f"IMAGE_SIZE: "
        f"{image_info.get('width')} x "
        f"{image_info.get('height')}"
    )

    output.append(
        "\n===== OCR TEXT ====="
    )

    output.append(
        parsed_image.get(
            "full_text",
            "",
        )
    )

    output.append(
        "\n===== STRUCTURED OCR ROWS ====="
    )

    for row in parsed_image.get(
        "rows",
        [],
    ):

        output.append(
            f"\nROW "
            f"{row['row_number']}:"
        )

        for cell in row.get(
            "cells",
            [],
        ):

            output.append(
                f"  COLUMN "
                f"{cell['column_position']}: "
                f"{cell['text']} "
                f"(x={cell['left']}, "
                f"y={cell['top']}, "
                f"confidence="
                f"{cell['confidence']})"
            )

    output.append(
        "\n===== DETECTED VISUAL LINES ====="
    )

    for line in parsed_image.get(
        "detected_lines",
        [],
    ):

        output.append(
            f"{line['orientation']} line: "
            f"x={line['x']}, "
            f"y={line['y']}, "
            f"width={line['width']}, "
            f"height={line['height']}"
        )

    output.append(
        "\n===== DOCUMENT TYPE HINTS ====="
    )

    output.append(
        str(
            parsed_image.get(
                "document_understanding",
                {},
            )
        )
    )

    return "\n".join(output)