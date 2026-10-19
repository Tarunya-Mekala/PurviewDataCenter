from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.comparison_run import ComparisonResultItem, ComparisonRun
from app.models.document import Document
from app.models.extracted_record import ExtractedRecord
from app.models.project import Project
from app.models.user import User
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    DashboardUrgentItem,
    DashboardVendorIssueCount,
)

router = APIRouter(tags=["Dashboard"])


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    summary="Get aggregated dashboard summary",
    description="Compute ready-made totals over active projects: open actions, records waiting for review, failed files, top 5 urgent items, top 5 vendors by open issues.",
)
def get_dashboard_summary(
    scope: str = Query("all", description="'mine' | 'all'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    proj_stmt = select(Project.id).where(Project.status == "active")
    if scope == "mine":
        proj_stmt = proj_stmt.where(
            (Project.owner_id == current_user.id) | (Project.created_by == current_user.email)
        )
    active_proj_ids = db.execute(proj_stmt).scalars().all()

    if not active_proj_ids:
        return DashboardSummaryResponse(
            scope=scope,
            active_projects_count=0,
            open_actions=0,
            records_waiting_for_review=0,
            failed_files=0,
            top_5_urgent_items=[],
            top_5_vendors_by_open_issues=[],
        )

    # 1. Records waiting for review
    records_waiting = (
        db.execute(
            select(func.count(ExtractedRecord.id)).where(
                ExtractedRecord.project_id.in_(active_proj_ids),
                ExtractedRecord.is_deleted == False,
                ExtractedRecord.review_status == "pending_review",
            )
        ).scalar()
        or 0
    )

    # 2. Failed files
    failed_files = (
        db.execute(
            select(func.count(Document.id)).where(
                Document.project_id.in_(active_proj_ids),
                Document.status == "failed",
            )
        ).scalar()
        or 0
    )

    # 3. Open actions (non-match items from comparison results)
    open_actions_stmt = (
        select(func.count(ComparisonResultItem.id))
        .join(ComparisonRun, ComparisonResultItem.run_id == ComparisonRun.id)
        .where(
            ComparisonRun.project_id.in_(active_proj_ids),
            ComparisonResultItem.result.in_(["exception", "discrepancy"]),
        )
    )
    open_actions = db.execute(open_actions_stmt).scalar() or 0

    # 4. Top 5 urgent items (Exceptions first, then discrepancies)
    urgent_stmt = (
        select(ComparisonResultItem, ComparisonRun.project_id)
        .join(ComparisonRun, ComparisonResultItem.run_id == ComparisonRun.id)
        .where(
            ComparisonRun.project_id.in_(active_proj_ids),
            ComparisonResultItem.result.in_(["exception", "discrepancy"]),
        )
        .order_by(
            ComparisonResultItem.result.asc(),
            ComparisonResultItem.created_at.desc(),
        )
        .limit(5)
    )
    urgent_rows = db.execute(urgent_stmt).all()
    urgent_items = []
    for item, proj_id in urgent_rows:
        urgent_items.append(
            DashboardUrgentItem(
                id=item.id,
                project_id=proj_id,
                item=item.item,
                part_number=item.part_number,
                rack=item.rack,
                result=item.result,
                cause=item.cause,
                action=item.action,
            )
        )

    # 5. Top 5 vendors by open issues
    vendor_issues_stmt = (
        select(
            ComparisonResultItem.vendor_name,
            func.count(ComparisonResultItem.id).label("issue_count"),
        )
        .join(ComparisonRun, ComparisonResultItem.run_id == ComparisonRun.id)
        .where(
            ComparisonRun.project_id.in_(active_proj_ids),
            ComparisonResultItem.result.in_(["exception", "discrepancy"]),
            ComparisonResultItem.vendor_name.isnot(None),
        )
        .group_by(ComparisonResultItem.vendor_name)
        .order_by(desc("issue_count"))
        .limit(5)
    )
    vendor_issue_rows = db.execute(vendor_issues_stmt).all()
    top_vendors = [
        DashboardVendorIssueCount(vendor_name=r[0] or "Unknown", issue_count=r[1])
        for r in vendor_issue_rows
    ]

    return DashboardSummaryResponse(
        scope=scope,
        active_projects_count=len(active_proj_ids),
        open_actions=open_actions,
        records_waiting_for_review=records_waiting,
        failed_files=failed_files,
        top_5_urgent_items=urgent_items,
        top_5_vendors_by_open_issues=top_vendors,
    )
