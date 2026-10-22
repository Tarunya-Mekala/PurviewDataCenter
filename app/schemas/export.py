from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExportCreateRequest(BaseModel):
    type: str = Field(..., description="'full' | 'issues' | 'vendor'")
    vendor_id: Optional[str] = None
    file_name: Optional[str] = None
    line_count: Optional[int] = 0
    run_id: Optional[str] = None


class ExportRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    export_type: str
    vendor_id: Optional[str] = None
    file_name: str
    file_path: Optional[str] = None
    checksum_sha256: Optional[str] = None
    fingerprint: Optional[str] = None
    run_id: Optional[str] = None
    line_count: int
    created_by: Optional[str] = None
    created_at: datetime
    type: Optional[str] = None

    def model_post_init(self, __context):
        if not self.type:
            self.type = self.export_type
        if not self.fingerprint and self.checksum_sha256:
            self.fingerprint = self.checksum_sha256


class ExportRecordListResponse(BaseModel):
    total: int
    items: List[ExportRecordResponse]
