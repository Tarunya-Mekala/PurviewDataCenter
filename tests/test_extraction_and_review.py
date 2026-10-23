import io
import pytest
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
    extract_res = client.post(f"/api/v1/documents/{doc_id}/extract?use_ai=false")
    assert extract_res.status_code == status.HTTP_200_OK
    extract_data = extract_res.json()
    assert extract_data["status"] == "extracted"
    assert extract_data["records_extracted"] == 3

    # 4. List extracted records (clean lines get read_clearly or pending_review)
    records_res = client.get(f"/api/v1/projects/{project_id}/records")
    assert records_res.status_code == status.HTTP_200_OK
    data = records_res.json()
    assert data["total"] == 3
    items = data["items"]
    assert all(r["review_status"] in ["read_clearly", "pending_review"] for r in items)

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
    assert "Cisco" in summary.get("by_manufacturer", {}) or "Cisco" in summary["by_vendor"]
    assert "Arista" in summary.get("by_manufacturer", {}) or "Arista" in summary["by_vendor"]

    # 11. Delete manual record
    del_res = client.delete(f"/api/v1/records/{manual_id}")
    assert del_res.status_code == status.HTTP_204_NO_CONTENT
    assert client.get(f"/api/v1/records/{manual_id}").status_code == status.HTTP_404_NOT_FOUND


def test_ai_extraction_reports_unavailable_engine(client, monkeypatch):
    from app.ai.llm import llm_client

    monkeypatch.setattr(llm_client, "is_available", lambda model=None: False)

    status_res = client.get("/api/v1/ai/status")
    assert status_res.status_code == status.HTTP_200_OK
    assert status_res.json()["available"] is False

    proj_res = client.post("/api/v1/projects", json={"name": "Extraction Test"})
    project_id = proj_res.json()["id"]

    sample_csv = b"Part,Qty,Desc\nN9K-9336,1,Cisco Spine Switch\n"
    files = [("files", ("spine_bom.csv", io.BytesIO(sample_csv), "text/csv"))]
    doc_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    doc_id = doc_res.json()["successful"][0]["id"]

    ai_res = client.post(f"/api/v1/documents/{doc_id}/extract-ai")
    assert ai_res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert ai_res.json()["detail"] == "AI engine is not available"

    use_ai_res = client.post(
        f"/api/v1/documents/{doc_id}/extract?use_ai=true"
    )
    assert use_ai_res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert use_ai_res.json()["detail"] == "AI engine is not available"

    extract_res = client.post(f"/api/v1/documents/{doc_id}/extract?use_ai=false")
    assert extract_res.status_code == status.HTTP_200_OK
    assert extract_res.json()["status"] == "extracted"

    st_res = client.get(f"/api/v1/documents/{doc_id}/extraction-status")
    assert st_res.status_code == status.HTTP_200_OK
    assert st_res.json()["status"] == "extracted"
    assert st_res.json()["total_records_extracted"] == 1


def test_ai_extraction_is_queued_and_marks_record_provenance(client, monkeypatch):
    from app.ai.llm import llm_client
    from app.core.config import settings

    monkeypatch.setattr(llm_client, "is_available", lambda model=None: True)

    def fake_extract_records(**kwargs):
        assert "Part Number" in kwargs["text_content"]
        second_document = "AI-DEVICE-02" in kwargs["text_content"]
        return [{
            "record_type": "bom_item",
            "part_number": "AI-DEVICE-02" if second_document else "AI-DEVICE-01",
            "description": "Router" if second_document else "Switch",
            "quantity": 1 if second_document else 2,
            "serial_number": "SER-02" if second_document else "SER-01",
            "vendor": "Example",
            "confidence_score": 0.95,
        }]

    monkeypatch.setattr(
        "app.ai.chains.extract_records_with_llm",
        fake_extract_records,
    )

    project = client.post("/api/v1/projects", json={"name": "AI extraction test"})
    project_id = project.json()["id"]
    upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[(
            "files",
            (
                "ai-source.csv",
                b"Part Number,Description,Qty,Serial No\nAI-DEVICE-01,Switch,2,SER-01\n",
                "text/csv",
            ),
        )],
    )
    document_id = upload.json()["successful"][0]["id"]

    response = client.post(f"/api/v1/documents/{document_id}/extract-ai")
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["status"] == "queued"
    assert response.json()["model_used"] == settings.LLM_MODEL

    second_upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[(
            "files",
            (
                "ai-flag.csv",
                b"Part Number,Description,Qty,Serial No\nAI-DEVICE-02,Router,1,SER-02\n",
                "text/csv",
            ),
        )],
    )
    second_document_id = second_upload.json()["successful"][0]["id"]
    ai_flag_response = client.post(
        f"/api/v1/documents/{second_document_id}/extract?use_ai=true"
    )
    assert ai_flag_response.status_code == status.HTTP_202_ACCEPTED
    assert ai_flag_response.json()["status"] == "queued"

    extraction_status = client.get(
        f"/api/v1/documents/{document_id}/extraction-status"
    )
    assert extraction_status.json()["status"] == "extracted"

    records = client.get(
        f"/api/v1/projects/{project_id}/records"
    ).json()["items"]
    assert len(records) == 2
    assert all(record["extraction_method"] == "ai" for record in records)
    assert all(record["model_used"] == settings.LLM_MODEL for record in records)
    assert all(record["review_reason"] == "not_verbatim" for record in records)
    assert all(record["vendor"] is None for record in records)
    assert all(record["confidence_score"] == 0.8 for record in records)
    assert all(
        record["field_sources"]["part_number"]["col"] == "A"
        and record["field_sources"]["part_number"]["row"] == 2
        for record in records
    )
    assert all(
        record["serial_number"] in {"SER-01", "SER-02"}
        and record["field_sources"]["serial_number"]["col"] == "D"
        for record in records
    )
    evidence = client.get(
        f"/api/v1/records/{records[0]['id']}/evidence"
    ).json()
    assert evidence["evidence"]["highlight"]["row"] == 2
    assert evidence["evidence"]["highlight"]["col"] == "A"
    assert evidence["evidence"]["highlight"]["text"] == "AI-DEVICE-01"
    assert "part_number" in evidence["evidence"]["fieldSources"]


