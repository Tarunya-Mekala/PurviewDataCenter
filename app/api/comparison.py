"""Comparison, reconciliation, results, issue groups, and runs endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_super_admin
from app.models.user import User
from app.schemas.comparison import (
    ComparisonResponse,
    ComparisonResultsListResponse,
    ComparisonRunListResponse,
    IssueGroupListResponse,
)
from app.services.comparison_service import ComparisonService

router = APIRouter(
    tags=["Comparison & Reconciliation"],
    dependencies=[Depends(get_current_super_admin)],
)


@router.post(
    "/projects/{project_id}/compare",
    response_model=ComparisonResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute comparison run (Plan vs Vendor Delivery)",
    description="Deterministic comparison comparing approved plan records with approved vendor delivery records. Persists run history, results, and issue groups.",
)
def execute_comparison(
    project_id: str,
    rack: Optional[str] = Query(None, description="Optional rack filter"),
    vendor_id: Optional[str] = Query(None, description="Optional vendor filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ComparisonService.compare_project(
        db=db,
        project_id=project_id,
        rack=rack,
        vendor_id=vendor_id,
        persist_run=True,
    )


@router.get(
    "/projects/{project_id}/compare",
    response_model=ComparisonResponse,
    summary="Compare approved plan vs vendor delivery (GET)",
    description="Compares approved engineering plan records with approved vendor delivery records per rack and vendor, returning Match, Discrepancy, or Exception with actionable next steps.",
)
def compare_plan_and_vendor(
    project_id: str,
    rack: Optional[str] = Query(None, description="Filter comparison by specific rack (e.g. Rack-A01)"),
    vendor_id: Optional[str] = Query(None, description="Filter comparison by specific vendor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ComparisonService.compare_project(
        db=db,
        project_id=project_id,
        rack=rack,
        vendor_id=vendor_id,
        persist_run=True,
    )


@router.get(
    "/projects/{project_id}/results",
    response_model=ComparisonResultsListResponse,
    summary="List granular comparison results",
    description="Retrieve line-by-line comparison result lines with support for grouping (issue, rack, vendor), status filtering, and search.",
)
def get_comparison_results(
    project_id: str,
    group_by: Optional[str] = Query(None, description="Group results by: 'issue', 'rack', or 'vendor'"),
    result: Optional[str] = Query(None, description="Filter by result status: 'match', 'discrepancy', 'exception'"),
    vendor_id: Optional[str] = Query(None, description="Filter by vendor ID"),
    rack: Optional[str] = Query(None, description="Filter by rack identifier"),
    q: Optional[str] = Query(None, description="Search query for part number, item, or cause"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Page size"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ComparisonService.get_results(
        db=db,
        project_id=project_id,
        group_by=group_by,
        result=result,
        vendor_id=vendor_id,
        rack=rack,
        q=q,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/projects/{project_id}/issue-groups",
    response_model=IssueGroupListResponse,
    summary="List comparison issue groups",
    description="Get summarized issue clusters grouping discrepancies and exceptions by cause, vendor, and equipment category.",
)
def get_issue_groups(
    project_id: str,
    run_id: Optional[str] = Query(None, description="Optional run ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ComparisonService.get_issue_groups(
        db=db,
        project_id=project_id,
        run_id=run_id,
    )


@router.get(
    "/projects/{project_id}/runs",
    response_model=ComparisonRunListResponse,
    summary="List comparison runs history",
    description="Retrieve all historical comparison runs for this project.",
)
def get_comparison_runs(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return ComparisonService.get_runs(db=db, project_id=project_id)
