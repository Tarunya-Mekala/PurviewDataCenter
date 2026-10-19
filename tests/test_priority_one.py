"""Tests for Priority One Issues: Problem 17, Problem 18, and Problem 27."""
import io
import pytest
from fastapi import status


def test_problem_17_automatic_parsing_after_upload(client):
    """Problem 17: After upload, document is parsed in background (pending -> parsing -> parsed)."""
    # 1. Create project
    proj_res = client.post("/api/v1/projects", json={"name": "P17 Background Parsing Test"})
    assert proj_res.status_code == status.HTTP_201_CREATED
    project_id = proj_res.json()["id"]

    # 2. Upload file
    csv_content = b"Part Number,Description,Qty,Rack\nSW-101,Top of Rack Switch,2,Rack-01\n"
    files = [("files", ("switches.csv", io.BytesIO(csv_content), "text/csv"))]
    upload_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["successful"][0]["id"]

    # In FastAPI TestClient, BackgroundTasks execute before response returns.
    # Check document status: must be 'parsed' without calling /extract endpoint
    doc_check = client.get(f"/api/v1/projects/{project_id}/documents")
    assert doc_check.status_code == status.HTTP_200_OK
    docs = doc_check.json()["items"]
    target_doc = next(d for d in docs if d["id"] == doc_id)
    assert target_doc["status"] == "parsed"


def test_problem_18_exact_evidence_cell_highlighting(client):
    """Problem 18: Extracted record stores exact cell/col/row coordinates and GET /records/{id}/evidence highlights cell."""
    # 1. Create project & upload sample CSV
    proj_res = client.post("/api/v1/projects", json={"name": "P18 Evidence Test"})
    project_id = proj_res.json()["id"]

    csv_content = (
        "Part Number,Description,Qty,Rack\n"
        "HF-6100-64ED-D,Spine Switch,54,Rack-Spine-01\n"
        "HF6100-32D,Storage Leaf,2,Rack-Leaf-01\n"
    ).encode("utf-8")
    files = [("files", ("equipment_bom.csv", io.BytesIO(csv_content), "text/csv"))]
    upload_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    doc_id = upload_res.json()["successful"][0]["id"]

    # 2. Extract records
    extract_res = client.post(f"/api/v1/documents/{doc_id}/extract")
    assert extract_res.status_code == status.HTTP_200_OK

    # 3. Retrieve records and verify field_sources
    records_res = client.get(f"/api/v1/projects/{project_id}/records")
    items = records_res.json()["items"]
    assert len(items) == 2

    spine_rec = next(r for r in items if "64ED" in r["part_number"])
    assert spine_rec["field_sources"] is not None
    assert "part_number" in spine_rec["field_sources"]
    assert "col" in spine_rec["field_sources"]["part_number"]
    assert spine_rec["field_sources"]["part_number"]["col"] == "A"
    assert spine_rec["field_sources"]["part_number"]["row"] == 2

    # 4. Check GET /records/{id}/evidence
    ev_res = client.get(f"/api/v1/records/{spine_rec['id']}/evidence")
    assert ev_res.status_code == status.HTTP_200_OK
    evidence_data = ev_res.json()
    assert evidence_data["record_id"] == spine_rec["id"]
    assert evidence_data["evidence_type"] == "excel"

    ev = evidence_data["evidence"]
    assert "headers" in ev
    assert "rows" in ev
    assert "highlight" in ev
    assert ev["highlight"]["row"] == 2
    assert ev["highlight"]["col"] == "A"


