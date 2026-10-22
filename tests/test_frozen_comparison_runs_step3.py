"""Test suite for Step 3: Frozen comparison runs and export run linkage."""
import io
import uuid
from fastapi import status


def _setup_comparison_project(client):
    """Helper to set up a project with plan and vendor documents extracted and approved."""
    proj_name = f"Frozen Run Project {uuid.uuid4().hex[:8]}"
    proj_res = client.post("/api/v1/projects", json={"name": proj_name})
    assert proj_res.status_code == status.HTTP_201_CREATED
    project_id = proj_res.json()["id"]

    # 1. Create vendor
    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Cisco Systems"})
    vendor_id = vnd_res.json()["id"]

    # 2. Upload Plan document (v1)
    plan_csv = (
        "Part Number,Description,Qty,Vendor,Rack\n"
        "N9K-C93180YC-FX,Nexus 9300 48-port,4,Cisco Systems,Rack-A01\n"
        "C9300-48P,Catalyst Switch,2,Cisco Systems,Rack-A01\n"
    ).encode("utf-8")
    files_plan = [("files", ("dc_plan_v1.csv", io.BytesIO(plan_csv), "text/csv"))]
    plan_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_plan,
        data={"source": "plan", "document_type": "bom"},
    )
    plan_doc_id = plan_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{plan_doc_id}/extract")

    # 3. Upload Vendor Delivery document (v1)
    vendor_csv = (
        "Part Number,Description,Qty,Vendor,Rack\n"
        "N9K-C93180YC-FX,Nexus 9300 48-port,4,Cisco Systems,Rack-A01\n"
        "C9300-48P,Catalyst Switch,1,Cisco Systems,Rack-A01\n"
    ).encode("utf-8")
    files_vendor = [("files", ("cisco_delivery_v1.csv", io.BytesIO(vendor_csv), "text/csv"))]
    vendor_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_vendor,
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    vendor_doc_id = vendor_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{vendor_doc_id}/extract")

    # 4. Approve all records
    records = client.get(f"/api/v1/projects/{project_id}/records?limit=100").json()["items"]
    record_ids = [r["id"] for r in records]
    client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": record_ids, "action": "approve", "review_notes": "Approved for comparison"},
    )

    return project_id, vendor_id, plan_doc_id, vendor_doc_id


def test_post_compare_saves_frozen_run_with_complete_audit_trail(client):
    """Test that POST /compare persists an immutable run containing:
    - results & issue groups
    - rule-set version
    - document versions used
    - who (created_by) and when (started_at/finished_at)
    """
    project_id, vendor_id, plan_doc_id, vendor_doc_id = _setup_comparison_project(client)

    # 1. Execute comparison run via POST /projects/{id}/compare
    cmp_res = client.post(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    cmp_data = cmp_res.json()

    run_id_1 = cmp_data["run_id"]
    assert run_id_1 is not None
    assert cmp_data["rule_set_version"] == "1.0"
    assert cmp_data["created_by"] is not None

    # Check document versions captured in run
    doc_versions = cmp_data["document_versions"]
    assert doc_versions is not None
    assert len(doc_versions) == 2
    doc_ids = {d["document_id"] for d in doc_versions}
    assert plan_doc_id in doc_ids
    assert vendor_doc_id in doc_ids

    # 2. Verify frozen run details via GET /projects/{id}/runs/{run_id}
    run_detail_res = client.get(f"/api/v1/projects/{project_id}/runs/{run_id_1}")
    assert run_detail_res.status_code == status.HTTP_200_OK
    run_detail = run_detail_res.json()
    assert run_detail["id"] == run_id_1
    assert run_detail["run_number"] == 1
    assert run_detail["status"] == "completed"
    assert run_detail["rule_set_version"] == "1.0"
    assert run_detail["matches_count"] == 1
    assert run_detail["exceptions_count"] == 1
    assert run_detail["created_by"] is not None
    assert run_detail["started_at"] is not None
    assert run_detail["finished_at"] is not None
    assert run_detail["is_frozen"] is True
    assert len(run_detail["document_versions"]) == 2

    # 3. Verify results and issue groups are stored under run_id_1
    res_list = client.get(f"/api/v1/projects/{project_id}/results?run_id={run_id_1}").json()
    assert res_list["total"] == 2
    for item in res_list["items"]:
        assert item["run_id"] == run_id_1

    grp_list = client.get(f"/api/v1/projects/{project_id}/issue-groups?run_id={run_id_1}").json()
    assert grp_list["total"] >= 1
    for grp in grp_list["items"]:
        assert grp["run_id"] == run_id_1


def test_frozen_run_immutability_and_report_rebuild(client):
    """Test that historical runs never change even when new runs or corrections occur,
    and a report is always rebuildable from the frozen run.
    """
    project_id, vendor_id, plan_doc_id, vendor_doc_id = _setup_comparison_project(client)

    # 1. Execute Run 1
    run1_res = client.post(f"/api/v1/projects/{project_id}/compare")
    assert run1_res.status_code == status.HTTP_200_OK
    run1_id = run1_res.json()["run_id"]
    run1_summary = run1_res.json()["summary"]

    # 2. Vendor uploads corrected delivery file v2 (now matches 100%)
    vendor_csv_v2 = (
        "Part Number,Description,Qty,Vendor,Rack\n"
        "N9K-C93180YC-FX,Nexus 9300 48-port,4,Cisco Systems,Rack-A01\n"
        "C9300-48P,Catalyst Switch,2,Cisco Systems,Rack-A01\n"
    ).encode("utf-8")
    files_vendor_v2 = [("files", ("cisco_delivery_v2.csv", io.BytesIO(vendor_csv_v2), "text/csv"))]
    upload_v2 = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_vendor_v2,
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    v2_doc_id = upload_v2.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{v2_doc_id}/extract")

    # Approve v2 records
    rec_v2 = client.get(f"/api/v1/documents/{v2_doc_id}/records").json()["items"]
    client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": [r["id"] for r in rec_v2], "action": "approve"},
    )

    # 3. Execute Run 2
    run2_res = client.post(f"/api/v1/projects/{project_id}/compare")
    assert run2_res.status_code == status.HTTP_200_OK
    run2_id = run2_res.json()["run_id"]
    run2_summary = run2_res.json()["summary"]

    assert run2_id != run1_id
    assert run2_summary["matches_count"] == 2
    assert run2_summary["exceptions_count"] == 0

    # 4. Verify Run 1 is STILL FROZEN and unchanged
    run1_after = client.get(f"/api/v1/projects/{project_id}/runs/{run1_id}").json()
    assert run1_after["matches_count"] == run1_summary["matches_count"]
    assert run1_after["exceptions_count"] == run1_summary["exceptions_count"]
    assert run1_after["run_number"] == 1

    # Rebuild report from frozen Run 1 via GET /projects/{id}/runs/{run_id}/report
    rebuilt_run1 = client.get(f"/api/v1/projects/{project_id}/runs/{run1_id}/report").json()
    assert rebuilt_run1["run_id"] == run1_id
    assert rebuilt_run1["summary"]["matches_count"] == 1
    assert rebuilt_run1["summary"]["exceptions_count"] == 1

    # Rebuild report from Run 1 via GET /projects/{id}/compare?run_id={run1_id}
    compare_param_run1 = client.get(f"/api/v1/projects/{project_id}/compare?run_id={run1_id}").json()
    assert compare_param_run1["run_id"] == run1_id
    assert compare_param_run1["summary"]["matches_count"] == 1

    # Query results filtered by run_id
    results_run1 = client.get(f"/api/v1/projects/{project_id}/results?run_id={run1_id}").json()
    assert results_run1["total"] == 2
    assert results_run1["run_id"] == run1_id

    results_run2 = client.get(f"/api/v1/projects/{project_id}/results?run_id={run2_id}").json()
    assert results_run2["total"] == 2
    assert results_run2["run_id"] == run2_id


