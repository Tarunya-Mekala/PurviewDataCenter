from __future__ import annotations


CANONICAL_FIELDS = [
    "equipment_name",
    "part_number",
    "description",
    "model",
    "manufacturer",
    "vendor",
    "quantity",
    "unit",
    "rack_id",
    "u_position",
    "source_device",
    "source_port",
    "target_device",
    "target_port",
    "cable_type",
    "length",
    "power_watts",
    "dimensions",
]


CATEGORY_EXTRACTION_GUIDANCE = {

    "bom": {
        "purpose": (
            "Equipment and material baseline/inventory."
        ),
        "fields": [
            "equipment_name",
            "part_number",
            "description",
            "model",
            "manufacturer",
            "vendor",
            "quantity",
            "unit",
        ],
    },

    "p2p": {
        "purpose": (
            "Point-to-point connectivity between "
            "devices and ports."
        ),
        "fields": [
            "source_device",
            "source_port",
            "target_device",
            "target_port",
            "cable_type",
            "length",
            "part_number",
            "quantity",
        ],
    },

    "rack": {
        "purpose": (
            "Physical rack and equipment placement."
        ),
        "fields": [
            "rack_id",
            "u_position",
            "equipment_name",
            "part_number",
            "model",
            "manufacturer",
            "quantity",
            "dimensions",
        ],
    },

    "rack_layout": {
        "purpose": (
            "Physical rack layout and equipment "
            "placement."
        ),
        "fields": [
            "rack_id",
            "u_position",
            "equipment_name",
            "part_number",
            "model",
            "manufacturer",
            "quantity",
            "dimensions",
        ],
    },

    "power": {
        "purpose": (
            "Power equipment, consumption and "
            "distribution information."
        ),
        "fields": [
            "equipment_name",
            "part_number",
            "model",
            "manufacturer",
            "vendor",
            "quantity",
            "power_watts",
            "description",
            "dimensions",
        ],
    },

    "cable": {
        "purpose": (
            "Cable inventory and physical/logical "
            "connectivity."
        ),
        "fields": [
            "source_device",
            "source_port",
            "target_device",
            "target_port",
            "cable_type",
            "length",
            "part_number",
            "manufacturer",
            "quantity",
        ],
    },
}


def build_extraction_prompt(
    document_content: str,
    document_category: str,
    source_file_name: str,
    source_file_type: str = "",
) -> str:

    category = (
        document_category
        .strip()
        .lower()
    )

    guidance = (
        CATEGORY_EXTRACTION_GUIDANCE.get(
            category,
            {
                "purpose": (
                    "General data-center "
                    "inventory information."
                ),
                "fields": CANONICAL_FIELDS,
            },
        )
    )

    prioritized_fields = "\n".join(
        f"- {field}"
        for field in guidance[
            "fields"
        ]
    )

    canonical_fields = "\n".join(
        f"- {field}"
        for field in CANONICAL_FIELDS
    )

    return f"""
You are a data-center document understanding
and structured extraction system.

BUSINESS CATEGORY:
{category}

CATEGORY PURPOSE:
{guidance["purpose"]}

SOURCE FILE:
{source_file_name}

SOURCE FILE TYPE:
{source_file_type}

==================================================
IMPORTANT EXTRACTION REQUIREMENT
==================================================

The source document may contain ANY combination of:

1. Excel-style tables
2. PDF tables
3. DOCX tables
4. Images of tables
5. Rows
6. Columns
7. Free-form text
8. Architecture diagrams
9. Rack diagrams
10. Network diagrams
11. Power diagrams
12. Cable diagrams
13. Labels connected by lines/arrows
14. Multiple tables on the same page
15. Multiple sheets in the same workbook

You MUST inspect all supplied content.

Do NOT assume that the first row is always
the header.

Do NOT assume that the first column is always
the identifier.

Do NOT assume fixed column names.

Do NOT assume fixed column positions.

Do NOT assume a fixed table structure.

Do NOT ignore data simply because its column
name is unfamiliar.

==================================================
SEMANTIC COLUMN MAPPING
==================================================

Map source fields according to their meaning.

Examples:

"MFR" -> manufacturer

"Manufacturer Name" -> manufacturer

"Maker" -> manufacturer

"ITEM NAME" -> equipment_name

"Product Name" -> equipment_name

"Device" -> equipment_name

"PART NO" -> part_number

"Item Code" -> part_number

"SKU" -> part_number

"QTY" -> quantity

"Quantity" -> quantity

"Count" -> quantity

Use the actual values and surrounding context
when determining the meaning.

==================================================
TABLE EXTRACTION
==================================================

For every table:

- preserve every available row
- preserve every available column
- preserve values even when some cells are empty
- identify likely headers semantically
- preserve source information in raw_data
- do not drop unknown columns
- place unmapped information in extra_fields

If a document contains several tables,
process all of them.

==================================================
ARCHITECTURE / DIAGRAM EXTRACTION
==================================================

If the document contains an architecture,
rack, power, network or cable diagram:

Identify:

- components
- devices
- racks
- ports
- labels
- power units
- cable labels
- connections
- source and target devices
- source and target ports
- relationships

Do not treat diagram text as unrelated text
when visual/structural information indicates
that the elements are connected.

When an exact relationship cannot be determined,
do not invent it.

Store the available information in:

- raw_data
- extra_fields

==================================================
CATEGORY-SPECIFIC FIELDS
==================================================

Prioritize these fields for this category:

{prioritized_fields}

==================================================
CANONICAL FIELDS
==================================================

{canonical_fields}

==================================================
EXTRACTION RULES
==================================================

1. Extract all available relevant records.

2. Do not invent values.

3. If a value cannot be determined,
   return null.

4. Preserve the original value in raw_data
   when useful.

5. Preserve unmapped source fields in
   extra_fields.

6. Preserve source context whenever available.

7. Confidence must be between 0 and 1.

8. Use a lower confidence when the mapping
   is ambiguous.

9. Use category="{category}".

10. record_type should describe the type of
    extracted record.

11. Do not merge two different physical
    components into one record unless the
    source clearly represents them as one item.

12. Do not discard duplicate rows unless the
    source explicitly indicates that they are
    duplicates.

13. Quantity must represent the source quantity,
    not an inferred quantity.

14. For diagrams, preserve relationship
    information in raw_data or extra_fields.

==================================================
EXPECTED JSON
==================================================

Return ONLY JSON matching this structure:

{{
  "records": [
    {{
      "category": "{category}",
      "record_type": "inventory_item",
      "equipment_name": null,
      "part_number": null,
      "description": null,
      "model": null,
      "manufacturer": null,
      "vendor": null,
      "quantity": null,
      "unit": null,
      "rack_id": null,
      "u_position": null,
      "source_device": null,
      "source_port": null,
      "target_device": null,
      "target_port": null,
      "cable_type": null,
      "length": null,
      "power_watts": null,
      "dimensions": null,
      "confidence_score": 0.0,
      "raw_data": {{}},
      "extra_fields": {{}}
    }}
  ]
}}

==================================================
SOURCE DOCUMENT CONTENT
==================================================

{document_content}
"""