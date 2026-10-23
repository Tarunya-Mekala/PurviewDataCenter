"""Header synonym mapping and column resolution for tabular data extraction."""
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# Master synonym map for canonical document comparison fields
COLUMN_SYNONYMS: Dict[str, List[str]] = {
    "part_number": [
        "part no", "part number", "part #", "part#", "manufacturer part #",
        "mfr part #", "mfr part", "pid vid", "pid", "device", "sku",
        "item code", "model no", "model #", "p/n", "pn", "product code",
        "item no", "cable part number"
    ],
    "serial_number": [
        "serial no", "serial number", "serial #", "serial#", "s/n", "sn",
        "barcode sl no", "serial", "serial_num", "service tag", "asset tag"
    ],
    "quantity": [
        "qty", "quantity", "count", "qty shpd", "qty rcvd", "units",
        "no of units", "no. of units", "total qty", "pcs", "shipped qty",
        "received qty", "qty received", "amount"
    ],
    "rack": [
        "rack", "rack id", "rack source", "rack #", "cabinet", "cabinet id"
    ],
    "u_position": [
        "u", "ru", "u position", "rack unit", "u pos", "unit position",
        "elevation", "slot"
    ],
    "location": [
        "location", "site", "datacenter location", "room", "facility"
    ],
    "description": [
        "description", "desc", "item description", "product", "item name",
        "item desc", "details", "specification"
    ],
    "model": [
        "model", "hardware model", "model name"
    ],
    "manufacturer": [
        "manufacturer", "mfg", "brand", "make"
    ],
    "vendor": [
        "vendor", "supplier", "vendor name", "supplier name", "vendor / supplier",
        "po vendor", "po supplier", "po / supplier", "po/supplier",
        "po", "po #", "po#", "po number", "po no", "purchase order", "purchase order #", "po ref"
    ],
    "power_kw": [
        "power kw", "power (kw)", "kw", "power", "power consumption"
    ],
    "cable_length_m": [
        "cable length m", "length m", "length (m)", "cable length", "length",
        "length_m", "cable length (ft)", "length (ft)"
    ],
    "source_device": [
        "source device", "src dev", "from device", "device a", "rack a",
        "source rack", "from rack", "source"
    ],
    "target_device": [
        "target device", "dst dev", "dest dev", "to device", "device b",
        "rack b", "target rack", "to rack", "target", "destination"
    ],
    "source_port": [
        "source port", "src port", "from port", "port a"
    ],
    "target_port": [
        "target port", "dst port", "dest port", "to port", "port b"
    ],
    "cable_type": [
        "cable type", "cable", "media type", "cord type"
    ],
    "category": [
        "category", "device type", "equip type", "hardware type"
    ],
    "condition_notes": [
        "notes", "condition notes", "remarks", "comments", "test notes"
    ],
    "hostname": [
        "hostname", "host name", "device hostname", "node name", "device name", "system name", "server name", "host"
    ],
    "delivery_date": [
        "delivery date", "delivery_date", "received", "received date",
        "date received", "delivered date", "ship date", "arrival date",
        "delivery dt", "rcvd date"
    ],
}


