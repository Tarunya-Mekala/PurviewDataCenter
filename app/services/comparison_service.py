"""Service for comparing approved plan records with approved vendor delivery records."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.comparison_run import ComparisonResultItem, ComparisonRun, IssueGroup
from app.models.document import Document
from app.models.extracted_record import ExtractedRecord
from app.models.project import Project
from app.models.vendor import Vendor
from app.schemas.comparison import (
    ComparisonItem,
    ComparisonResponse,
    ComparisonResultLine,
    ComparisonResultsListResponse,
    ComparisonRunListResponse,
    ComparisonRunResponse,
    ComparisonStatus,
    ComparisonSummary,
    IssueGroupListResponse,
    IssueGroupResponse,
)
from app.schemas.record import ReviewStatus
from app.utils.id_generator import generate_id


def get_utc_now():
    return datetime.now(timezone.utc)


class ComparisonService:

    @staticmethod
    def compare_project(
        db: Session,
        project_id: str,
        rack: Optional[str] = None,
        vendor_id: Optional[str] = None,
        persist_run: bool = True,
    ) -> ComparisonResponse:
        """Compare approved plan records against approved vendor delivery records."""
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        # 1. Fetch approved plan records
        plan_docs_stmt = select(Document.id).where(
            Document.project_id == project_id,
            Document.source == "plan",
        )
        plan_doc_ids = db.execute(plan_docs_stmt).scalars().all()

        plan_records_query = select(ExtractedRecord).where(
            ExtractedRecord.document_id.in_(plan_doc_ids),
            ExtractedRecord.is_deleted == False,
            ExtractedRecord.review_status.in_([ReviewStatus.APPROVED.value, ReviewStatus.MODIFIED.value]),
        )
        if rack:
            plan_records_query = plan_records_query.where(
                (ExtractedRecord.rack == rack) | (ExtractedRecord.location == rack)
            )
        plan_records = db.execute(plan_records_query).scalars().all() if plan_doc_ids else []

        # 2. Fetch approved vendor records
        vendor_docs_stmt = select(Document.id, Document.vendor_id).where(
            Document.project_id == project_id,
            Document.source == "vendor",
        )
        if vendor_id:
            vendor_docs_stmt = vendor_docs_stmt.where(Document.vendor_id == vendor_id)

        vendor_doc_rows = db.execute(vendor_docs_stmt).all()
        vendor_doc_ids = [r[0] for r in vendor_doc_rows]
        doc_to_vendor = {r[0]: r[1] for r in vendor_doc_rows}

        # Cache vendor names
        vendors_stmt = select(Vendor).where(Vendor.project_id == project_id)
        vendor_names = {v.id: v.name for v in db.execute(vendors_stmt).scalars().all()}

        vendor_records_query = select(ExtractedRecord).where(
            ExtractedRecord.document_id.in_(vendor_doc_ids),
            ExtractedRecord.is_deleted == False,
            ExtractedRecord.review_status.in_([ReviewStatus.APPROVED.value, ReviewStatus.MODIFIED.value]),
        )
        if rack:
            vendor_records_query = vendor_records_query.where(
                (ExtractedRecord.rack == rack) | (ExtractedRecord.location == rack)
            )
        vendor_records = db.execute(vendor_records_query).scalars().all() if vendor_doc_ids else []

        # 3. Aggregate Plan records by canonical (part_key, rack_key)
        # Rule: serial rows count as 1 each during comparison
        plan_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r in plan_records:
            part_key = r.cleaned_part_number or r.part_number or "UNKNOWN"
            rack_key = r.rack or r.location or "UNASSIGNED"
            key = (part_key.upper(), rack_key.upper())

            qty = r.quantity if r.quantity is not None else (1.0 if r.serial_number else 1.0)
            if key not in plan_map:
                plan_map[key] = {
                    "part_number": r.part_number or part_key,
                    "cleaned_part_number": r.cleaned_part_number,
                    "description": r.description,
                    "rack": r.rack or r.location,
                    "category": r.category,
                    "model": r.model,
                    "u_position": r.u_position,
                    "power_kw": r.power_kw,
                    "cable_type": r.cable_type,
                    "cable_length_m": r.cable_length_m,
                    "source_ref": f"{r.source_sheet or 'Plan'}:R{r.source_row or 0}",
                    "quantity": 0.0,
                }
            plan_map[key]["quantity"] += qty

        # 4. Aggregate Vendor records by canonical (part_key, rack_key)
        vendor_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r in vendor_records:
            part_key = r.cleaned_part_number or r.part_number or "UNKNOWN"
            rack_key = r.rack or r.location or "UNASSIGNED"
            key = (part_key.upper(), rack_key.upper())

            qty = r.quantity if r.quantity is not None else (1.0 if r.serial_number else 1.0)
            v_id = doc_to_vendor.get(r.document_id)
            v_name = vendor_names.get(v_id) if v_id else (r.vendor or "Unknown Vendor")

            if key not in vendor_map:
                vendor_map[key] = {
                    "part_number": r.part_number or part_key,
                    "cleaned_part_number": r.cleaned_part_number,
                    "description": r.description,
                    "rack": r.rack or r.location,
                    "category": r.category,
                    "model": r.model,
                    "u_position": r.u_position,
                    "power_kw": r.power_kw,
                    "cable_type": r.cable_type,
                    "cable_length_m": r.cable_length_m,
                    "source_ref": f"{r.source_sheet or 'Vendor'}:R{r.source_row or 0}",
                    "vendor_id": v_id,
                    "vendor_name": v_name,
                    "quantity": 0.0,
                    "conditions": [],
                    "condition_notes": [],
                }
            vendor_map[key]["quantity"] += qty
            if r.condition:
                vendor_map[key]["conditions"].append(r.condition)
            if r.condition_notes:
                vendor_map[key]["condition_notes"].append(r.condition_notes)

        # 5. Compare Expected vs Found using deterministic business rules
        all_keys = set(plan_map.keys()) | set(vendor_map.keys())
        raw_items: List[Dict[str, Any]] = []

        total_expected = 0.0
        total_found = 0.0
        matches_count = 0
        discrepancies_count = 0
        exceptions_count = 0

        for key in sorted(all_keys):
            p_data = plan_map.get(key)
            v_data = vendor_map.get(key)

            expected_qty = p_data["quantity"] if p_data else 0.0
            found_qty = v_data["quantity"] if v_data else 0.0
            total_expected += expected_qty
            total_found += found_qty

            diff = found_qty - expected_qty
            part_display = (p_data["part_number"] if p_data else (v_data["part_number"] if v_data else key[0]))
            clean_part_display = (p_data.get("cleaned_part_number") if p_data else (v_data.get("cleaned_part_number") if v_data else None))
            desc_display = (p_data.get("description") if p_data else (v_data.get("description") if v_data else None))
            rack_display = (p_data.get("rack") if p_data else (v_data.get("rack") if v_data else None))
            cat_display = (p_data.get("category") if p_data else (v_data.get("category") if v_data else "hardware"))
            v_id = v_data.get("vendor_id") if v_data else None
            v_name = v_data.get("vendor_name") if v_data else None

            has_condition_failure = False
            cond_str = None
            notes_str = None
            if v_data and v_data.get("conditions"):
                if "failed" in v_data["conditions"]:
                    has_condition_failure = True
                    cond_str = "failed"
                else:
                    cond_str = "ok"
            if v_data and v_data.get("condition_notes"):
                notes_str = "; ".join(v_data["condition_notes"])

            expected_src = p_data.get("source_ref") if p_data else None
            found_src = v_data.get("source_ref") if v_data else None

            # Classification according to Problem 27 specifications:
            if expected_qty > 0 and found_qty == 0:
                status_code = ComparisonStatus.EXCEPTION
                exceptions_count += 1
                cause = "Missing item"
                details = f"Item planned ({expected_qty:.0f} units) but not delivered by vendor."
                action = "Follow up with vendor for pending shipment."
                rule_id = "RULE_MISSING_ITEM"
            elif expected_qty == 0 and found_qty > 0:
                status_code = ComparisonStatus.EXCEPTION
                exceptions_count += 1
                cause = "Extra item"
                details = f"Unexpected item ({found_qty:.0f} units) delivered by vendor not in approved plan."
                action = "Verify unauthorized delivery or check for substituted part number."
                rule_id = "RULE_EXTRA_ITEM"
            elif diff != 0:
                status_code = ComparisonStatus.EXCEPTION
                exceptions_count += 1
                cause = "Quantity different"
                rule_id = "RULE_QTY_MISMATCH"
                if diff < 0:
                    details = f"Shortage detected: expected {expected_qty:.0f}, found {found_qty:.0f} (short by {abs(diff):.0f})."
                    action = "Request expedited shortage delivery or vendor credit."
                else:
                    details = f"Excess delivery: expected {expected_qty:.0f}, found {found_qty:.0f} (excess of {diff:.0f})."
                    action = "Verify excess delivery with procurement."
            elif has_condition_failure:
                status_code = ComparisonStatus.DISCREPANCY
                discrepancies_count += 1
                cause = "DOA / Hardware Test Failure"
                details = f"Unit condition failed (DOA/Testing Failure: {notes_str or 'Defective'})."
                action = "Initiate RMA return / quarantine defective unit."
                rule_id = "RULE_CONDITION_FAILED"
            elif p_data and v_data and p_data.get("model") and v_data.get("model") and p_data["model"] != v_data["model"]:
                status_code = ComparisonStatus.DISCREPANCY
                discrepancies_count += 1
                cause = "Model different"
                details = f"Model mismatch: planned '{p_data['model']}', found '{v_data['model']}'."
                action = "Review hardware model difference with engineering."
                rule_id = "RULE_MODEL_MISMATCH"
            elif p_data and v_data and p_data.get("u_position") and v_data.get("u_position") and p_data["u_position"] != v_data["u_position"]:
                status_code = ComparisonStatus.DISCREPANCY
                discrepancies_count += 1
                cause = "Rack / U position different"
                details = f"U-elevation mismatch: planned {p_data['u_position']}, delivered {v_data['u_position']}."
                action = "Relocate equipment to designated rack / U slot."
                rule_id = "RULE_LOCATION_MISMATCH"
            else:
                status_code = ComparisonStatus.MATCH
                matches_count += 1
                cause = "Exact match"
                details = "Delivered hardware matches engineering plan exactly with healthy condition."
                action = "Accept / Verified for data center rack installation."
                rule_id = "RULE_MATCH"

            raw_items.append({
                "part_number": part_display,
                "cleaned_part_number": clean_part_display,
                "description": desc_display,
                "rack": rack_display,
                "vendor_id": v_id,
                "vendor_name": v_name,
                "category": cat_display,
                "item": desc_display or part_display,
                "expected": expected_qty,
                "found": found_qty,
                "difference": diff,
                "status": status_code,
                "cause": cause,
                "rule_id": rule_id,
                "condition_status": cond_str,
                "condition_notes": notes_str,
                "details": details,
                "action": action,
                "expected_source": expected_src,
                "found_source": found_src,
            })

        # 6. Group discrepancies and exceptions into Issue Groups
        # "Group lines with the same cause + vendor + category into issue groups with a summary"
        issue_groups_dict: Dict[Tuple[str, Optional[str], Optional[str]], Dict[str, Any]] = {}
        for it in raw_items:
            if it["status"] != ComparisonStatus.MATCH:
                g_key = (it["cause"], it["vendor_id"], it["category"])
                if g_key not in issue_groups_dict:
                    issue_groups_dict[g_key] = {
                        "id": generate_id("grp_"),
                        "cause": it["cause"],
                        "vendor_id": it["vendor_id"],
                        "vendor_name": it["vendor_name"],
                        "category": it["category"],
                        "lines_count": 0,
                        "total_diff": 0.0,
                    }
                issue_groups_dict[g_key]["lines_count"] += 1
                issue_groups_dict[g_key]["total_diff"] += it["difference"]

        # Build issue summaries and link to items
        for it in raw_items:
            if it["status"] != ComparisonStatus.MATCH:
                g_key = (it["cause"], it["vendor_id"], it["category"])
                g_info = issue_groups_dict[g_key]
                it["issue_group_id"] = g_info["id"]
                it["issue_summary"] = (
                    f"{g_info['lines_count']} {g_info['category'] or 'equipment'} lines: "
                    f"{g_info['cause']} from {g_info['vendor_name'] or 'vendor'}"
                )
                g_info["summary"] = it["issue_summary"]

        # 7. Persist run and result items if requested
        run_id = None
        if persist_run:
            latest_run_num = db.execute(
                select(func.coalesce(func.max(ComparisonRun.run_number), 0)).where(
                    ComparisonRun.project_id == project_id
                )
            ).scalar() or 0
            new_run_num = int(latest_run_num) + 1
            run_id = generate_id("run_")

            run = ComparisonRun(
                id=run_id,
                project_id=project_id,
                run_number=new_run_num,
                status="completed",
                rule_set_version="1.0",
                total_expected=total_expected,
                total_found=total_found,
                matches_count=matches_count,
                discrepancies_count=discrepancies_count,
                exceptions_count=exceptions_count,
                started_at=get_utc_now(),
                finished_at=get_utc_now(),
            )
            db.add(run)

            # Persist issue groups
            for g_info in issue_groups_dict.values():
                ig = IssueGroup(
                    id=g_info["id"],
                    project_id=project_id,
                    run_id=run_id,
                    vendor_id=g_info["vendor_id"],
                    vendor_name=g_info["vendor_name"],
                    category=g_info["category"],
                    cause=g_info["cause"],
                    summary=g_info.get("summary", g_info["cause"]),
                    total_lines=g_info["lines_count"],
                )
                db.add(ig)

            # Persist result lines
            for it in raw_items:
                res_line = ComparisonResultItem(
                    id=generate_id("res_"),
                    project_id=project_id,
                    run_id=run_id,
                    rack=it["rack"],
                    vendor_id=it["vendor_id"],
                    vendor_name=it["vendor_name"],
                    category=it["category"],
                    item=it["item"],
                    part_number=it["part_number"],
                    field="quantity" if it["rule_id"] == "RULE_QTY_MISMATCH" else "hardware",
                    expected=it["expected"],
                    found=it["found"],
                    difference=it["difference"],
                    result=it["status"].value.lower(),
                    action=it["action"],
                    cause=it["cause"],
                    issue_group_id=it.get("issue_group_id"),
                    issue_summary=it.get("issue_summary"),
                    expected_source=it.get("expected_source"),
                    found_source=it.get("found_source"),
                    rule_id=it["rule_id"],
                    condition_status=it.get("condition_status"),
                    condition_notes=it.get("condition_notes"),
                )
                db.add(res_line)

            db.commit()

        # Build ComparisonItem objects
        items: List[ComparisonItem] = [
            ComparisonItem(
                part_number=it["part_number"],
                cleaned_part_number=it["cleaned_part_number"],
                description=it["description"],
                rack=it["rack"],
                vendor_id=it["vendor_id"],
                vendor_name=it["vendor_name"],
                category=it["category"],
                expected_quantity=it["expected"],
                found_quantity=it["found"],
                difference=it["difference"],
                status=it["status"],
                condition_status=it["condition_status"],
                condition_notes=it["condition_notes"],
                details=it["details"],
                action=it["action"],
                cause=it["cause"],
                rule_id=it["rule_id"],
                issue_group_id=it.get("issue_group_id"),
                issue_summary=it.get("issue_summary"),
                expected_source=it.get("expected_source"),
                found_source=it.get("found_source"),
            )
            for it in raw_items
        ]

        total_lines = len(items)
        match_rate = round((matches_count / total_lines * 100.0), 1) if total_lines > 0 else 0.0

        summary = ComparisonSummary(
            total_expected=total_expected,
            total_found=total_found,
            matches_count=matches_count,
            discrepancies_count=discrepancies_count,
            exceptions_count=exceptions_count,
            match_rate_percentage=match_rate,
        )

        return ComparisonResponse(
            project_id=project_id,
            run_id=run_id,
            rule_set_version="1.0",
            rack=rack,
            vendor_id=vendor_id,
            summary=summary,
            items=items,
        )

    @staticmethod
    def get_results(
        db: Session,
        project_id: str,
        group_by: Optional[str] = None,
        result: Optional[str] = None,
        vendor_id: Optional[str] = None,
        rack: Optional[str] = None,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ComparisonResultsListResponse:
        """Fetch granular comparison result lines for a project with filters and pagination."""
        query = select(ComparisonResultItem).where(ComparisonResultItem.project_id == project_id)

        if result:
            query = query.where(func.lower(ComparisonResultItem.result) == result.lower())
        if vendor_id:
            query = query.where(ComparisonResultItem.vendor_id == vendor_id)
        if rack:
            query = query.where(ComparisonResultItem.rack == rack)
        if q:
            search_pattern = f"%{q.lower()}%"
            query = query.where(
                or_(
                    func.lower(ComparisonResultItem.part_number).like(search_pattern),
                    func.lower(ComparisonResultItem.item).like(search_pattern),
                    func.lower(ComparisonResultItem.cause).like(search_pattern),
                )
            )

        # Ordering based on group_by
        if group_by == "issue":
            query = query.order_by(ComparisonResultItem.issue_group_id.asc(), ComparisonResultItem.created_at.desc())
        elif group_by == "rack":
            query = query.order_by(ComparisonResultItem.rack.asc(), ComparisonResultItem.created_at.desc())
        elif group_by == "vendor":
            query = query.order_by(ComparisonResultItem.vendor_name.asc(), ComparisonResultItem.created_at.desc())
        else:
            query = query.order_by(ComparisonResultItem.created_at.desc())

        total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
        offset = max(0, (page - 1) * page_size)
        items = db.execute(query.offset(offset).limit(page_size)).scalars().all()

        return ComparisonResultsListResponse(
            total=total,
            page=page,
            page_size=page_size,
            group_by=group_by,
            items=[ComparisonResultLine.model_validate(it) for it in items],
        )

    @staticmethod
    def get_issue_groups(
        db: Session,
        project_id: str,
        run_id: Optional[str] = None,
    ) -> IssueGroupListResponse:
        """Retrieve issue groups summarizing common discrepancies and exceptions."""
        query = select(IssueGroup).where(IssueGroup.project_id == project_id)
        if run_id:
            query = query.where(IssueGroup.run_id == run_id)
        groups = db.execute(query.order_by(IssueGroup.total_lines.desc())).scalars().all()
        return IssueGroupListResponse(
            total=len(groups),
            items=[IssueGroupResponse.model_validate(g) for g in groups],
        )

    @staticmethod
    def get_runs(db: Session, project_id: str) -> ComparisonRunListResponse:
        """Retrieve comparison runs history for a project."""
        query = select(ComparisonRun).where(ComparisonRun.project_id == project_id).order_by(ComparisonRun.run_number.desc())
        runs = db.execute(query).scalars().all()
        return ComparisonRunListResponse(
            total=len(runs),
            items=[ComparisonRunResponse.model_validate(r) for r in runs],
        )
