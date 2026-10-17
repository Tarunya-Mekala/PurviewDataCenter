from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExportCreateRequest(BaseModel):
    type: str = Field(..., description="'full' | 'issues' | 'vendor'")
    vendor_id: Optional[str] = None
    file_name: Optional[str] = None
    line_count: Optional[int] = 0


class ExportRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    export_type: str
    vendor_id: Optional[str] = None
    file_name: str
    line_count: int
    created_by: Optional[str] = None
    created_at: datetime
    type: Optional[str] = None

    def model_post_init(self, __context):
        if not self.type:
            self.type = self.export_type


class ExportRecordListResponse(BaseModel):
    total: int
    items: List[ExportRecordResponse]
