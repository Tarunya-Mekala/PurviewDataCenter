"""Test suite for the Comparison API (Plan vs Vendor Reconciliation)."""
from fastapi import status


def test_comparison_api_match_discrepancy_exception(client):
    """Test full comparison API workflow returning MATCH, DISCREPANCY, and EXCEPTION."""
    # 1. Create a project
    proj_res = client.post("/api/v1/projects", json={"name": "Reconciliation Test"})
    project_id = proj_res.json()["id"]

    # 2. Create Vendor
    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Primary Vendor"})
    vendor_id = vnd_res.json()["id"]

    # 3. Upload Plan document
    plan_csv = (
        "Part Number,Description,Qty,Rack\n"
        "N9K-C93180YC-FX,Nexus Switch,2,Rack-A01\n"
        "PowerEdge-R750,Dell Server,4,Rack-A01\n"
        "AP8887,PDU,2,Rack-A01\n"
    ).encode("utf-8")
    files_plan = [("files", ("plan.csv", plan_csv, "text/csv"))]
    plan_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_plan,
        data={"source": "plan", "document_type": "bom"},
    )
    plan_doc_id = plan_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{plan_doc_id}/extract")

    # 4. Upload Vendor delivery document
    # Vendor delivers:
    # - N9K-C93180YC-FX: 2 units (MATCH)
    # - PowerEdge-R750: 3 units (DISCREPANCY: shortage by 1)
    # - UNEXPECTED-SRV: 1 unit (EXCEPTION: unexpected item not in plan)
    # - Note: AP8887 is missing in delivery (EXCEPTION: planned but not delivered)
    vendor_csv = (
        "Part Number,Description,Qty,Rack\n"
        "N9K-C93180YC-FX,Nexus Switch,2,Rack-A01\n"
        "PowerEdge-R750,Dell Server,3,Rack-A01\n"
        "UNEXPECTED-SRV,Extra Server,1,Rack-A01\n"
    ).encode("utf-8")
    files_vendor = [("files", ("delivery.csv", vendor_csv, "text/csv"))]
    vendor_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_vendor,
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    vendor_doc_id = vendor_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{vendor_doc_id}/extract")

    # 5. Approve all records in project for comparison
    records = client.get(f"/api/v1/projects/{project_id}/records?limit=100").json()["items"]
    record_ids = [r["id"] for r in records]
    client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": record_ids, "action": "approve", "review_notes": "Batch approving for comparison"},
    )

    # 6. Run Comparison API
    cmp_res = client.get(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    cmp_data = cmp_res.json()

    summary = cmp_data["summary"]
    assert summary["matches_count"] == 1
    assert summary["discrepancies_count"] == 0
    assert summary["exceptions_count"] == 3

    items = {item["part_number"]: item for item in cmp_data["items"]}

    # Verify MATCH item
    nexus = items["N9K-C93180YC-FX"]
    assert nexus["status"] == "MATCH"
    assert nexus["expected_quantity"] == 2.0
    assert nexus["found_quantity"] == 2.0
    assert "Accept / Verified" in nexus["action"]

    # Verify Quantity Difference item (Exception per Problem 27 rule)
    dell = items["PowerEdge-R750"]
    assert dell["status"] == "EXCEPTION"
    assert dell["expected_quantity"] == 4.0
    assert dell["found_quantity"] == 3.0
    assert dell["difference"] == -1.0
    assert "shortage" in dell["details"].lower()

    # Verify EXCEPTION (planned but not delivered)
    ap8887 = items["AP8887"]
    assert ap8887["status"] == "EXCEPTION"
    assert ap8887["expected_quantity"] == 2.0
    assert ap8887["found_quantity"] == 0.0

    # Verify EXCEPTION (unexpected delivery)
    unexp = items["UNEXPECTED-SRV"]
    assert unexp["status"] == "EXCEPTION"
    assert unexp["expected_quantity"] == 0.0
    assert unexp["found_quantity"] == 1.0

    # 7. Test comparison with rack filter
    rack_res = client.get(f"/api/v1/projects/{project_id}/compare?rack=Rack-A01")
    assert rack_res.status_code == status.HTTP_200_OK
    assert len(rack_res.json()["items"]) == 4

    rack_empty = client.get(f"/api/v1/projects/{project_id}/compare?rack=Rack-Z99")
    assert rack_empty.status_code == status.HTTP_200_OK
    assert len(rack_empty.json()["items"]) == 0


def test_comparison_doa_condition_failure_discrepancy(client):
    """Test that a delivered unit with condition='failed' flags as DISCREPANCY requiring RMA."""
    proj_res = client.post("/api/v1/projects", json={"name": "DOA Comparison Test"})
    project_id = proj_res.json()["id"]

    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Sharon AI"})
    vendor_id = vnd_res.json()["id"]

    # Plan: 1 unit of HF6100-32D in Rack-B01
    plan_csv = "Part Number,Description,Qty,Rack\nHF6100-32D,Storage Leaf Switch,1,Rack-B01\n".encode("utf-8")
    files_plan = [("files", ("plan.csv", plan_csv, "text/csv"))]
    plan_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_plan,
        data={"source": "plan", "document_type": "bom"},
    )
    plan_doc_id = plan_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{plan_doc_id}/extract")

    # Delivery: 1 unit of HF6100-32D delivered, but failed test (DOA)
    vendor_csv = "Part Number,Description,Qty,Rack,DOA - FANS,NOTES\nHF6100-32D,Storage Leaf Switch,1,Rack-B01,FAIL,INCORRECT FANS\n".encode("utf-8")
    files_vendor = [("files", ("delivery.csv", vendor_csv, "text/csv"))]
    vendor_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files_vendor,
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    vendor_doc_id = vendor_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{vendor_doc_id}/extract")

    # Approve both records
    records = client.get(f"/api/v1/projects/{project_id}/records").json()["items"]
    record_ids = [r["id"] for r in records]
    client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": record_ids, "action": "approve", "review_notes": "Approving for comparison"},
    )

    # Compare
    cmp_res = client.get(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    cmp_data = cmp_res.json()
    assert cmp_data["summary"]["discrepancies_count"] == 1
    assert cmp_data["summary"]["matches_count"] == 0

    item = cmp_data["items"][0]
    assert item["status"] == "DISCREPANCY"
    assert item["condition_status"] == "failed"
    assert "INCORRECT FANS" in item["condition_notes"]
    assert "Initiate RMA" in item["action"]

