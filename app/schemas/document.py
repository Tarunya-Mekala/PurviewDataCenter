from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    BOM = "bom"
    PLAN_BOM = "plan_bom"
    VENDOR_QUOTE = "vendor_quote"
    PURCHASE = "purchase"
    P2P = "p2p"  # Alias for purchase / legacy support
    RACK_LAYOUT = "rack_layout"
    POWER = "power"
    CABLE = "cable"
    OTHER = "other"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"


class DocumentBase(BaseModel):
    filename: str
    document_type: Union[DocumentType, str] = DocumentType.OTHER
    source: str = Field(default="plan", description="'plan' or 'vendor'")
    vendor_id: Optional[str] = Field(default=None, description="Vendor ID if source is vendor")


class DocumentUpdate(BaseModel):
    document_type: Optional[Union[DocumentType, str]] = None
    source: Optional[str] = None
    vendor_id: Optional[str] = None
    status: Optional[DocumentStatus] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    filename: str
    stored_filename: str
    file_type: str
    file_size: int
    document_type: Union[DocumentType, str]
    source: str = "plan"
    vendor_id: Optional[str] = None
    version: int = 1
    uploaded_by: Optional[str] = None
    status: Union[DocumentStatus, str]
    checksum_sha256: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime



class DocumentListResponse(BaseModel):
    total: int
    items: List[DocumentResponse]


class DocumentUploadFailure(BaseModel):
    filename: str
    reason: str


class DocumentUploadResult(BaseModel):
    successful: List[DocumentResponse]
    failed: List[DocumentUploadFailure]
