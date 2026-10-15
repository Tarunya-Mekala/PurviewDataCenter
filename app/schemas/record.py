from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReviewStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"


class RecordType(str, Enum):
    BOM_ITEM = "bom_item"
    RACK_ITEM = "rack_item"
    CABLE_ITEM = "cable_item"
    POWER_ITEM = "power_item"
    OTHER = "other"


class ExtractedRecordBase(BaseModel):
    record_type: RecordType = Field(default=RecordType.BOM_ITEM, description="Record category")
    category: Optional[str] = Field(None, description="Equipment category (e.g. Switch, Server, PDU)")
    part_number: Optional[str] = Field(None, description="Manufacturer part number or model")
    description: Optional[str] = Field(None, description="Item description or specifications")
    quantity: Optional[float] = Field(default=1.0, description="Item quantity")
    unit: Optional[str] = Field(default="pcs", description="Unit of measurement (pcs, meters, etc.)")
    vendor: Optional[str] = Field(None, description="Manufacturer or vendor brand")
    location: Optional[str] = Field(None, description="Physical location or Rack RU")
    source_device: Optional[str] = Field(None, description="Source device for cabling connections")
    source_port: Optional[str] = Field(None, description="Source port for cabling connections")
    target_device: Optional[str] = Field(None, description="Target device for cabling connections")
    target_port: Optional[str] = Field(None, description="Target port for cabling connections")
    cable_type: Optional[str] = Field(None, description="Cable media type (e.g. Cat6, Fiber, DAC)")


class ExtractedRecordCreate(ExtractedRecordBase):
    """Used by human reviewer to manually add a missing record."""
    review_notes: Optional[str] = Field(None, description="Notes on why this record was manually added")


class ExtractedRecordUpdate(BaseModel):
    """Used to edit/correct extracted record fields."""
    record_type: Optional[RecordType] = None
    category: Optional[str] = None
    part_number: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    vendor: Optional[str] = None
    location: Optional[str] = None
    source_device: Optional[str] = None
    source_port: Optional[str] = None
    target_device: Optional[str] = None
    target_port: Optional[str] = None
    cable_type: Optional[str] = None
    review_notes: Optional[str] = None


class ExtractedRecordReview(BaseModel):
    """Used to submit a human review decision (approve, reject, or modify)."""
    status: ReviewStatus = Field(..., description="Review decision: approved, modified, or rejected")
    review_notes: Optional[str] = Field(None, description="Reviewer feedback, notes, or justification")
    corrections: Optional[ExtractedRecordUpdate] = Field(
        None,
        description="Optional field corrections to apply concurrently with the review decision",
    )


class BatchReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class BatchReviewRequest(BaseModel):
    record_ids: List[str] = Field(..., description="List of record IDs to review")
    action: BatchReviewAction = Field(..., description="Action to perform: approve or reject")
    review_notes: Optional[str] = Field(None, description="Optional batch review notes")


class ExtractedRecordResponse(ExtractedRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    document_id: str
    confidence_score: float
    raw_data: Optional[Dict[str, Any]] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    review_status: ReviewStatus
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    is_manually_added: bool
    created_at: datetime
    updated_at: datetime


class RecordListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[ExtractedRecordResponse]


class ReviewSummaryResponse(BaseModel):
    project_id: str
    total_records: int
    pending_review_count: int
    approved_count: int
    modified_count: int
    rejected_count: int
    completion_percentage: float
    average_confidence: float
    by_record_type: Dict[str, int]
    by_vendor: Dict[str, int]


class ExtractionJobResponse(BaseModel):
    document_id: str
    document_name: str
    status: str
    records_extracted: int
    message: str
    model_used: Optional[str] = None


class AIExtractionRequest(BaseModel):
    model: Optional[str] = Field(
        None,
        description="Override Ollama model (e.g. 'qwen2.5:27b', 'qwen3.5:27b'). Defaults to system LLM_MODEL.",
    )


class RawTextExtractionRequest(BaseModel):
    text: str = Field(..., description="Raw text, unstructured BOM, or table text to extract with AI")
    document_type: Optional[str] = Field("bom", description="Document type: 'bom', 'p2p', 'rack_layout', 'other'")
    model: Optional[str] = Field(None, description="Ollama model to use (e.g. 'qwen2.5:27b')")


class DocumentExtractionStatusResponse(BaseModel):
    document_id: str
    filename: str
    document_type: str
    status: str
    total_records_extracted: int
    review_status_counts: Dict[str, int]
    error_message: Optional[str] = None

