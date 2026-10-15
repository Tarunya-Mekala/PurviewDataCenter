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
