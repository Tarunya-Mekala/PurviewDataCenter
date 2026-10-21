"""Schemas for BOM comparison, results, runs, and issue groups."""
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ComparisonStatus(str, Enum):
    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"
    EXCEPTION = "EXCEPTION"


class ComparisonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    part_number: str
    cleaned_part_number: Optional[str] = None
    description: Optional[str] = None
    rack: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    expected_quantity: Optional[float] = None
    found_quantity: Optional[float] = None
    expected_text: Optional[str] = None
    found_text: Optional[str] = None
    difference: float = 0.0
    status: ComparisonStatus
    condition_status: Optional[str] = None
    condition_notes: Optional[str] = None
    details: str
    action: str
    cause: Optional[str] = None
    rule_id: Optional[str] = None
    issue_group_id: Optional[str] = None
    issue_summary: Optional[str] = None
    expected_source: Optional[str] = None
    found_source: Optional[str] = None


class ComparisonSummary(BaseModel):
    total_expected: float
    total_found: float
    matches_count: int
    discrepancies_count: int
    exceptions_count: int
    match_rate_percentage: float


class ComparisonResponse(BaseModel):
    project_id: str
    run_id: Optional[str] = None
    rule_set_version: Optional[str] = "1.0"
    rack: Optional[str] = None
    vendor_id: Optional[str] = None
    summary: ComparisonSummary
    items: List[ComparisonItem]


class ComparisonResultLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    project_id: str
    rack: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    item: Optional[str] = None
    part_number: str
    field: Optional[str] = None
    expected: Optional[float] = None
    found: Optional[float] = None
    expected_text: Optional[str] = None
    found_text: Optional[str] = None
    difference: float = 0.0
    result: str  # match | discrepancy | exception
    action: str
    cause: str
    issue_group_id: Optional[str] = None
    issue_summary: Optional[str] = None
    expected_source: Optional[str] = None
    found_source: Optional[str] = None
    rule_id: str
    condition_status: Optional[str] = None
    condition_notes: Optional[str] = None
    created_at: datetime


class ComparisonResultsListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    group_by: Optional[str] = None
    items: List[ComparisonResultLine]


class IssueGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    run_id: str
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    cause: str
    summary: str
    total_lines: int
    total_affected_lines: Optional[int] = None
    created_at: datetime

    def model_post_init(self, __context):
        if self.total_affected_lines is None:
            self.total_affected_lines = self.total_lines


class IssueGroupListResponse(BaseModel):
    total: int
    items: List[IssueGroupResponse]


class ComparisonRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    run_number: int
    status: str
    rule_set_version: str
    total_expected: float
    total_found: float
    matches_count: int
    discrepancies_count: int
    exceptions_count: int
    started_at: datetime
    finished_at: Optional[datetime] = None


class ComparisonRunListResponse(BaseModel):
    total: int
    items: List[ComparisonRunResponse]
