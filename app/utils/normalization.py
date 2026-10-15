import re
from typing import Any, Dict, Optional, Tuple


VENDOR_KEYWORDS = [
    "cisco", "arista", "juniper", "dell", "hp", "hpe", "supermicro",
    "panduit", "apc", "schneider", "eaton", "corning", "commscope",
    "intel", "nvidia", "mellanox", "broadcom", "amphenol"
]


def clean_header_string(header: str) -> str:
    """Normalize column header to lowercase alphanumeric snake_case."""
    if not header:
        return ""
    clean = re.sub(r"[^\w\s]", " ", str(header)).strip().lower()
    return re.sub(r"\s+", "_", clean)


def match_column_name(header: str) -> Optional[str]:
    """
    Map an arbitrary table column header to standard canonical schema fields.
    Returns: 'part_number', 'description', 'quantity', 'vendor', 'location',
             'source_device', 'source_port', 'target_device', 'target_port', 'cable_type', 'category'
    """
    h = clean_header_string(header)
    if not h:
        return None

    # Part Number / Model
    if any(k in h for k in ["part_num", "part_no", "part_#", "pn", "p_n", "model", "sku", "item_code", "product_code"]):
        return "part_number"
    if h in ["part", "model_number", "partno", "item_no"]:
        return "part_number"

    # Description
    if any(k in h for k in ["description", "desc", "specification", "item_desc", "details"]):
        return "description"
    if h in ["item", "name", "item_name", "product_name"]:
        return "description"

    # Quantity
    if any(k in h for k in ["quantity", "qty", "count", "pcs", "units", "total_qty"]):
        return "quantity"

    # Vendor / Manufacturer
    if any(k in h for k in ["vendor", "manufacturer", "mfg", "brand", "make", "supplier"]):
        return "vendor"

    # Location / Rack Elevation
    if any(k in h for k in ["rack", "cabinet", "location", "elevation", "slot", "ru", "rack_id", "rack_unit"]):
        return "location"

    # Category
    if any(k in h for k in ["category", "device_type", "equip_type", "hardware_type"]):
        return "category"

    # P2P / Cabling fields
    if any(k in h for k in ["source_port", "src_port", "from_port", "port_a"]):
        return "source_port"
    if any(k in h for k in ["target_port", "dst_port", "dest_port", "to_port", "port_b"]):
        return "target_port"
    if any(k in h for k in ["source_dev", "src_dev", "source", "from_device", "device_a"]):
        return "source_device"
    if any(k in h for k in ["target_dev", "dest_dev", "target", "destination", "to_device", "device_b"]):
        return "target_device"
    if any(k in h for k in ["cable_type", "cable", "media_type", "cord_type"]):
        return "cable_type"

    return None


def extract_vendor_from_text(text: str) -> Optional[str]:
    """Detect well-known data center hardware vendors in part number or description."""
    if not text:
        return None
    lower = text.lower()
    for v in VENDOR_KEYWORDS:
        if re.search(r"\b" + re.escape(v) + r"\b", lower):
            return v.capitalize()
    return None


def parse_quantity(val: Any) -> float:
    """Safely convert arbitrary quantity value to float."""
    if val is None:
        return 1.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return 1.0
    return 1.0
