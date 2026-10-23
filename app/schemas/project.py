from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProjectDocumentCounts(BaseModel):
    pending: int = 0
    parsing: int = 0
    parsed: int = 0
    extracting: int = 0
    extracted: int = 0
    failed: int = 0


class ProjectRecordCounts(BaseModel):
    total: int = 0
    pending_review: int = 0


class ProjectLatestRunCounts(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    run_number: int
    status: str = "completed"
    total_expected: float = 0.0
    total_found: float = 0.0
    matches_count: int = 0
    discrepancies_count: int = 0
    exceptions_count: int = 0
    match_rate_percentage: Optional[float] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(None, max_length=2000, description="Project description")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = Field(None, description="active, complete, or archived")


class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str = "active"
    owner_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    document_count: Optional[int] = 0
    document_counts: ProjectDocumentCounts = Field(default_factory=ProjectDocumentCounts)
    record_counts: ProjectRecordCounts = Field(default_factory=ProjectRecordCounts)
    vendor_names: List[str] = Field(default_factory=list, description="Vendor names associated with project")
    vendors: List[str] = Field(default_factory=list, description="Alias for vendor_names")
    latest_run: Optional[ProjectLatestRunCounts] = Field(None, description="Latest comparison run summary and counts")
    latest_run_counts: Optional[ProjectLatestRunCounts] = Field(None, description="Alias for latest_run")


class ProjectListResponse(BaseModel):
    total: int
    items: List[ProjectResponse]

