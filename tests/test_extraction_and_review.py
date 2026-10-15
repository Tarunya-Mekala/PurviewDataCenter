import io
from fastapi import status


def test_extraction_and_human_review_flow(client):
    # 1. Create a project
    res = client.post("/api/v1/projects", json={"name": "Project Review Test", "description": "Testing extraction & review"})
    assert res.status_code == status.HTTP_201_CREATED
    project_id = res.json()["id"]

    # 2. Upload a hardware BOM CSV file
    bom_csv = (
        "Part Number,Description,Qty,Vendor,Rack\n"
        "N9K-C93180YC-FX,Nexus 9300 48-port 25G Switch,2,Cisco,Rack-A01\n"
        "DCS-7050TX3-48C8,Arista 48x10G 8x100G Switch,4,Arista,Rack-A02\n"
        "PowerEdge-R750,Dell Dual Xeon Server 64GB,8,Dell,Rack-B01\n"
    ).encode("utf-8")

    files = [("files", ("datacenter_bom.csv", io.BytesIO(bom_csv), "text/csv"))]
    upload_res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files,
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["successful"][0]["id"]

    # 3. Trigger extraction on the document
    extract_res = client.post(f"/api/v1/documents/{doc_id}/extract")
    assert extract_res.status_code == status.HTTP_200_OK
    extract_data = extract_res.json()
    assert extract_data["status"] == "extracted"
    assert extract_data["records_extracted"] == 3

    # 4. List extracted records (initially all pending_review)
    records_res = client.get(f"/api/v1/projects/{project_id}/records")
    assert records_res.status_code == status.HTTP_200_OK
    data = records_res.json()
    assert data["total"] == 3
    items = data["items"]
    assert all(r["review_status"] == "pending_review" for r in items)

    # Check parsed fields
    cisco_rec = next(r for r in items if "93180" in r["part_number"])
    assert cisco_rec["vendor"] == "Cisco"
    assert cisco_rec["quantity"] == 2.0
    assert cisco_rec["location"] == "Rack-A01"
    assert cisco_rec["confidence_score"] >= 0.8

    # 5. Review single record: Approve with feedback
    cisco_id = cisco_rec["id"]
    review_res = client.post(
        f"/api/v1/records/{cisco_id}/review",
        json={"status": "approved", "review_notes": "Verified against site engineering spec"},
    )
    assert review_res.status_code == status.HTTP_200_OK
    reviewed_item = review_res.json()
    assert reviewed_item["review_status"] == "approved"
    assert reviewed_item["review_notes"] == "Verified against site engineering spec"
    assert reviewed_item["reviewed_by"] is not None

    # 6. Edit/Modify another record
    arista_rec = next(r for r in items if "7050" in r["part_number"])
    arista_id = arista_rec["id"]
    patch_res = client.patch(
        f"/api/v1/records/{arista_id}",
        json={"quantity": 6.0, "review_notes": "Increased count based on leaf spine topology"},
    )
    assert patch_res.status_code == status.HTTP_200_OK
    patched_item = patch_res.json()
    assert patched_item["quantity"] == 6.0
    assert patched_item["review_status"] == "modified"

    # 7. Manually add a missing record
    manual_res = client.post(
        f"/api/v1/documents/{doc_id}/records",
        json={
            "record_type": "cable_item",
            "part_number": "CAB-Q-Q-100G-3M",
            "description": "100G QSFP28 to QSFP28 DAC Cable 3m",
            "quantity": 16.0,
            "vendor": "Arista",
            "source_device": "Spine-01",
            "target_device": "Leaf-01",
            "review_notes": "Manually added cross-rack interconnect cable",
        },
    )
    assert manual_res.status_code == status.HTTP_201_CREATED
    manual_item = manual_res.json()
    assert manual_item["is_manually_added"] is True
    assert manual_item["review_status"] == "approved"
    manual_id = manual_item["id"]

    # 8. Filter records by review_status
    approved_res = client.get(f"/api/v1/projects/{project_id}/records?review_status=approved")
    assert approved_res.status_code == status.HTTP_200_OK
    assert approved_res.json()["total"] == 2  # cisco approved + manually added approved

    # 9. Batch review: Reject the dell server record
    dell_rec = next(r for r in items if "R750" in r["part_number"])
    batch_res = client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={
            "record_ids": [dell_rec["id"]],
            "action": "reject",
            "review_notes": "Compute hardware deferred to Phase 2",
        },
    )
    assert batch_res.status_code == status.HTTP_200_OK
    assert batch_res.json()["records_reviewed"] == 1

    # 10. Check Review Progress Summary Metrics
    summary_res = client.get(f"/api/v1/projects/{project_id}/review-summary")
    assert summary_res.status_code == status.HTTP_200_OK
    summary = summary_res.json()
    assert summary["total_records"] == 4  # 3 extracted + 1 manual
    assert summary["pending_review_count"] == 0  # all 4 have been reviewed (2 approved, 1 modified, 1 rejected)
    assert summary["approved_count"] == 2
    assert summary["modified_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["completion_percentage"] == 100.0
    assert "Cisco" in summary["by_vendor"]
    assert "Arista" in summary["by_vendor"]

    # 11. Delete manual record
    del_res = client.delete(f"/api/v1/records/{manual_id}")
    assert del_res.status_code == status.HTTP_204_NO_CONTENT
    assert client.get(f"/api/v1/records/{manual_id}").status_code == status.HTTP_404_NOT_FOUND


def test_ai_status_and_extraction_endpoints(client, monkeypatch):
    # 1. Test AI status endpoint
    status_res = client.get("/api/v1/ai/status")
    assert status_res.status_code == status.HTTP_200_OK
    data = status_res.json()
    assert "configured_model" in data
    assert "ollama_online" in data
    assert "recommended_model" in data

    # 2. Create project & document for AI extraction
    proj_res = client.post("/api/v1/projects", json={"name": "AI Extraction Test"})
    project_id = proj_res.json()["id"]

    sample_csv = b"Part,Qty,Desc\nN9K-9336,1,Cisco Spine Switch\n"
    files = [("files", ("spine_bom.csv", io.BytesIO(sample_csv), "text/csv"))]
    doc_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    doc_id = doc_res.json()["successful"][0]["id"]

    # 3. Test check extraction status (initially pending)
    st_res = client.get(f"/api/v1/documents/{doc_id}/extraction-status")
    assert st_res.status_code == status.HTTP_200_OK
    assert st_res.json()["status"] == "pending"
    assert st_res.json()["total_records_extracted"] == 0

    # 4. Mock Ollama response to test AI extraction pipeline without requiring running local Ollama
    from app.ai.llm import ollama_client

    def mock_generate_json(prompt, system=None, model=None, timeout_seconds=120.0):
        return {
            "records": [
                {
                    "part_number": "N9K-9336C-FX2",
                    "description": "Nexus 9336C-FX2 36-Port 100G Switch",
                    "quantity": 2.0,
                    "unit": "pcs",
                    "vendor": "Cisco",
                    "category": "Switch",
                    "confidence_score": 0.98,
                }
            ]
        }

    monkeypatch.setattr(ollama_client, "generate_json", mock_generate_json)

    # 5. Trigger dedicated AI extraction endpoint
    ai_res = client.post(
        f"/api/v1/documents/{doc_id}/extract-ai",
        json={"model": "qwen2.5:27b"},
    )
    assert ai_res.status_code == status.HTTP_200_OK
    ai_data = ai_res.json()
    assert ai_data["status"] == "extracted"
    assert ai_data["records_extracted"] == 1
    assert "qwen2.5:27b" in (ai_data.get("model_used") or "")

    # 6. Check extraction status reflects extracted records
    st_res = client.get(f"/api/v1/documents/{doc_id}/extraction-status")
    assert st_res.status_code == status.HTTP_200_OK
    assert st_res.json()["status"] == "extracted"
    assert st_res.json()["total_records_extracted"] == 1
    assert st_res.json()["review_status_counts"]["pending_review"] == 1

    # 7. Test direct raw snippet AI extraction
    snippet_res = client.post(
        "/api/v1/extract/ai-snippet",
        json={
            "text": "1x DCS-7280SR Arista 100G router, 4x SFP-25G-SR optics",
            "document_type": "bom",
            "model": "qwen2.5:27b",
        },
    )
    assert snippet_res.status_code == status.HTTP_200_OK
    snippet_data = snippet_res.json()
    assert len(snippet_data) >= 1
    assert snippet_data[0]["vendor"] == "Cisco"