def normalize_header(header: str) -> str:
    """Normalize headers before matching: lowercase, trim, collapse spaces, remove . : #"""
    if not header:
        return ""
    s = str(header).lower().strip()
    s = re.sub(r"[.:#]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_part_number(val: Optional[str]) -> Optional[str]:
    """
    Keep the value exactly as written (e.g. 'HF6100-32D V01') and
    store a cleaned version for matching (e.g. 'HF6100-32D').
    Strips trailing hardware version/rev suffixes.
    """
    if not val:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    # Strip trailing version/rev, e.g. "HF6100-32D V01" -> "HF6100-32D"
    cleaned = re.sub(r"[\s_-]+v(er)?\.?\s*\d+(\.\d+)?$", "", val_str, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s_-]+rev\.?\s*[a-z0-9]+$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def map_headers(headers: List[str]) -> Tuple[Dict[str, str], Dict[str, float]]:
    """
    Given a list of original table column headers:
    1. Normalizes each header.
    2. Finds the best match across canonical synonym lists.
    3. Guarantees that no two columns map to the same canonical field (best match wins).
    Returns:
      - col_to_field: {orig_header: canonical_field}
      - col_match_confidence: {orig_header: 1.0 (exact) or 0.85 (loose)}
    """
    norm_headers = [(h, normalize_header(h)) for h in headers]

    # Collect all possible matches: (score, orig_header, canonical_field, is_exact)
    candidate_matches = []

    for orig_h, norm_h in norm_headers:
        if not norm_h:
            continue

        for canonical_field, synonyms in COLUMN_SYNONYMS.items():
            if canonical_field == "quantity":
                # Never map date columns to quantity (Problem 4 fix)
                is_date = any(w in norm_h.split() or w == norm_h for w in ["received", "date", "timestamp", "time", "eta", "delivered"]) and not any(k in norm_h for k in ["qty", "quantity", "count", "units", "pcs"])
                if is_date:
                    continue

            for syn in synonyms:
                norm_syn = normalize_header(syn)
                if not norm_syn:
                    continue

                if norm_h == norm_syn:
                    # Exact full match: highest priority
                    score = 100.0 + len(norm_syn)
                    candidate_matches.append((score, orig_h, canonical_field, 1.0))
                    break
                elif re.search(r"\b" + re.escape(norm_syn) + r"\b", norm_h):
                    # Multi-word or whole-word phrase match
                    score = 50.0 + len(norm_syn)
                    candidate_matches.append((score, orig_h, canonical_field, 0.90))
                elif re.search(r"\b" + re.escape(norm_h) + r"\b", norm_syn):
                    score = 40.0 + len(norm_h)
                    candidate_matches.append((score, orig_h, canonical_field, 0.85))

    # Sort descending by score
    candidate_matches.sort(key=lambda x: x[0], reverse=True)

    assigned_fields: Set[str] = set()
    assigned_cols: Set[str] = set()
    col_to_field: Dict[str, str] = {}
    col_confidence: Dict[str, float] = {}

    for _, orig_h, canonical_field, conf in candidate_matches:
        if orig_h not in assigned_cols and canonical_field not in assigned_fields:
            col_to_field[orig_h] = canonical_field
            col_confidence[orig_h] = conf
            assigned_cols.add(orig_h)
            assigned_fields.add(canonical_field)

    return col_to_field, col_confidence


def is_doa_or_test_column(header: str) -> bool:
    """Check if header relates to DOA or component functional testing."""
    h = normalize_header(header)
    # Exclude PSU identification / serial columns like 'psu1', 'psu2', 'psu pid vid', 'psu serial', etc.
    if re.search(r"\bpsu\s*\d+\b", h) or re.search(r"\bpsu\b.*(pid|vid|serial|sn|s/n)", h):
        return False
    if any(k in h for k in ["doa", "test", "functional", "qc", "inspection"]):
        return not any(k in h for k in ["part", "serial", "quantity", "description"])
    if any(k in h for k in ["fans", "chassis", "leds"]) and not any(k in h for k in ["part", "serial", "quantity", "description"]):
        return True
    return False


def detect_condition(raw_row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Examines DOA/test columns and notes in a row.
    Returns:
      (condition, condition_notes)
      condition: "failed" | "ok" | None
    """
    test_columns_found = 0
    has_failure = False
    condition_notes: List[str] = []

    for k, v in raw_row.items():
        if v is None:
            continue
        v_str = str(v).strip()
        h_norm = normalize_header(k)

        # Check for notes
        if any(term in h_norm for term in ["notes", "remarks", "comments", "condition notes"]):
            if v_str:
                condition_notes.append(v_str)
                # Check for explicit failure notes like "incorrect fans", "failed", "defective"
                v_lower = v_str.lower()
                if any(w in v_lower for w in ["fail", "failed", "defect", "damage", "broken", "incorrect", "bad", "burn", "short"]):
                    has_failure = True

        # Check for test/DOA columns
        if is_doa_or_test_column(k):
            test_columns_found += 1
            lower_val = v_str.lower()
            # If boolean False, or text 'fail', 'failed', 'f', 'bad', 'broken', 'false', '0', 'no'
            if lower_val in ["false", "fail", "failed", "f", "0", "no", "bad", "broken"]:
                has_failure = True
                condition_notes.append(f"{k}: {v_str}")
            elif lower_val in ["true", "pass", "passed", "p", "1", "yes", "ok"]:
                pass

    final_condition = None
    if test_columns_found > 0 or condition_notes:
        final_condition = "failed" if has_failure else ("ok" if test_columns_found > 0 else None)

    notes_str = "; ".join(condition_notes) if condition_notes else None
    return final_condition, notes_str
