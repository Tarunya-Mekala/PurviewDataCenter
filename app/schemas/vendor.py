"""Schemas for Vendor entity."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class VendorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Vendor name (supplier of equipment/delivery)")
    contact_person: Optional[str] = Field(None, description="Contact person name")
    contact_email: Optional[str] = Field(None, description="Contact email address")
    contact_phone: Optional[str] = Field(None, description="Contact phone number")


class VendorCreate(VendorBase):
    pass


class VendorContactUpdate(BaseModel):
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated vendor name")
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class VendorResponse(VendorBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class VendorListResponse(BaseModel):
    total: int
    items: List[VendorResponse]

