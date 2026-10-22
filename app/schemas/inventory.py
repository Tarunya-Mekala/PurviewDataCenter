from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class SourceProvenance(BaseModel):
    """
    Tracks where an extracted value came from.
    """

    file_name: Optional[str] = None
    sheet_name: Optional[str] = None
    source_row: Optional[int] = None
    source_column: Optional[str] = None
    source_text: Optional[str] = None


class CanonicalInventoryRecord(BaseModel):
    """
    Generic canonical record used across BOM, P2P, Rack,
    Power, Cable and other document categories.

    The fields are intentionally optional because different
    categories contain different information.
    """

    model_config = ConfigDict(extra="allow")

    category: str = Field(
        default="bom",
        description="Business document category"
    )

    record_type: str = Field(
        default="inventory_item"
    )

    equipment_name: Optional[str] = None

    part_number: Optional[str] = None

    serial_number: Optional[str] = None

    description: Optional[str] = None

    model: Optional[str] = None

    manufacturer: Optional[str] = None

    vendor: Optional[str] = None

    condition: Optional[str] = None

    condition_notes: Optional[str] = None

    quantity: Optional[float] = Field(
        default=None,
        ge=0
    )

    unit: Optional[str] = None

    location: Optional[str] = None

    rack: Optional[str] = None

    rack_id: Optional[str] = None

    u_position: Optional[str] = None

    source_device: Optional[str] = None

    source_port: Optional[str] = None

    target_device: Optional[str] = None

    target_port: Optional[str] = None

    cable_type: Optional[str] = None

    length: Optional[str] = None

    power_watts: Optional[float] = Field(
        default=None,
        ge=0
    )

    dimensions: Optional[str] = None

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0
    )

    provenance: Optional[SourceProvenance] = None

    raw_data: dict[str, Any] = Field(
        default_factory=dict
    )

    extra_fields: dict[str, Any] = Field(
        default_factory=dict
    )


class CanonicalInventoryDocument(BaseModel):
    """
    Canonical output returned by the AI extraction pipeline.
    """

    document_category: str

    records: list[CanonicalInventoryRecord] = Field(
        default_factory=list
    )

    mapping_notes: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )