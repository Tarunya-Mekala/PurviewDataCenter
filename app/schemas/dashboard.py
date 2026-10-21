from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DashboardVendorIssueCount(BaseModel):
    vendor_name: str
    issue_count: int


class DashboardUrgentItem(BaseModel):
    id: str
    project_id: str
    item: str
    part_number: Optional[str] = None
    rack: Optional[str] = None
    result: str
    cause: Optional[str] = None
    action: Optional[str] = None


class DashboardSummaryResponse(BaseModel):
    scope: str
    active_projects_count: int
    open_actions: int
    records_waiting_for_review: int
    failed_files: int
    top_5_urgent_items: List[DashboardUrgentItem]
    top_5_vendors_by_open_issues: List[DashboardVendorIssueCount]
