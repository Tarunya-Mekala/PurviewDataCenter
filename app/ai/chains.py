from __future__ import annotations

from typing import Any, Optional

from app.ai.llm import llm_client
from app.ai.prompts.extraction_prompt import build_extraction_prompt
from app.schemas.inventory import (
    CanonicalInventoryDocument,
    CanonicalInventoryRecord,
)


LLM_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "record_type": {"type": "string"},
                    "equipment_name": {"type": "string", "nullable": True},
                    "part_number": {"type": "string", "nullable": True},
                    "description": {"type": "string", "nullable": True},
                    "model": {"type": "string", "nullable": True},
                    "manufacturer": {"type": "string", "nullable": True},
                    "vendor": {"type": "string", "nullable": True},
                    "quantity": {"type": "number", "nullable": True},
                    "unit": {"type": "string", "nullable": True},
                    "rack_id": {"type": "string", "nullable": True},
                    "u_position": {"type": "string", "nullable": True},
                    "source_device": {"type": "string", "nullable": True},
                    "source_port": {"type": "string", "nullable": True},
                    "target_device": {"type": "string", "nullable": True},
                    "target_port": {"type": "string", "nullable": True},
                    "cable_type": {"type": "string", "nullable": True},
                    "length": {"type": "string", "nullable": True},
                    "power_watts": {"type": "number", "nullable": True},
                    "dimensions": {"type": "string", "nullable": True},
                    "confidence_score": {"type": "number"},
                    "raw_data": {"type": "object"},
                    "extra_fields": {"type": "object"},
                },
                "required": [
                    "category",
                    "record_type",
                ],
            },
        }
    },
    "required": ["records"],
}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_records(
    result: dict[str, Any],
    category: str,
) -> CanonicalInventoryDocument:

    records: list[CanonicalInventoryRecord] = []

    for item in result.get("records", []):

        item = dict(item)

        item["category"] = (
            item.get("category")
            or category
        )

        item["record_type"] = (
            item.get("record_type")
            or "inventory_item"
        )

        item["quantity"] = _safe_float(
            item.get("quantity")
        )

        item["power_watts"] = _safe_float(
            item.get("power_watts")
        )

        confidence = _safe_float(
            item.get("confidence_score")
        )

        if confidence is None:
            confidence = 0.0

        item["confidence_score"] = max(
            0.0,
            min(1.0, confidence)
        )

        record = CanonicalInventoryRecord.model_validate(
            item
        )

        records.append(record)

    return CanonicalInventoryDocument(
        document_category=category,
        records=records,
    )


def extract_records_with_llm(
    document_content: Optional[str] = None,
    document_category: Optional[str] = None,
    source_file_name: str = "unknown",
    *,
    text_content: Optional[str] = None,
    document_type: Optional[str] = None,
    model: Optional[str] = None,
) -> CanonicalInventoryDocument:
    content = document_content if document_content is not None else (text_content or "")
    category = document_category if document_category is not None else (document_type or "bom")

    prompt = build_extraction_prompt(
        document_content=content,
        document_category=category,
        source_file_name=source_file_name,
    )

    result = llm_client.generate_json(
        prompt=prompt,
        response_schema=LLM_RESPONSE_SCHEMA,
    )

    return _validate_records(
        result=result,
        category=category,
    )