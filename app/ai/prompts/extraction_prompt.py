BOM_EXTRACTION_PROMPT = """You are an expert AI Data Center Infrastructure and Hardware Engineer specializing in Bill of Materials (BOM) extraction.
Analyze the following document text and extract all hardware line items into structured JSON.

For each item, identify:
- part_number: The manufacturer part number, model, or order code (e.g. "N9K-C93180YC-FX", "DCS-7050TX3-48C8", "PowerEdge R750").
- description: Full product description and specifications.
- quantity: Numeric quantity (float/integer). Defaults to 1.0 if not specified.
- unit: Unit of measure (e.g. "pcs", "meters", "ft", "spool"). Defaults to "pcs".
- vendor: Manufacturer or vendor brand (e.g. "Cisco", "Arista", "Dell", "Schneider", "Panduit", "APC").
- category: Hardware category (e.g. "Switch", "Router", "Server", "Transceiver", "PDU", "Cable", "Optics", "Patch Panel").
- location: Physical location, cabinet, or rack elevation if specified.
- confidence_score: Confidence in extraction between 0.0 and 1.0.

Respond strictly with a JSON object matching this schema:
{
  "records": [
    {
      "part_number": "string or null",
      "description": "string or null",
      "quantity": 1.0,
      "unit": "pcs",
      "vendor": "string or null",
      "category": "string or null",
      "location": "string or null",
      "confidence_score": 0.95
    }
  ]
}

Document Content:
\"\"\"
{content}
\"\"\"
"""


P2P_EXTRACTION_PROMPT = """You are an expert Data Center Network and Cabling Engineer specializing in Point-to-Point (P2P) cable schedules and patch lists.
Analyze the following document text and extract all cable connection records into structured JSON.

For each connection, identify:
- source_device: Origin device or patch panel name (e.g. "Leaf-01", "Core-SW-A", "Rack-A01-PP1").
- source_port: Origin port identifier (e.g. "Eth1/1", "Port 24", "Slot 2/Port 1").
- target_device: Destination device or patch panel name (e.g. "Spine-01", "Server-01-NIC1").
- target_port: Destination port identifier.
- cable_type: Media type (e.g. "Cat6A", "OM4 MPO", "OS2 LC-LC", "100G QSFP28 DAC", "AOC").
- part_number: Cable assembly part number if mentioned.
- description: Details regarding length, color, or pathway.
- quantity: Number of cables/connections (defaults to 1.0).
- vendor: Cable manufacturer if mentioned.
- confidence_score: Confidence in extraction between 0.0 and 1.0.

Respond strictly with a JSON object matching this schema:
{
  "records": [
    {
      "source_device": "string or null",
      "source_port": "string or null",
      "target_device": "string or null",
      "target_port": "string or null",
      "cable_type": "string or null",
      "part_number": "string or null",
      "description": "string or null",
      "quantity": 1.0,
      "vendor": "string or null",
      "confidence_score": 0.90
    }
  ]
}

IMPORTANT EXTRACTION REQUIREMENT

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

SEMANTIC COLUMN MAPPING

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

TABLE EXTRACTION

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

ARCHITECTURE / DIAGRAM EXTRACTION

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

CATEGORY-SPECIFIC FIELDS

Prioritize these fields for this category:

{prioritized_fields}

CANONICAL FIELDS

{canonical_fields}

EXTRACTION RULES

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

EXPECTED JSON

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

SOURCE DOCUMENT CONTENT
Document Content:
\"\"\"
{content}
\"\"\"
"""


RACK_LAYOUT_EXTRACTION_PROMPT = """You are an expert Data Center Facilities Engineer specializing in Rack Elevation and Cabinet Space Planning.
Analyze the following document text and extract all rack hardware allocations into structured JSON.

For each mounted item, identify:
- location: Rack identifier and U-elevation range (e.g. "Rack-A01 (U41-U42)", "Cabinet 102 (RU 15)").
- part_number: Model or hardware code.
- description: Equipment installed in the rack unit.
- vendor: Manufacturer.
- category: Equipment type (e.g. "TOR Switch", "Compute Node", "Storage Array", "PDU", "Cable Management").
- quantity: Count of units installed.
- confidence_score: Confidence in extraction between 0.0 and 1.0.

Respond strictly with a JSON object matching this schema:
{
  "records": [
    {
      "location": "string or null",
      "part_number": "string or null",
      "description": "string or null",
      "vendor": "string or null",
      "category": "string or null",
      "quantity": 1.0,
      "confidence_score": 0.90
    }
  ]
}

Document Content:
\"\"\"
{content}
\"\"\"
"""


GENERIC_EXTRACTION_PROMPT = """You are an AI Data Center Engineer. Extract all data center hardware, cables, power units, or components from the following text into structured JSON.

Respond strictly with a JSON object matching this schema:
{
  "records": [
    {
      "part_number": "string or null",
      "description": "string or null",
      "quantity": 1.0,
      "unit": "pcs",
      "vendor": "string or null",
      "category": "string or null",
      "location": "string or null",
      "source_device": "string or null",
      "source_port": "string or null",
      "target_device": "string or null",
      "target_port": "string or null",
      "cable_type": "string or null",
      "confidence_score": 0.85
    }
  ]
}

Document Content:
\"\"\"
{content}
\"\"\"
"""