def test_ai_value_verification_requires_exact_source_match(tmp_path):
    from openpyxl import Workbook

    from app.services.extraction_service import ExtractionService

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Inventory"
    sheet.append(["Part Number", "Quantity"])
    sheet.append(["SW-100", 2])
    path = tmp_path / "inventory.xlsx"
    workbook.save(path)

    content, segments = ExtractionService._ai_source_content(path)

    assert "SHEET: Inventory" in content
    part_number = ExtractionService._verify_ai_value("SW-100", segments)
    assert part_number is not None
    assert part_number["sheet"] == "Inventory"
    assert part_number["row"] == 2
    assert part_number["col"] == "A"
    assert part_number["text"] == "SW-100"

    assert ExtractionService._verify_ai_value("SW-100X", segments) is None
    assert ExtractionService._verify_ai_value("SW", segments) is None
    quantity = ExtractionService._verify_ai_value(2.0, segments)
    assert quantity is not None
    assert quantity["row"] == 2
    assert quantity["col"] == "B"
    assert quantity["text"] == "2"


def test_ai_prompt_and_schema_cover_semantic_equipment_fields():
    from app.ai.chains import LLM_RESPONSE_SCHEMA
    from app.ai.prompts.extraction_prompt import build_extraction_prompt

    prompt = build_extraction_prompt(
        document_content="Item Code | Manufacturer | Count",
        document_category="bom",
        source_file_name="semantic.csv",
    )
    assert '"Item Code" -> part_number' in prompt
    assert '"Manufacturer Name" -> manufacturer' in prompt
    assert '"Count" -> quantity' in prompt
    assert "Missing values must be JSON null" in prompt
    properties = LLM_RESPONSE_SCHEMA["properties"]["records"]["items"]["properties"]
    assert "serial_number" in properties
    assert "rack_id" in properties
    assert "condition_notes" in properties


def test_ai_image_inputs_preserve_image_and_pdf_visual_sources(tmp_path):
    try:
        import pymupdf as fitz
    except ImportError:
        fitz = pytest.importorskip("fitz")

    from app.services.extraction_service import ExtractionService

    image_path = tmp_path / "source.png"
    image_bytes = b"image-source-bytes"
    image_path.write_bytes(image_bytes)
    assert ExtractionService._ai_image_inputs(image_path) == [
        (image_bytes, "image/png")
    ]

    pdf_path = tmp_path / "diagram.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=200, height=100)
    page.insert_text((20, 30), "Switch to Rack A")
    pdf.save(pdf_path)
    pdf.close()

    pages = ExtractionService._ai_image_inputs(pdf_path)
    assert len(pages) == 1
    assert pages[0][0].startswith(b"\x89PNG")
    assert pages[0][1] == "image/png"


def test_llm_client_sends_visual_sources_with_prompt(monkeypatch):
    from types import SimpleNamespace

    from app.ai.llm import llm_client

    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text='{"records": []}')

    monkeypatch.setattr(
        llm_client,
        "client",
        SimpleNamespace(models=FakeModels()),
    )

    result = llm_client.generate_json(
        prompt="Extract records from the visual source.",
        image_inputs=[(b"image-bytes", "image/png")],
    )

    assert result == {"records": []}
    assert isinstance(captured["contents"], list)
    assert captured["contents"][0] == "Extract records from the visual source."
    assert captured["contents"][1].inline_data.mime_type == "image/png"
