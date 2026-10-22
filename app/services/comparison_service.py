import re
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
        created_by: Optional[str] = None,
    ) -> ComparisonResponse:
        """Compare approved plan records against approved vendor delivery records."""
        project = db.get(Project, project_id)
        if not project or getattr(project, "is_deleted", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        # 1. Fetch approved plan records
        plan_docs_stmt = select(Document).where(
            Document.project_id == project_id,
            Document.source == "plan",
        )
        plan_docs = db.execute(plan_docs_stmt).scalars().all()
        plan_doc_ids = [d.id for d in plan_docs]

        plan_records_query = select(ExtractedRecord).where(
            ExtractedRecord.document_id.in_(plan_doc_ids),
            ExtractedRecord.is_deleted == False,
            ExtractedRecord.review_status.in_([
                ReviewStatus.APPROVED.value,
                ReviewStatus.MODIFIED.value,
                ReviewStatus.READ_CLEARLY.value,
                "read_clearly",
            ]),
        )
        if rack:
            plan_records_query = plan_records_query.where(
                (ExtractedRecord.rack == rack) | (ExtractedRecord.location == rack)
            )
        plan_records = db.execute(plan_records_query).scalars().all() if plan_doc_ids else []

        # 2. Fetch approved vendor records
        # Problem 15: For corrected vendor files, only select latest version of each file
        vendor_docs = db.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.source == "vendor",
            )
        ).scalars().all()
        if vendor_id:
            vendor_docs = [d for d in vendor_docs if d.vendor_id == vendor_id]

        latest_docs_by_name: Dict[str, Tuple[Document, int]] = {}
        for d in vendor_docs:
            clean_name = re.sub(r"_v\d+([_\.\-]|$)", "", d.filename.lower())
            m = re.search(r"_v(\d+)", d.filename.lower())
            file_version = int(m.group(1)) if m else d.version
            effective_version = max(d.version, file_version)
            if clean_name not in latest_docs_by_name or effective_version > latest_docs_by_name[clean_name][1]:
                latest_docs_by_name[clean_name] = (d, effective_version)

        active_vendor_docs = [pair[0] for pair in latest_docs_by_name.values()]
        vendor_doc_ids = [d.id for d in active_vendor_docs]
        doc_to_vendor = {d.id: d.vendor_id for d in active_vendor_docs}

        # Cache vendor names & vendor objects
        vendors_stmt = select(Vendor).where(Vendor.project_id == project_id)
        project_vendors = db.execute(vendors_stmt).scalars().all()
        vendor_names = {v.id: v.name for v in project_vendors}

        vendor_records_query = select(ExtractedRecord).where(
            ExtractedRecord.document_id.in_(vendor_doc_ids),
            ExtractedRecord.is_deleted == False,
            ExtractedRecord.review_status.in_([
                ReviewStatus.APPROVED.value,
                ReviewStatus.MODIFIED.value,
                ReviewStatus.READ_CLEARLY.value,
                "read_clearly",
            ]),
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
                    "vendor": r.vendor,
                    "manufacturer": r.manufacturer,
                    "u_position": r.u_position,
                    "power_kw": r.power_kw,
                    "cable_type": r.cable_type,
                    "cable_length_m": r.cable_length_m,
                    "source_ref": f"{r.source_sheet or 'Plan'}:R{r.source_row or 0}",
                    "quantity": 0.0,
                    "raw_data": r.raw_data or {},
                }
            else:
                if not plan_map[key].get("vendor") and r.vendor:
                    plan_map[key]["vendor"] = r.vendor
                if not plan_map[key].get("manufacturer") and r.manufacturer:
                    plan_map[key]["manufacturer"] = r.manufacturer
                if not plan_map[key].get("category") and r.category:
                    plan_map[key]["category"] = r.category
                if not plan_map[key].get("raw_data") and r.raw_data:
                    plan_map[key]["raw_data"] = r.raw_data
            plan_map[key]["quantity"] += qty

        # 4. Aggregate Vendor records by canonical (part_key, rack_key)
        vendor_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r in vendor_records:
            part_key = r.cleaned_part_number or r.part_number or "UNKNOWN"
            rack_key = r.rack or r.location or "UNASSIGNED"
            key = (part_key.upper(), rack_key.upper())

            # For serial lists: each line is one serial, so found = count of serials
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

        # Precompute category coverage per vendor from vendor records and active vendor docs
        vendor_category_counts: Dict[str, Dict[str, int]] = {}
        for r in vendor_records:
            v_id_rec = doc_to_vendor.get(r.document_id)
            if v_id_rec and r.category:
                cat_norm = r.category.strip().lower()
                if cat_norm:
                    vendor_category_counts.setdefault(v_id_rec, {})
                    vendor_category_counts[v_id_rec][cat_norm] = (
                        vendor_category_counts[v_id_rec].get(cat_norm, 0) + 1
                    )

        category_keywords = {
            "cable": "cable",
            "cabling": "cable",
            "fiber": "cable",
            "cooling": "cooling",
            "containment": "containment",
            "pdu": "pdu",
            "power": "power",
            "ups": "ups",
            "rack": "rack",
            "cabinet": "rack",
            "switch": "network",
            "switching": "network",
            "network": "network",
            "optics": "optics",
            "transceiver": "optics",
            "sensor": "sensor",
            "server": "server",
        }
        for d in active_vendor_docs:
            if d.vendor_id:
                fname_lower = (d.filename or "").lower()
                for kw, mapped_cat in category_keywords.items():
                    if kw in fname_lower:
                        vendor_category_counts.setdefault(d.vendor_id, {})
                        vendor_category_counts[d.vendor_id][mapped_cat] = (
                            vendor_category_counts[d.vendor_id].get(mapped_cat, 0) + 1
                        )

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

            # B2: Missing items have no vendor -> assign vendor
            if not v_id:
                if vendor_id:
                    v_id = vendor_id
                    v_name = vendor_names.get(v_id)
                elif len(project_vendors) == 1:
                    # 1. One-vendor check -> that vendor
                    v_id = project_vendors[0].id
                    v_name = project_vendors[0].name
                else:
                    # 2. Check supplier / PO column on the plan line
                    plan_cand_strings: List[str] = []
                    if p_data:
                        if p_data.get("vendor"):
                            plan_cand_strings.append(str(p_data["vendor"]).strip())
                        if p_data.get("manufacturer"):
                            plan_cand_strings.append(str(p_data["manufacturer"]).strip())
                        raw_dict = p_data.get("raw_data") or {}
                        for r_k, r_v in raw_dict.items():
                            rk_clean = str(r_k).lower().strip()
                            rv_str = str(r_v).strip() if r_v is not None else ""
                            if rv_str and any(h in rk_clean for h in ["po", "purchase order", "supplier", "vendor", "order"]):
                                plan_cand_strings.append(rv_str)

                    matched_vendor: Optional[Tuple[str, str]] = None
                    stop_words = {
                        "inc", "corp", "corporation", "ltd", "llc", "co", "company",
                        "systems", "solutions", "electric", "it", "technologies",
                        "group", "holdings", "services", "division", "infrastructure"
                    }
                    for cand in plan_cand_strings:
                        cand_clean = cand.strip().lower()
                        if not cand_clean or cand_clean in ["none", "null", "n/a", "na", "-", ""]:
                            continue
                        for pv in project_vendors:
                            pv_name_clean = pv.name.strip().lower()
                            if pv_name_clean == cand_clean or pv_name_clean in cand_clean or cand_clean in pv_name_clean:
                                matched_vendor = (pv.id, pv.name)
                                break
                            pv_tokens = [
                                t for t in re.split(r"[\s,\.\-_]+", pv.name.lower())
                                if len(t) >= 3 and t not in stop_words
                            ]
                            for tok in pv_tokens:
                                if re.search(r"\b" + re.escape(tok) + r"\b", cand_clean) or tok in cand_clean:
                                    matched_vendor = (pv.id, pv.name)
                                    break
                            if matched_vendor:
                                break
                        if matched_vendor:
                            break

                    if matched_vendor:
                        v_id, v_name = matched_vendor
                    else:
                        # 3. Check vendor whose files cover that category
                        item_cat = (cat_display or "").strip().lower()
                        if item_cat:
                            cat_scores: Dict[str, int] = {}
                            for v_id_cand, cat_dict in vendor_category_counts.items():
                                for covered_cat, count in cat_dict.items():
                                    if item_cat == covered_cat:
                                        cat_scores[v_id_cand] = cat_scores.get(v_id_cand, 0) + 100 + count
                                    elif item_cat in covered_cat or covered_cat in item_cat:
                                        cat_scores[v_id_cand] = cat_scores.get(v_id_cand, 0) + 50 + count
                                    elif any(
                                        kw in item_cat and kw in covered_cat
                                        for kw in ["cable", "cooling", "containment", "power", "pdu", "ups", "rack", "network", "switch", "optics", "sensor", "server"]
                                    ):
                                        cat_scores[v_id_cand] = cat_scores.get(v_id_cand, 0) + 20 + count

                            if cat_scores:
                                best_vid = max(cat_scores.items(), key=lambda x: x[1])[0]
                                v_id = best_vid
                                v_name = vendor_names.get(best_vid)

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

            # Classification according to business rules:
            if expected_qty > 0 and found_qty == 0:
                status_code = ComparisonStatus.EXCEPTION
                exceptions_count += 1
                cause = "Missing item"
                details = f"Item planned ({expected_qty:.0f} units) but not delivered by vendor."
                action = "Follow up with vendor for pending shipment."
                rule_id = "RULE_MISSING_ITEM"
                exp_num = expected_qty
                fnd_num = 0.0
                exp_text = f"{expected_qty:.0f}" if expected_qty.is_integer() else f"{expected_qty}"
                fnd_text = "Not delivered"
            elif expected_qty == 0 and found_qty > 0:
                status_code = ComparisonStatus.EXCEPTION
                exceptions_count += 1
                cause = "Extra item"
                details = f"Unexpected item ({found_qty:.0f} units) delivered by vendor not in approved plan."
                action = "Verify unauthorized delivery or check for substituted part number."
                rule_id = "RULE_EXTRA_ITEM"
                exp_num = 0.0
                fnd_num = found_qty
                exp_text = "Not in plan"
                fnd_text = f"{found_qty:.0f}" if found_qty.is_integer() else f"{found_qty}"
            elif diff != 0:
                status_code = ComparisonStatus.EXCEPTION
                exceptions_count += 1
                cause = "Quantity different"
                rule_id = "RULE_QTY_MISMATCH"
                exp_num = expected_qty
                fnd_num = found_qty
                exp_text = f"{expected_qty:.0f}" if expected_qty.is_integer() else f"{expected_qty}"
                fnd_text = f"{found_qty:.0f}" if found_qty.is_integer() else f"{found_qty}"
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
                exp_num = expected_qty
                fnd_num = found_qty
                exp_text = f"{expected_qty:.0f}" if expected_qty.is_integer() else f"{expected_qty}"
                fnd_text = f"{found_qty:.0f}" if found_qty.is_integer() else f"{found_qty}"
            elif p_data and v_data and p_data.get("model") and v_data.get("model") and p_data["model"] != v_data["model"]:
                status_code = ComparisonStatus.DISCREPANCY
                discrepancies_count += 1
                cause = "Model different"
                details = f"Model mismatch: planned '{p_data['model']}', found '{v_data['model']}'."
                action = "Review hardware model difference with engineering."
                rule_id = "RULE_MODEL_MISMATCH"
                exp_num = expected_qty
                fnd_num = found_qty
                exp_text = p_data["model"]
                fnd_text = v_data["model"]
            elif p_data and v_data and p_data.get("u_position") and v_data.get("u_position") and p_data["u_position"] != v_data["u_position"]:
                status_code = ComparisonStatus.DISCREPANCY
                discrepancies_count += 1
                cause = "Rack / U position different"
                details = f"U-elevation mismatch: planned {p_data['u_position']}, delivered {v_data['u_position']}."
                action = "Relocate equipment to designated rack / U slot."
                rule_id = "RULE_LOCATION_MISMATCH"
                exp_num = expected_qty
                fnd_num = found_qty
                exp_text = f"U{p_data['u_position']}"
                fnd_text = f"U{v_data['u_position']}"
            else:
                status_code = ComparisonStatus.MATCH
                matches_count += 1
                cause = "Exact match"
                details = "Delivered hardware matches engineering plan exactly with healthy condition."
                action = "Accept / Verified for data center rack installation."
                rule_id = "RULE_MATCH"
                exp_num = expected_qty
                fnd_num = found_qty
                exp_text = f"{expected_qty:.0f}" if expected_qty.is_integer() else f"{expected_qty}"
                fnd_text = f"{found_qty:.0f}" if found_qty.is_integer() else f"{found_qty}"

            raw_items.append({
                "part_number": part_display,
                "cleaned_part_number": clean_part_display,
                "description": desc_display,
                "rack": rack_display,
                "vendor_id": v_id,
                "vendor_name": v_name,
                "category": cat_display,
                "item": desc_display or part_display,
                "expected": exp_num,
                "found": fnd_num,
                "expected_text": exp_text,
                "found_text": fnd_text,
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
        doc_versions_list = [
            {
                "document_id": d.id,
                "filename": d.filename,
                "version": d.version,
                "source": d.source,
                "document_type": d.document_type,
                "vendor_id": d.vendor_id,
                "checksum_sha256": d.checksum_sha256,
            }
            for d in (plan_docs + active_vendor_docs)
        ]

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
                created_by=created_by,
                document_versions=doc_versions_list,
                is_frozen=True,
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
                    expected_text=it.get("expected_text"),
                    found_text=it.get("found_text"),
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

            # Record audit log for comparison run
            try:
                from app.api.audit import record_audit_log
                record_audit_log(
                    db=db,
                    action="compare",
                    resource_type="project",
                    resource_id=project_id,
                    project_id=project_id,
                    details={
                        "run_id": run_id,
                        "matches_count": matches_count,
                        "discrepancies_count": discrepancies_count,
                        "exceptions_count": exceptions_count,
                    },
                )
            except Exception:
                pass

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
                expected_text=it.get("expected_text"),
                found_text=it.get("found_text"),
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
            created_by=created_by,
            document_versions=doc_versions_list if persist_run else None,
        )

    @staticmethod
    def get_results(
        db: Session,
        project_id: str,
        run_id: Optional[str] = None,
        group_by: Optional[str] = None,
        result: Optional[str] = None,
        vendor_id: Optional[str] = None,
        rack: Optional[str] = None,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ComparisonResultsListResponse:
        """Fetch granular comparison result lines for a project with filters and pagination."""
        project = db.get(Project, project_id)
        if not project or getattr(project, "is_deleted", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        query = select(ComparisonResultItem).where(ComparisonResultItem.project_id == project_id)

        if not run_id:
            latest_run_id = db.execute(
                select(ComparisonRun.id)
                .where(ComparisonRun.project_id == project_id)
                .order_by(ComparisonRun.run_number.desc(), ComparisonRun.started_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest_run_id:
                query = query.where(ComparisonResultItem.run_id == latest_run_id)
                run_id = latest_run_id
        else:
            query = query.where(ComparisonResultItem.run_id == run_id)

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
            run_id=run_id,
            items=[ComparisonResultLine.model_validate(it) for it in items],
        )

    @staticmethod
    def get_issue_groups(
        db: Session,
        project_id: str,
        run_id: Optional[str] = None,
    ) -> IssueGroupListResponse:
        """Retrieve issue groups summarizing common discrepancies and exceptions."""
        project = db.get(Project, project_id)
        if not project or getattr(project, "is_deleted", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        query = select(IssueGroup).where(IssueGroup.project_id == project_id)
        if not run_id:
            latest_run_id = db.execute(
                select(ComparisonRun.id)
                .where(ComparisonRun.project_id == project_id)
                .order_by(ComparisonRun.run_number.desc(), ComparisonRun.started_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest_run_id:
                query = query.where(IssueGroup.run_id == latest_run_id)
                run_id = latest_run_id
        else:
            query = query.where(IssueGroup.run_id == run_id)

        groups = db.execute(query.order_by(IssueGroup.total_lines.desc())).scalars().all()
        return IssueGroupListResponse(
            total=len(groups),
            run_id=run_id,
            items=[IssueGroupResponse.model_validate(g) for g in groups],
        )

    @staticmethod
    def get_runs(db: Session, project_id: str) -> ComparisonRunListResponse:
        """Retrieve comparison runs history for a project."""
        project = db.get(Project, project_id)
        if not project or getattr(project, "is_deleted", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        query = select(ComparisonRun).where(ComparisonRun.project_id == project_id).order_by(ComparisonRun.run_number.desc())
        runs = db.execute(query).scalars().all()
        return ComparisonRunListResponse(
            total=len(runs),
            items=[ComparisonRunResponse.model_validate(r) for r in runs],
        )

    @staticmethod
    def get_run(db: Session, project_id: str, run_id: str) -> ComparisonRunResponse:
        """Retrieve a specific frozen comparison run by ID."""
        project = db.get(Project, project_id)
        if not project or getattr(project, "is_deleted", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        run = db.execute(
            select(ComparisonRun).where(
                ComparisonRun.project_id == project_id,
                ComparisonRun.id == run_id,
            )
        ).scalar_one_or_none()
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comparison run '{run_id}' not found for project '{project_id}'.",
            )
        return ComparisonRunResponse.model_validate(run)

    @staticmethod
    def get_run_report(
        db: Session,
        project_id: str,
        run_id: str,
        rack: Optional[str] = None,
        vendor_id: Optional[str] = None,
    ) -> ComparisonResponse:
        """Rebuild or retrieve full comparison report exactly from a frozen run."""
        project = db.get(Project, project_id)
        if not project or getattr(project, "is_deleted", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

        run = db.execute(
            select(ComparisonRun).where(
                ComparisonRun.project_id == project_id,
                ComparisonRun.id == run_id,
            )
        ).scalar_one_or_none()
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comparison run '{run_id}' not found for project '{project_id}'.",
            )

        query = select(ComparisonResultItem).where(ComparisonResultItem.run_id == run_id)
        if rack:
            query = query.where(ComparisonResultItem.rack == rack)
        if vendor_id:
            query = query.where(ComparisonResultItem.vendor_id == vendor_id)

        items_db = db.execute(query.order_by(ComparisonResultItem.created_at.asc())).scalars().all()

        items: List[ComparisonItem] = [
            ComparisonItem(
                part_number=it.part_number,
                cleaned_part_number=None,
                description=it.item,
                rack=it.rack,
                vendor_id=it.vendor_id,
                vendor_name=it.vendor_name,
                category=it.category,
                expected_quantity=it.expected,
                found_quantity=it.found,
                expected_text=it.expected_text,
                found_text=it.found_text,
                difference=it.difference,
                status=ComparisonStatus(it.result.upper()),
                condition_status=it.condition_status,
                condition_notes=it.condition_notes,
                details=it.action,
                action=it.action,
                cause=it.cause,
                rule_id=it.rule_id,
                issue_group_id=it.issue_group_id,
                issue_summary=it.issue_summary,
                expected_source=it.expected_source,
                found_source=it.found_source,
            )
            for it in items_db
        ]

        if not rack and not vendor_id:
            matches_count = run.matches_count
            discrepancies_count = run.discrepancies_count
            exceptions_count = run.exceptions_count
            total_expected = run.total_expected
            total_found = run.total_found
        else:
            matches_count = sum(1 for it in items if it.status == ComparisonStatus.MATCH)
            discrepancies_count = sum(1 for it in items if it.status == ComparisonStatus.DISCREPANCY)
            exceptions_count = sum(1 for it in items if it.status == ComparisonStatus.EXCEPTION)
            total_expected = sum(it.expected_quantity or 0.0 for it in items)
            total_found = sum(it.found_quantity or 0.0 for it in items)

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
            run_id=run.id,
            rule_set_version=run.rule_set_version,
            rack=rack,
            vendor_id=vendor_id,
            summary=summary,
            items=items,
            created_by=run.created_by,
            document_versions=run.document_versions,
        )
