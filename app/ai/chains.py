import json
from typing import Any, Dict, List, Optional

from app.ai.llm import ollama_client
from app.ai.prompts.extraction_prompt import (
    BOM_EXTRACTION_PROMPT,
    GENERIC_EXTRACTION_PROMPT,
    P2P_EXTRACTION_PROMPT,
    RACK_LAYOUT_EXTRACTION_PROMPT,
)
from app.utils.normalization import extract_vendor_from_text, parse_quantity


def get_prompt_template(document_type: str) -> str:
    """Select prompt template matching document domain."""
    dt = (document_type or "bom").lower()
    if dt == "bom":
        return BOM_EXTRACTION_PROMPT
    if dt in ["p2p", "cable"]:
        return P2P_EXTRACTION_PROMPT
    if dt == "rack_layout":
        return RACK_LAYOUT_EXTRACTION_PROMPT
    return GENERIC_EXTRACTION_PROMPT


def clean_extracted_item(raw_item: Dict[str, Any], doc_type: str) -> Optional[Dict[str, Any]]:
    """Validate and clean a single record produced by the LLM."""
    if not isinstance(raw_item, dict):
        return None

    part_number = raw_item.get("part_number")
    description = raw_item.get("description")

    # Clean None/"null" strings
    if part_number in [None, "null", "None", ""]:
        part_number = None
    else:
        part_number = str(part_number).strip()

    if description in [None, "null", "None", ""]:
        description = None
    else:
        description = str(description).strip()

    # Must have at least a part number or description or connection
    source_dev = raw_item.get("source_device")
    target_dev = raw_item.get("target_device")
    if not part_number and not description and not (source_dev and target_dev):
        return None

    # Inferred vendor if missing
    vendor = raw_item.get("vendor")
    if vendor in [None, "null", "None", ""]:
        vendor = extract_vendor_from_text(f"{part_number or ''} {description or ''}")
    else:
        vendor = str(vendor).strip()

    # Quantity
    quantity = parse_quantity(raw_item.get("quantity"))

    # Confidence score
    conf = raw_item.get("confidence_score")
    try:
        conf_score = round(float(conf), 2) if conf is not None else 0.85
    except (ValueError, TypeError):
        conf_score = 0.85
    conf_score = max(0.1, min(1.0, conf_score))

    # Map record type
    record_type = "bom_item"
    if doc_type in ["p2p", "cable"] or (source_dev and target_dev):
        record_type = "cable_item"
    elif doc_type == "rack_layout" or raw_item.get("location"):
        record_type = "rack_item"
    elif doc_type == "power":
        record_type = "power_item"

    return {
        "record_type": record_type,
        "part_number": part_number,
        "description": description,
        "quantity": quantity,
        "unit": str(raw_item.get("unit") or "pcs").strip(),
        "vendor": vendor,
        "category": str(raw_item.get("category")).strip() if raw_item.get("category") else None,
        "location": str(raw_item.get("location")).strip() if raw_item.get("location") else None,
        "source_device": str(source_dev).strip() if source_dev else None,
        "source_port": str(raw_item.get("source_port")).strip() if raw_item.get("source_port") else None,
        "target_device": str(target_dev).strip() if target_dev else None,
        "target_port": str(raw_item.get("target_port")).strip() if raw_item.get("target_port") else None,
        "cable_type": str(raw_item.get("cable_type")).strip() if raw_item.get("cable_type") else None,
        "confidence_score": conf_score,
        "raw_data": raw_item,
    }


def chunk_text(text: str, max_chunk_chars: int = 8000) -> List[str]:
    """Break long documents into chunks to fit comfortably within LLM context window."""
    if len(text) <= max_chunk_chars:
        return [text]

    lines = text.splitlines(keepends=True)
    chunks = []
    current_chunk: List[str] = []
    current_len = 0

    for line in lines:
        if current_len + len(line) > max_chunk_chars and current_chunk:
            chunks.append("".join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(line)
        current_len += len(line)

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks


def extract_records_with_llm(
    text_content: str,
    document_type: str = "bom",
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Execute AI extraction chain on text content using Ollama (e.g. Qwen 2.5 27B).
    Returns list of parsed records with confidence scores.
    """
    if not text_content or not text_content.strip():
        return []

    template = get_prompt_template(document_type)
    chunks = chunk_text(text_content)
    all_records: List[Dict[str, Any]] = []

    for chunk in chunks:
        prompt = template.replace("{content}", chunk)
        response_dict = ollama_client.generate_json(prompt=prompt, model=model)
        raw_records = response_dict.get("records", [])

        if isinstance(raw_records, list):
            for raw_rec in raw_records:
                cleaned = clean_extracted_item(raw_rec, document_type)
                if cleaned:
                    all_records.append(cleaned)

    return all_records
