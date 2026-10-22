import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple, Union

from fastapi import HTTPException, UploadFile, status

from app.schemas.document import DocumentType

ALLOWED_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".xlsm",
    ".csv",
    ".tsv",
    ".pdf",
    ".docx",
    ".doc",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".zip",
}

EXTENSION_MIME_MAP = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".zip": "application/zip",
}


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing dangerous path separators and special characters.
    """
    clean = os.path.basename(filename)
    clean = re.sub(r"[^\w\s\.-]", "_", clean).strip()
    clean = re.sub(r"\s+", "_", clean)
    if not clean or clean.startswith("."):
        clean = f"document_{clean.lstrip('.')}" if clean.lstrip(".") else "document"
    return clean


def get_file_extension(filename: str) -> str:
    """
    Extract lowercase extension including the dot.
    """
    return Path(filename).suffix.lower()


def validate_file_extension(filename: str) -> str:
    """
    Validate that the file extension is allowed.
    Raises HTTPException(415) if not supported.
    """
    ext = get_file_extension(filename)
    if not ext or ext not in ALLOWED_EXTENSIONS:
        allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext}'. Allowed types: {allowed_list}",
        )
    return ext


def detect_document_type(filename: str) -> DocumentType:
    """
    Auto-detect document type from filename keywords.
    """
    lower = filename.lower()
    if any(k in lower for k in ["bom", "bill_of_materials", "bill-of-materials", "materials"]):
        return DocumentType.BOM
    if any(k in lower for k in ["p2p", "point_to_point", "point-to-point", "port_to_port", "interconnect"]):
        return DocumentType.P2P
    if any(k in lower for k in ["rack", "elevation", "layout", "cabinet"]):
        return DocumentType.RACK_LAYOUT
    if any(k in lower for k in ["power", "pdu", "ups", "electric", "feed"]):
        return DocumentType.POWER
    if any(k in lower for k in ["cable", "cabling", "patch", "wiring", "fiber"]):
        return DocumentType.CABLE
    return DocumentType.OTHER


def get_mime_type_for_file(file_path: Union[Path, str]) -> str:
    """
    Get appropriate MIME type for download streaming.
    """
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MIME_MAP.get(ext, "application/octet-stream")


async def save_upload_file(
    upload_file: UploadFile,
    dest_path: Path,
    max_size_mb: Optional[int] = None,
) -> Tuple[int, str]:
    """
    Stream upload file to disk while calculating SHA-256.
    If max_size_mb is provided, enforces max size; otherwise allows unlimited size.
    Returns (file_size_bytes, sha256_checksum).
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = max_size_mb * 1024 * 1024 if max_size_mb else None
    total_bytes = 0
    hasher = hashlib.sha256()

    try:
        with open(dest_path, "wb") as f:
            chunk_size = 1024 * 1024  # 1MB chunks
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if max_bytes and total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {max_size_mb} MB",
                    )
                hasher.update(chunk)
                f.write(chunk)
    except Exception:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        raise

    return total_bytes, hasher.hexdigest()


def delete_file_safely(file_path: Path) -> bool:
    """
    Safely delete a file from disk if it exists.
    """
    try:
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    except OSError:
        return False
