from __future__ import annotations


CANONICAL_FIELDS = [
    "equipment_name",
    "part_number",
    "serial_number",
    "description",
    "model",
    "manufacturer",
    "vendor",
    "condition",
    "condition_notes",
    "quantity",
    "unit",
    "location",
    "rack",
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
            "serial_number",
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
For image attachments, inspect the visual source itself in addition
to the OCR text, including table structure, diagram labels, and
spatial relationships. Treat OCR text as supporting evidence, not
as a replacement for the image.

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

"Brand" -> manufacturer

"Supplier" -> vendor

"Vendor" -> manufacturer when the column identifies
the equipment maker or brand; otherwise map it to vendor.

"Vendor Name" -> vendor

"ITEM NAME" -> equipment_name

"Product Name" -> equipment_name

"Device" -> equipment_name

"PART NO" -> part_number

"Part No" -> part_number

"Item Code" -> part_number

"SKU" -> part_number

"Product Code" -> part_number

"Serial No" -> serial_number

"Serial Number" -> serial_number

"QTY" -> quantity

"Quantity" -> quantity

"Count" -> quantity

"Rack Name" -> rack_id

"Rack ID" -> rack_id

"Rack" -> rack_id

"Rack Position" -> u_position

"U Position" -> u_position

"RU" -> u_position

"Wattage" -> power_watts

"Power Rating" -> power_watts

"Cable Length" -> length

Use the actual values and surrounding context
when determining the meaning.

==================================================
TABLE EXTRACTION
==================================================

For every table:

- preserve every available row
- preserve every available column
- support headers that appear above or beside the data, and multi-row headers
- preserve values even when some cells are empty
- identify likely headers semantically
- preserve source information in raw_data
- do not drop unknown columns
- place unmapped information in extra_fields
- associate each value with the correct row and all applicable headers
- do not combine adjacent cells unless the source clearly presents them as one value

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

4. Copy each extracted value exactly as printed or stored in the source.
   Do not normalize, repair, complete, calculate, or infer a value.

5. Missing values must be JSON null. Never substitute a default such as
   quantity 1, unit "pcs", or a guessed manufacturer.

6. Preserve the original value in raw_data
   when useful.

7. Preserve unmapped source fields in
   extra_fields.

8. Preserve source context whenever available.

9. Confidence must be between 0 and 1.

10. Use a lower confidence when the mapping
   is ambiguous.

11. Use category="{category}".

12. record_type should describe the type of
    extracted record.

13. Do not merge two different physical
    components into one record unless the
    source clearly represents them as one item.

14. Do not discard duplicate rows unless the
    source explicitly indicates that they are
    duplicates.

15. Quantity must represent the source quantity,
    not an inferred quantity.

16. For diagrams, preserve relationship
    information in raw_data or extra_fields.

17. Only use values that appear in the supplied source content or
    images. Keep identifiers, serial numbers, quantities, and labels
    verbatim; any interpretation that is not explicitly printed must
    be null.

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
      "serial_number": null,
      "description": null,
      "model": null,
      "manufacturer": null,
      "vendor": null,
      "condition": null,
      "condition_notes": null,
      "quantity": null,
      "unit": null,
      "location": null,
      "rack": null,
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