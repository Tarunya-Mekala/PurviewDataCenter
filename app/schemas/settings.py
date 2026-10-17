from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    high_confidence_threshold: float = 0.90
    check_confidence_threshold: float = 0.70
    external_project_name: Optional[str] = None
    inactivity_days: int = 30
    updated_at: Optional[datetime] = None


class SettingsUpdate(BaseModel):
    high_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    check_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    external_project_name: Optional[str] = None
    inactivity_days: Optional[int] = Field(None, ge=1)
