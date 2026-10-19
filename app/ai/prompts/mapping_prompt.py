from typing import Any, Dict, List
import json

SEMANTIC_MAPPING_PROMPT = """
You are an expert Data Center document semantic mapping system.

Your task is to identify the meaning of source columns and map them
to canonical field names.

IMPORTANT RULES:

1. NEVER depend on column position.
2. NEVER require an exact column name.
3. Understand abbreviations, synonyms and business terminology.
4. Use column name, surrounding headers and sample values together.
5. If a column does not clearly match a canonical field, return null.
6. Never invent mappings.
7. Preserve the original source column name.
8. Return only valid JSON.

Common examples:

Part Number:
- Part No
- Part Number
- P/N
- P.N.
- PN
- Item Code
- Item Number
- Product Code
- Material Code
- SKU

Item Name:
- Item
- Item Name
- Product
- Product Name
- Equipment
- Equipment Name
- Device
- Device Name
- Description

Manufacturer:
- MFR
- MFG
- Manufacturer
- Maker
- OEM
- Brand
- Vendor

Quantity:
- Qty
- QTY
- Quantity
- Count
- No.
- Number Required

Rack:
- Rack
- Rack No
- Rack Number
- Rack ID
- Cabinet
- Cabinet No
- Cabinet ID

U Position:
- U
- U Position
- Rack Unit
- RU
- Rack Position
- Unit Position

Serial Number:
- Serial
- Serial No
- Serial Number
- S/N
- SN

Return:

{
    "mappings": [
        {
            "source_column": "MFR",
            "canonical_field": "manufacturer",
            "confidence": 0.98
        }
    ]
}

Allowed canonical fields:

part_number
item_name
model
manufacturer
quantity
rack_number
u_position
serial_number
device_type
description
location
vendor
source_equipment
source_port
source_rack
destination_equipment
destination_port
destination_rack
cable_type
cable_part_number
length
power_rating
voltage
po_number
po_date

Source columns:

{columns}

Sample rows:

{sample_rows}
"""

MAPPING_SYSTEM_PROMPT = (
    "You are an expert Data Center document semantic mapping system. "
    "Your task is to identify the meaning of source columns and map them to canonical field names. "
    "Return only valid JSON."
)


def build_mapping_prompt(
    category: str,
    source_columns: list[str],
    sample_rows: list[dict[str, Any]],
) -> str:
    import json
    columns_str = "\n".join(f"- {c}" for c in source_columns)
    sample_str = json.dumps(sample_rows[:5], indent=2) if sample_rows else "[]"
    return (
        SEMANTIC_MAPPING_PROMPT.replace("{columns}", columns_str)
        .replace("{sample_rows}", sample_str)
    )