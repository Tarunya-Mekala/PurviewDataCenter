import io
from fastapi import status


def test_create_and_list_project(client):
    # 1. Create a project
    res = client.post(
        "/api/v1/projects",
        json={"name": "Data Center Alpha", "description": "Phase 1 hardware BOM and cable schedules"},
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["name"] == "Data Center Alpha"
    assert "id" in data
    project_id = data["id"]
    assert project_id.startswith("proj_")

    # 2. List projects
    res = client.get("/api/v1/projects")
    assert res.status_code == status.HTTP_200_OK
    list_data = res.json()
    assert list_data["total"] >= 1
    assert any(p["id"] == project_id for p in list_data["items"])

    # 3. Get single project
    res = client.get(f"/api/v1/projects/{project_id}")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["name"] == "Data Center Alpha"


def test_upload_documents(client):
    # Create project first
    res = client.post(
        "/api/v1/projects",
        json={"name": "Project Beta", "description": "Test upload"},
    )
    assert res.status_code == status.HTTP_201_CREATED
    project_id = res.json()["id"]

    # Prepare dummy files
    bom_content = b"Item,Part Number,Qty,Description\n1,SFP-10G-SR,20,10G Transceiver\n"
    rack_content = b"%PDF-1.4 dummy pdf for rack elevation..."

    files = [
        ("files", ("dc_hardware_bom.csv", io.BytesIO(bom_content), "text/csv")),
        ("files", ("rack_layout_cabinet_a1.pdf", io.BytesIO(rack_content), "application/pdf")),
    ]

    # Upload files without explicit document_type to test auto-detection via main documents endpoint
    res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=files,
    )
    assert res.status_code == status.HTTP_201_CREATED
    upload_res = res.json()
    assert len(upload_res["successful"]) == 2
    assert len(upload_res["failed"]) == 0

    doc_bom = next(d for d in upload_res["successful"] if "bom" in d["filename"])
    doc_rack = next(d for d in upload_res["successful"] if "rack" in d["filename"])

    # Auto-detection checks
    assert doc_bom["id"].startswith("doc_")
    assert doc_bom["document_type"] == "bom"
    assert doc_bom["status"] == "pending"
    assert doc_bom["checksum_sha256"] is not None

    assert doc_rack["id"].startswith("doc_")
    assert doc_rack["document_type"] == "rack_layout"
    assert doc_rack["status"] == "pending"


def test_upload_with_explicit_type(client):
    res = client.post("/api/v1/projects", json={"name": "Project Gamma"})
    project_id = res.json()["id"]

    p2p_content = b"Source,Dest,Port,CableType\nSwitchA,SwitchB,eth1/1,DAC\n"
    files = [("files", ("network_connections.csv", io.BytesIO(p2p_content), "text/csv"))]

    res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        data={"document_type": "p2p"},
        files=files,
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert len(data["successful"]) == 1
    assert data["successful"][0]["document_type"] == "p2p"


def test_unsupported_file_extension(client):
    res = client.post("/api/v1/projects", json={"name": "Project Delta"})
    project_id = res.json()["id"]

    bad_files = [("files", ("executable.exe", io.BytesIO(b"binary"), "application/octet-stream"))]
    res = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=bad_files,
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert len(data["successful"]) == 0
    assert len(data["failed"]) == 1
    assert "Unsupported file type" in data["failed"][0]["reason"]


def test_list_and_filter_documents(client):
    res = client.post("/api/v1/projects", json={"name": "Project Filter Test"})
    project_id = res.json()["id"]

    # Upload 2 files
    files = [
        ("files", ("power_distribution_feed.csv", io.BytesIO(b"feed,amps\n1,30A"), "text/csv")),
        ("files", ("cabling_patch_schedule.csv", io.BytesIO(b"cable,type\n1,cat6"), "text/csv")),
    ]
    client.post(f"/api/v1/projects/{project_id}/documents", files=files)

    # Filter by document_type=power
    res = client.get(f"/api/v1/projects/{project_id}/documents?document_type=power")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["document_type"] == "power"

    # Filter by document_type=cable
    res = client.get(f"/api/v1/projects/{project_id}/documents?document_type=cable")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["document_type"] == "cable"


def test_document_download_and_lifecycle(client):
    res = client.post("/api/v1/projects", json={"name": "Project Lifecycle"})
    project_id = res.json()["id"]

    sample_content = b"Server,Slot,Model\nServer01,U1,Dell-R750\n"
    files = [("files", ("rack_bom_sample.csv", io.BytesIO(sample_content), "text/csv"))]
    upload_res = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    doc_id = upload_res.json()["successful"][0]["id"]

    # 1. Get document details
    res = client.get(f"/api/v1/documents/{doc_id}")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["filename"] == "rack_bom_sample.csv"

    # 2. Download document
    res = client.get(f"/api/v1/documents/{doc_id}/download")
    assert res.status_code == status.HTTP_200_OK
    assert res.content == sample_content

    # 3. Update document metadata / reclassify
    res = client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"document_type": "rack_layout"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["document_type"] == "rack_layout"

    # 4. Reprocess document
    res = client.post(f"/api/v1/documents/{doc_id}/reprocess")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "pending"

    # 5. Delete document
    res = client.delete(f"/api/v1/documents/{doc_id}")
    assert res.status_code == status.HTTP_204_NO_CONTENT

    # 6. Verify deleted
    res = client.get(f"/api/v1/documents/{doc_id}")
    assert res.status_code == status.HTTP_404_NOT_FOUND
