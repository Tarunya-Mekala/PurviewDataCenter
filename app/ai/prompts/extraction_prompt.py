from __future__ import annotations


CANONICAL_FIELDS = {
    "equipment_name": (
        "Name of the equipment, device, product or physical item."
    ),
    "part_number": (
        "Part number, SKU, item code, product code or equivalent identifier."
    ),
    "description": (
        "Detailed description of the item."
    ),
    "model": (
        "Model number or model name."
    ),
    "manufacturer": (
        "Manufacturer or maker of the equipment."
    ),
    "vendor": (
        "Supplier, vendor or seller."
    ),
    "quantity": (
        "Number of units/items."
    ),
    "unit": (
        "Unit of measurement such as pcs, units, meters, kW."
    ),
    "rack_id": (
        "Rack identifier such as R01, Rack-12."
    ),
    "u_position": (
        "Rack U-position or mounting position."
    ),
    "source_device": (
        "Origin/source device for a connection."
    ),
    "source_port": (
        "Origin/source port."
    ),
    "target_device": (
        "Destination/target device."
    ),
    "target_port": (
        "Destination/target port."
    ),
    "cable_type": (
        "Cable type."
    ),
    "length": (
        "Cable or physical length."
    ),
    "power_watts": (
        "Power requirement or rating in watts."
    ),
    "dimensions": (
        "Physical dimensions."
    ),
}


def build_extraction_prompt(
    document_content: str,
    document_category: str,
    source_file_name: str,
) -> str:

    field_description = "\n".join(
        f"- {field}: {description}"
        for field, description in CANONICAL_FIELDS.items()
    )

    return f"""
You are an enterprise data-center document extraction system.

Your task is to extract structured engineering/inventory information
from a heterogeneous source document.

DOCUMENT CATEGORY:
{document_category}

SOURCE FILE:
{source_file_name}

The source document may contain completely different terminology,
column names, layouts, ordering, spelling or formatting.

You MUST perform semantic mapping based on the meaning of the
headers AND the values.

Do NOT rely on:
- exact column names
- fixed column positions
- fixed sheet names
- fixed row numbers
- a specific vendor format

CANONICAL FIELDS:

{field_description}

SEMANTIC MAPPING EXAMPLES:

"Equipment", "Device", "Product", "Item", "Asset"
    -> equipment_name

"SKU", "Part No", "Part Number", "Item Code", "Product Code"
    -> part_number

"Qty", "Quantity", "Count", "Units", "No. of Items"
    -> quantity

"Vendor", "Supplier", "Seller"
    -> vendor

"Mfr", "Manufacturer", "Maker", "Brand"
    -> manufacturer

"Rack", "Rack ID", "Rack Number"
    -> rack_id

"U", "U Position", "Rack Position"
    -> u_position

IMPORTANT RULES:

1. Extract every valid record.

2. Semantically map source fields to canonical fields.

3. The same source field may have different names in different
   documents.

4. Column position has NO semantic meaning.

5. Do not assume the first column is the equipment name.

6. Do not assume the second column is the part number.

7. Preserve values exactly when possible.

8. Do not invent missing information.

9. If a field is not present, return null.

10. If the source contains extra useful fields that do not fit the
    canonical fields, preserve them in extra_fields.

11. Do not merge different physical items unless the source clearly
    indicates they are the same item.

12. Keep the original source information in raw_data.

13. Provide a confidence score between 0 and 1.

14. High confidence means the semantic mapping is clear.

15. Low confidence means the mapping is ambiguous.

16. Return valid JSON only.

SOURCE DOCUMENT:

{document_content}
"""