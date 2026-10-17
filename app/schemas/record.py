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
    part_number: Optional[str] = Field(None, description="Manufacturer part number or model as written")
    cleaned_part_number: Optional[str] = Field(None, description="Standardized part number stripped of minor revision tags")
    model: Optional[str] = Field(None, description="Hardware model name")
    serial_number: Optional[str] = Field(None, description="Unit serial number / service tag")
    condition: Optional[str] = Field(None, description="Unit condition: 'ok', 'failed', or null")
    condition_notes: Optional[str] = Field(None, description="DOA or test failure remarks")
    description: Optional[str] = Field(None, description="Item description or specifications")
    quantity: Optional[float] = Field(default=None, description="Item quantity (null when unstated)")
    unit: Optional[str] = Field(default=None, description="Unit of measurement (pcs, meters, etc.)")
    vendor: Optional[str] = Field(None, description="Supplier / vendor brand")
    manufacturer: Optional[str] = Field(None, description="Equipment maker / brand (Dell, Cisco, etc.)")
    location: Optional[str] = Field(None, description="Physical location or Rack RU")
    rack: Optional[str] = Field(None, description="Rack identifier (e.g. RACK-A01)")
    u_position: Optional[str] = Field(None, description="Rack unit position (e.g. U12, RU42)")
    power_kw: Optional[float] = Field(None, description="Power rating in kW")
    cable_length_m: Optional[float] = Field(None, description="Cable length in meters")
    source_device: Optional[str] = Field(None, description="Source device / rack for cabling connections")
    source_port: Optional[str] = Field(None, description="Source port for cabling connections")
    target_device: Optional[str] = Field(None, description="Target device / rack for cabling connections")
    target_port: Optional[str] = Field(None, description="Target port for cabling connections")
    cable_type: Optional[str] = Field(None, description="Cable media type (e.g. Cat6, Fiber, DAC)")
    field_sources: Optional[Dict[str, Any]] = Field(None, description="Precise cell or area coordinate evidence per field")


class ExtractedRecordCreate(ExtractedRecordBase):
    """Used by human reviewer to manually add a missing record."""
    review_notes: Optional[str] = Field(None, description="Notes on why this record was manually added")


class ExtractedRecordUpdate(BaseModel):
    """Used to edit/correct extracted record fields."""
    record_type: Optional[RecordType] = None
    category: Optional[str] = None
    part_number: Optional[str] = None
    cleaned_part_number: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    condition: Optional[str] = None
    condition_notes: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    vendor: Optional[str] = None
    manufacturer: Optional[str] = None
    location: Optional[str] = None
    rack: Optional[str] = None
    u_position: Optional[str] = None
    power_kw: Optional[float] = None
    cable_length_m: Optional[float] = None
    source_device: Optional[str] = None
    source_port: Optional[str] = None
    target_device: Optional[str] = None
    target_port: Optional[str] = None
    cable_type: Optional[str] = None
    field_sources: Optional[Dict[str, Any]] = None
    review_notes: Optional[str] = None
    review_reason: Optional[str] = None


class ExtractedRecordReview(BaseModel):
    """Used to submit a human review decision (approve, reject, or modify)."""
    status: ReviewStatus = Field(..., description="Review decision: approved, modified, or rejected")
    review_notes: Optional[str] = Field(None, description="Reviewer feedback, notes, or justification (required for modified/rejected)")
    corrections: Optional[ExtractedRecordUpdate] = Field(
        None,
        description="Optional field corrections to apply concurrently with the review decision",
    )

    from pydantic import model_validator

    @model_validator(mode="after")
    def validate_notes_for_rejection_or_modification(self) -> "ExtractedRecordReview":
        if self.status in [ReviewStatus.MODIFIED, ReviewStatus.REJECTED]:
            if not self.review_notes or len(self.review_notes.strip()) < 3:
                raise ValueError("review_notes must be at least 3 characters when status is 'modified' or 'rejected'")
        return self


class BatchReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class BatchReviewRequest(BaseModel):
    record_ids: List[str] = Field(..., description="List of record IDs to review")
    action: BatchReviewAction = Field(..., description="Action to perform: approve or reject")
    review_notes: Optional[str] = Field(None, description="Optional batch review notes")
    min_confidence: Optional[float] = Field(None, description="Minimum confidence score required for approval (records below are skipped)")



class RecordReviewActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    record_id: str
    action: str
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    reviewer_id: Optional[str] = None
    created_at: datetime


class ExtractedRecordResponse(ExtractedRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    document_id: str
    confidence_score: float = Field(..., description="Extraction confidence score from 0.0 to 1.0")
    raw_data: Optional[Dict[str, Any]] = None
    unmapped_columns: List[str] = Field(default_factory=list, description="Names of unmapped or unlabelled columns with data")
    review_reason: Optional[str] = Field(None, description="Reason flagged for human review (missing_value, unmapped_field, low_confidence, etc.)")
    original_values: Optional[Dict[str, Any]] = Field(None, description="Original parsed values immutable copy for audit/undo")
    extraction_method: Optional[str] = Field("table", description="'table' or 'ai'")
    model_used: Optional[str] = Field(None, description="LLM model used if AI extracted")
    is_deleted: bool = False
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
    by_manufacturer: Optional[Dict[str, int]] = None


class ExtractionJobResponse(BaseModel):
    document_id: str
    document_name: str
    status: str
    records_extracted: int
    message: str
    model_used: Optional[str] = None
    fallback: Optional[bool] = None


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


class AIStatusResponse(BaseModel):
    available: bool = Field(..., description="Whether Ollama engine is reachable and available")
    reachable: bool = Field(True, description="Alias for available")
    ollama_online: bool = Field(True, description="Alias for available")
    model: Optional[str] = Field(None, description="Active configured model")
    configured_model: Optional[str] = None
    installed_models: List[str] = Field(default_factory=list, description="Models currently pulled in Ollama")
    recommended_model: Optional[str] = None
    message: Optional[str] = None


class RecordEvidenceResponse(BaseModel):
    record_id: str
    document_id: str
    document_name: Optional[str] = None
    evidence_type: str = Field(..., description="'excel' | 'image' | 'text'")
    evidence: Dict[str, Any]


