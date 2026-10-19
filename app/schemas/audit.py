from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    total: int
    items: List[AuditLogResponse]