def test_every_export_record_points_to_its_run_id(client):
    """Test that:
    1. Export records with explicit run_id point to that run.
    2. Export records without run_id automatically point to the latest comparison run.
    3. Export records created on projects without prior runs auto-create and link to a run_id.
    """
    project_id, vendor_id, _, _ = _setup_comparison_project(client)

    # Execute a comparison run
    cmp_res = client.post(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    run_id = cmp_res.json()["run_id"]

    # 1. Export with explicit run_id
    export_bytes1 = b"Part Number,Qty\nN9K,4\n"
    res1 = client.post(
        f"/api/v1/projects/{project_id}/exports",
        files={"file": ("export_with_run.csv", io.BytesIO(export_bytes1), "text/csv")},
        data={"type": "full", "run_id": run_id, "file_name": "export_with_run.csv"},
    )
    assert res1.status_code == status.HTTP_201_CREATED
    assert res1.json()["run_id"] == run_id

    # 2. Export without run_id -> points to latest run_id automatically
    export_bytes2 = b"Part Number,Qty\nN9K,4\n"
    res2 = client.post(
        f"/api/v1/projects/{project_id}/exports",
        files={"file": ("export_auto_run.csv", io.BytesIO(export_bytes2), "text/csv")},
        data={"type": "full", "file_name": "export_auto_run.csv"},
    )
    assert res2.status_code == status.HTTP_201_CREATED
    assert res2.json()["run_id"] == run_id

    # 3. Export in a brand new project with no prior comparison runs
    new_proj = client.post("/api/v1/projects", json={"name": f"Empty Project {uuid.uuid4().hex[:6]}"}).json()
    new_proj_id = new_proj["id"]

    res_empty_proj = client.post(
        f"/api/v1/projects/{new_proj_id}/exports",
        json={"type": "full", "file_name": "baseline_export.xlsx"},
    )
    assert res_empty_proj.status_code == status.HTTP_201_CREATED
    exp_empty_data = res_empty_proj.json()
    # run_id must NOT be null and must point to a real run_id
    assert exp_empty_data["run_id"] is not None
    assert exp_empty_data["run_id"].startswith("run_")

    # Verify that run exists in database
    run_check = client.get(f"/api/v1/projects/{new_proj_id}/runs/{exp_empty_data['run_id']}")
    assert run_check.status_code == status.HTTP_200_OK
    assert run_check.json()["id"] == exp_empty_data["run_id"]
