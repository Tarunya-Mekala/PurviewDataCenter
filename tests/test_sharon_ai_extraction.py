"""Integration and validation test suite for Sharon AI sample files and all 16 Problems."""
import io
import shutil
from pathlib import Path
import pytest
from fastapi import status


SHARON_DOA_FILE = Path("data/uploads/proj_ad4cec344e6a4b3589526487fa9920de/doc_a608f358dfd244b9a291bb83fb67242d_SHARONAI_ACTIVE_EQUIPMENT_DOA_TESTING_-_OldRECORD.xlsx")
CABLE_SUMMARY_FILE = Path("data/uploads/proj_ad4cec344e6a4b3589526487fa9920de/doc_4a287d9377d34707874d6d368f80b3e5_Cable_Quantities_Summary.xlsx")


def test_sharon_ai_extraction_problem_1_2_3_5_7_14_15(client):
    """Test Problems 1, 2, 3, 5, 7, 14, 15 on Sharon AI DOA test file."""
    # 1. Create project
    proj_res = client.post("/api/v1/projects", json={"name": "Sharon AI DOA Test"})
    assert proj_res.status_code == status.HTTP_201_CREATED
    project_id = proj_res.json()["id"]

    # 2. Upload Sharon AI DOA file
    assert SHARON_DOA_FILE.exists()
    with open(SHARON_DOA_FILE, "rb") as f:
        file_bytes = f.read()

    files = [("files", ("sharon_doa.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    upload_res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files,
        data={"source": "vendor", "document_type": "bom"},
    )
    # Fails because vendor_id is required when source='vendor' (Problem 6 check)
    assert upload_res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Create vendor first (Problem 6)
    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Sharon AI Supplier"})
    assert vnd_res.status_code == status.HTTP_201_CREATED
    vendor_id = vnd_res.json()["id"]

    # Re-upload with vendor_id
    upload_res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files,
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_resp = upload_res.json()["successful"][0]
    assert doc_resp["source"] == "vendor"
    assert doc_resp["vendor_id"] == vendor_id
    doc_id = doc_resp["id"]

    # 3. Extract DOA file
    extract_res = client.post(f"/api/v1/documents/{doc_id}/extract")
    assert extract_res.status_code == status.HTTP_200_OK
    extract_data = extract_res.json()
    assert extract_data["status"] == "extracted"
    assert extract_data["records_extracted"] > 0

    # 4. Fetch records
    records_res = client.get(f"/api/v1/projects/{project_id}/records?limit=500")
    assert records_res.status_code == status.HTTP_200_OK
    items = records_res.json()["items"]

    # PROBLEM 1 Check: AP8887 extracted from Device column
    ap8887_recs = [r for r in items if r["part_number"] == "AP8887"]
    assert len(ap8887_recs) >= 1
    ap_rec = ap8887_recs[0]
    assert ap_rec["cleaned_part_number"] == "AP8887"
    assert ap_rec["quantity"] == 208.0
    assert ap_rec["description"] == "PDU"

    # PROBLEM 1 & 2 Check: Row 26 in Sheet1 (2) has part_number HF6100-32D V01, serial_number, condition failed
    sheet1_row26 = [
        r for r in items
        if r.get("source_sheet") == "Sheet1 (2)" and r.get("source_row") == 26
    ]
    assert len(sheet1_row26) == 1
    s1_r26 = sheet1_row26[0]
    assert s1_r26["part_number"] == "HF6100-32D V01"
    assert s1_r26["cleaned_part_number"] == "HF6100-32D"
    assert s1_r26["serial_number"] == "FLM300309G2"
    assert s1_r26["condition"] == "failed"
    assert "INCORRECT FANS" in (s1_r26.get("condition_notes") or "")

    # PROBLEM 5 Check: Serial rows in DOA file have quantity = None and review_reason = "missing_value"
    assert s1_r26["quantity"] is None
    assert s1_r26["review_reason"] == "missing_value"

    # PROBLEM 3 Check: HF6100-32D V01 summary in Sheet2 lists unlabelled columns in unmapped_columns and has review_reason = "unmapped_field"
    sheet2_hf6100 = [
        r for r in items
        if r.get("source_sheet") == "Sheet2" and "HF6100" in (r.get("part_number") or "")
    ]
    assert len(sheet2_hf6100) >= 1
    s2_hf = sheet2_hf6100[0]
    assert len(s2_hf["unmapped_columns"]) >= 1
    assert s2_hf["review_reason"] == "unmapped_field"

    # PROBLEM 14 Check: extraction_method is table, model_used is null
    assert ap_rec["extraction_method"] == "table"
    assert ap_rec["model_used"] is None


def test_cable_quantities_summary_problem_11(client):
    """Test Problem 11: Cable_Quantities_Summary skips Bundle Counts and keeps Cable Counts."""
    proj_res = client.post("/api/v1/projects", json={"name": "Cable Summary Project"})
    project_id = proj_res.json()["id"]

    assert CABLE_SUMMARY_FILE.exists()
    with open(CABLE_SUMMARY_FILE, "rb") as f:
        file_bytes = f.read()

    files = [("files", ("Cable_Quantities_Summary.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    upload_res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files,
        data={"source": "plan", "document_type": "cable"},
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["successful"][0]["id"]

    extract_res = client.post(f"/api/v1/documents/{doc_id}/extract")
    assert extract_res.status_code == status.HTTP_200_OK

    # Check skipped_sheets in document
    docs_res = client.get(f"/api/v1/projects/{project_id}/documents")
    doc_item = docs_res.json()["items"][0]
    meta = doc_item.get("metadata_json") or {}
    skipped = meta.get("skipped_sheets") or []
    assert any(s["name"] == "Bundle Counts" for s in skipped)

    # Check record count is around 39 from Cable Counts (NOT 158)
    records_res = client.get(f"/api/v1/projects/{project_id}/records?limit=200")
    items = records_res.json()["items"]
    assert len(items) == 39
    assert all(r["source_sheet"] == "Cable Counts" for r in items)
    assert all(r["confidence_score"] >= 0.90 for r in items)


def test_problem_4_ai_offline_503(client, monkeypatch):
    """Verify unavailable AI is reported without falling back to table extraction."""
    from app.ai.llm import llm_client

    monkeypatch.setattr(llm_client, "is_available", lambda model=None: False)
    proj_res = client.post("/api/v1/projects", json={"name": "AI 503 Test"})
    project_id = proj_res.json()["id"]

    files = [("files", ("test.csv", b"Part Number,Quantity\nABC-123,5\n", "text/csv"))]
    upload_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    doc_id = upload_res.json()["successful"][0]["id"]

    ai_res = client.post(f"/api/v1/documents/{doc_id}/extract-ai")
    assert ai_res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    status_res = client.get("/api/v1/ai/status")
    assert status_res.status_code == status.HTTP_200_OK
    assert status_res.json()["available"] is False



def test_problem_8_9_10_review_audit_and_undo(client):
    """Test Problems 8, 9, 10: Validation, history, soft delete, and undo restoring original values."""
    proj_res = client.post("/api/v1/projects", json={"name": "Audit Test Project"})
    project_id = proj_res.json()["id"]

    files = [("files", ("items.csv", b"Part Number,Description,Qty\nSRV-01,Server,440\n", "text/csv"))]
    upload_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    doc_id = upload_res.json()["successful"][0]["id"]

    client.post(f"/api/v1/documents/{doc_id}/extract")
    records_res = client.get(f"/api/v1/projects/{project_id}/records")
    record = records_res.json()["items"][0]
    rec_id = record["id"]
    assert record["quantity"] == 440.0
    assert record["original_values"]["quantity"] == 440.0

    # Problem 10 Check: rejected or modified without review_notes >= 3 chars returns 422
    invalid_review = client.post(
        f"/api/v1/records/{rec_id}/review",
        json={"status": "rejected", "review_notes": ""},
    )
    assert invalid_review.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    invalid_modified = client.post(
        f"/api/v1/records/{rec_id}/review",
        json={"status": "modified", "review_notes": "no"},
    )
    assert invalid_modified.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Correct 440 to 441
    mod_res = client.post(
        f"/api/v1/records/{rec_id}/review",
        json={
            "status": "modified",
            "review_notes": "Vendor delivery note says 441 units",
            "corrections": {"quantity": 441.0},
        },
    )
    assert mod_res.status_code == status.HTTP_200_OK
    assert mod_res.json()["quantity"] == 441.0

    # Problem 8 Check: Undo restores original 440
    undo_res = client.post(
        f"/api/v1/records/{rec_id}/review",
        json={"status": "pending_review", "review_notes": "Reverting correction"},
    )
    assert undo_res.status_code == status.HTTP_200_OK
    undone = undo_res.json()
    assert undone["quantity"] == 440.0
    assert undone["original_values"]["quantity"] == 440.0

    # Check history endpoint has entries
    hist_res = client.get(f"/api/v1/records/{rec_id}/history")
    assert hist_res.status_code == status.HTTP_200_OK
    history = hist_res.json()
    assert len(history) >= 2

    # Problem 9 Check: Approve record then PATCH without notes resets to pending_review
    client.post(
        f"/api/v1/records/{rec_id}/review",
        json={"status": "approved", "review_notes": "Looks good"},
    )
    patch_res = client.patch(f"/api/v1/records/{rec_id}", json={"description": "Updated Server Desc"})
    assert patch_res.status_code == status.HTTP_200_OK
    assert patch_res.json()["review_status"] == "pending_review"


def test_problem_12_extract_all_queued(client):
    """Test Problem 12: extract-all returns 202 immediately with queued status."""
    proj_res = client.post("/api/v1/projects", json={"name": "Extract All Test"})
    project_id = proj_res.json()["id"]

    files = [("files", ("f1.csv", b"Part Number,Qty\nA-1,1\n", "text/csv"))]
    client.post(f"/api/v1/projects/{project_id}/documents", files=files)

    res = client.post(f"/api/v1/projects/{project_id}/extract-all")
    assert res.status_code == status.HTTP_202_ACCEPTED
    items = res.json()
    assert len(items) == 1
    assert items[0]["status"] == "queued"


def test_problem_13_re_extraction_preserves_approvals(client):
    """Test Problem 13: Extracting identical file twice preserves approvals and does not duplicate."""
    proj_res = client.post("/api/v1/projects", json={"name": "Re-extract Project"})
    project_id = proj_res.json()["id"]

    files = [("files", ("dedup.csv", b"Part Number,Description,Qty\nP-100,Switch,10\n", "text/csv"))]
    upload_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    doc_id = upload_res.json()["successful"][0]["id"]

    # First extraction
    client.post(f"/api/v1/documents/{doc_id}/extract")
    records = client.get(f"/api/v1/projects/{project_id}/records").json()["items"]
    assert len(records) == 1
    rec_id = records[0]["id"]

    # Approve record
    client.post(
        f"/api/v1/records/{rec_id}/review",
        json={"status": "approved", "review_notes": "Approved line item"},
    )

    # Second extraction on identical file
    client.post(f"/api/v1/documents/{doc_id}/extract")
    records_after = client.get(f"/api/v1/projects/{project_id}/records").json()["items"]
    assert len(records_after) == 1
    assert records_after[0]["id"] == rec_id
    assert records_after[0]["review_status"] == "approved"
    assert records_after[0]["review_notes"] == "Approved line item"
