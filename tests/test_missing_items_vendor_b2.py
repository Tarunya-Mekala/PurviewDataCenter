"""Test suite for Issue B2: Missing items vendor assignment logic.

Verifies:
1. One-vendor check -> that vendor is assigned to missing items.
2. Multi-vendor: supplier / PO column on plan line assigns that vendor.
3. Multi-vendor: category covered by vendor files assigns that vendor.
4. Prepare for vendor: GET /projects/{id}/results?vendor_id={id} returns missing items for that vendor.
"""
from fastapi import status


def test_b2_one_vendor_assigns_missing_items(client):
    """B2 Rule 1: One-vendor check assigns that vendor to missing items."""
    # 1. Create project & vendor
    proj_res = client.post("/api/v1/projects", json={"name": "B2 One Vendor Test"})
    project_id = proj_res.json()["id"]

    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Schneider Electric IT Corp"})
    vendor_id = vnd_res.json()["id"]

    # 2. Plan has 2 items
    plan_csv = (
        "Part Number,Description,Qty,Rack\n"
        "AR3300,Server Rack,10,Rack-A01\n"
        "AP8887,PDU Metered,4,Rack-A01\n"
    ).encode("utf-8")
    p_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", ("plan.csv", plan_csv, "text/csv"))],
        data={"source": "plan", "document_type": "bom"},
    )
    p_doc_id = p_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{p_doc_id}/extract")

    # 3. Vendor delivers only AR3300 (AP8887 is missing)
    vnd_csv = (
        "Part Number,Description,Qty,Rack\n"
        "AR3300,Server Rack,10,Rack-A01\n"
    ).encode("utf-8")
    v_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", ("delivery.csv", vnd_csv, "text/csv"))],
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    v_doc_id = v_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{v_doc_id}/extract")

    # 4. Approve all records
    records = client.get(f"/api/v1/projects/{project_id}/records?limit=100").json()["items"]
    client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": [r["id"] for r in records], "action": "approve"},
    )

    # 5. Run comparison
    cmp_res = client.get(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    items = {it["part_number"]: it for it in cmp_res.json()["items"]}

    ap8887 = items["AP8887"]
    assert ap8887["cause"] == "Missing item"
    assert ap8887["vendor_id"] == vendor_id
    assert ap8887["vendor_name"] == "Schneider Electric IT Corp"

    # 6. Check results for vendor preview
    res_vnd = client.get(f"/api/v1/projects/{project_id}/results?vendor_id={vendor_id}")
    assert res_vnd.status_code == status.HTTP_200_OK
    vnd_items = {it["part_number"]: it for it in res_vnd.json()["items"]}
    assert "AP8887" in vnd_items


def test_b2_multivendor_supplier_and_category_coverage(client):
    """B2 Rules 2 & 3: Supplier/PO column and Category coverage in multi-vendor project."""
    # 1. Create project
    proj_res = client.post("/api/v1/projects", json={"name": "B2 Multi Vendor Test"})
    project_id = proj_res.json()["id"]

    # 2. Create 2 Vendors: Schneider (Power/Racks) and Vertiv (Cooling)
    vnd_s = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Schneider Electric"}).json()["id"]
    vnd_v = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Vertiv Critical Infrastructure"}).json()["id"]

    # 3. Plan has:
    # - AR3300: Rack, Supplier: Schneider Electric
    # - CRAC-01: Cooling unit, no supplier specified, but category is Cooling
    # - AP8868: Power/PDU, PO column: PO-SCHNEIDER-101
    plan_csv = (
        "Part Number,Description,Category,Qty,Rack,Supplier,PO\n"
        "AR3300,Server Rack,Rack,5,Rack-01,Schneider Electric,\n"
        "CRAC-01,In-Row Cooling 35kW,Cooling,2,Rack-01,,\n"
        "AP8868,Rack PDU,Power,4,Rack-01,,PO-SCHNEIDER-101\n"
    ).encode("utf-8")
    p_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", ("plan.csv", plan_csv, "text/csv"))],
        data={"source": "plan", "document_type": "bom"},
    )
    p_doc_id = p_upload.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{p_doc_id}/extract")

    # 4. Vendor deliveries:
    # - Schneider delivers AR3300 (AP8868 is missing)
    s_csv = "Part Number,Description,Category,Qty,Rack\nAR3300,Server Rack,Rack,5,Rack-01\n".encode("utf-8")
    s_doc_id = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", ("schneider_del.csv", s_csv, "text/csv"))],
        data={"source": "vendor", "vendor_id": vnd_s, "document_type": "bom"},
    ).json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{s_doc_id}/extract")

    # - Vertiv uploaded a cooling file with category Cooling, but for a different unit CRAC-02 (CRAC-01 is missing)
    v_csv = "Part Number,Description,Category,Qty,Rack\nCRAC-02,Spare In-Row Cooling,Cooling,1,Rack-01\n".encode("utf-8")
    v_doc_id = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", ("vertiv_cooling.csv", v_csv, "text/csv"))],
        data={"source": "vendor", "vendor_id": vnd_v, "document_type": "bom"},
    ).json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{v_doc_id}/extract")

    # 5. Approve all records
    records = client.get(f"/api/v1/projects/{project_id}/records?limit=100").json()["items"]
    client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": [r["id"] for r in records], "action": "approve"},
    )

    # 6. Compare
    cmp_res = client.get(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    items = {it["part_number"]: it for it in cmp_res.json()["items"]}

    # AP8868 was missing; matched Schneider via PO column ("PO-SCHNEIDER-101")
    ap8868 = items["AP8868"]
    assert ap8868["cause"] == "Missing item"
    assert ap8868["vendor_id"] == vnd_s

    # CRAC-01 was missing; had no supplier, but category "Cooling" matches Vertiv's uploaded files
    crac01 = items["CRAC-01"]
    assert crac01["cause"] == "Missing item"
    assert crac01["vendor_id"] == vnd_v
    assert crac01["vendor_name"] == "Vertiv Critical Infrastructure"

    # 7. Verify Results -> Prepare for vendor:
    # Vertiv preview lists CRAC-01
    vertiv_results = client.get(f"/api/v1/projects/{project_id}/results?vendor_id={vnd_v}").json()["items"]
    assert any(it["part_number"] == "CRAC-01" for it in vertiv_results)

    # Schneider preview lists AP8868
    schneider_results = client.get(f"/api/v1/projects/{project_id}/results?vendor_id={vnd_s}").json()["items"]
    assert any(it["part_number"] == "AP8868" for it in schneider_results)