def test_problem_27_comparison_and_results_rules(client):
    """Problem 27: Compare approved plan with vendor records using exact rules (no AI).
    Spine switch HF-6100-64ED-D expected 54, received 48 = Exception.
    Storage leaf HF6100-32D expected 2, received 4 = Exception.
    """
    # 1. Create project and vendor
    proj_res = client.post("/api/v1/projects", json={"name": "P27 Comparison Rules Test"})
    project_id = proj_res.json()["id"]

    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "NorthGate Systems"})
    vendor_id = vnd_res.json()["id"]

    # 2. Upload Plan document
    plan_csv = (
        "Part Number,Description,Qty,Rack\n"
        "HF-6100-64ED-D,Spine Switch,54,Spine-Rack-1\n"
        "HF6100-32D,Storage Leaf,2,Leaf-Rack-1\n"
        "N9K-C93180YC,Access Switch,10,Access-Rack-1\n"
    ).encode("utf-8")
    files_plan = [("files", ("plan.csv", plan_csv, "text/csv"))]
    plan_res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_plan,
        data={"source": "plan", "document_type": "bom"},
    )
    plan_doc_id = plan_res.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{plan_doc_id}/extract")

    # 3. Upload Vendor document (received 48 of spine switch, received 4 of storage leaf, received 10 of access switch)
    vendor_csv = (
        "Part Number,Description,Qty,Rack\n"
        "HF-6100-64ED-D,Spine Switch,48,Spine-Rack-1\n"
        "HF6100-32D,Storage Leaf,4,Leaf-Rack-1\n"
        "N9K-C93180YC,Access Switch,10,Access-Rack-1\n"
    ).encode("utf-8")
    files_vendor = [("files", ("delivery.csv", vendor_csv, "text/csv"))]
    vendor_res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_vendor,
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    vendor_doc_id = vendor_res.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{vendor_doc_id}/extract")

    # 4. Approve all records
    records = client.get(f"/api/v1/projects/{project_id}/records?limit=100").json()["items"]
    record_ids = [r["id"] for r in records]
    batch_res = client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": record_ids, "action": "approve", "review_notes": "Approved for comparison"},
    )
    assert batch_res.status_code == status.HTTP_200_OK

    # 5. Run comparison POST /projects/{id}/compare
    cmp_res = client.post(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    cmp_data = cmp_res.json()

    summary = cmp_data["summary"]
    assert summary["matches_count"] == 1  # N9K-C93180YC (10 expected == 10 received)
    assert summary["exceptions_count"] == 2  # 54 vs 48 (shortage) and 2 vs 4 (excess)

    items = {item["part_number"]: item for item in cmp_data["items"]}
    spine = items["HF-6100-64ED-D"]
    assert spine["status"] == "EXCEPTION"
    assert spine["expected_quantity"] == 54.0
    assert spine["found_quantity"] == 48.0
    assert spine["difference"] == -6.0

    leaf = items["HF6100-32D"]
    assert leaf["status"] == "EXCEPTION"
    assert leaf["expected_quantity"] == 2.0
    assert leaf["found_quantity"] == 4.0
    assert leaf["difference"] == 2.0

    # 6. Check GET /projects/{id}/results
    res_list = client.get(f"/api/v1/projects/{project_id}/results?result=exception")
    assert res_list.status_code == status.HTTP_200_OK
    res_data = res_list.json()
    assert res_data["total"] == 2

    # Check result fields
    first_item = res_data["items"][0]
    for required_field in [
        "rack", "vendor_id", "vendor_name", "category", "item", "part_number",
        "field", "expected", "found", "result", "action", "cause", "rule_id",
    ]:
        assert required_field in first_item

    # 7. Check GET /projects/{id}/issue-groups
    groups_res = client.get(f"/api/v1/projects/{project_id}/issue-groups")
    assert groups_res.status_code == status.HTTP_200_OK
    groups = groups_res.json()["items"]
    assert len(groups) >= 1
    assert groups[0]["cause"] == "Quantity different"
    assert groups[0]["total_affected_lines"] == 2

    # 8. Check GET /projects/{id}/runs
    runs_res = client.get(f"/api/v1/projects/{project_id}/runs")
    assert runs_res.status_code == status.HTTP_200_OK
    runs = runs_res.json()["items"]
    assert len(runs) >= 1
    assert runs[0]["run_number"] == 1
    assert runs[0]["status"] == "completed"
