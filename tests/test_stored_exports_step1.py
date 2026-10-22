"""Test suite for Step 1: Store every exported file with SHA-256 fingerprint, download, and audit log."""
import hashlib
import io
from fastapi import status


def test_post_export_file_multipart_and_download(client, auth_token, unauth_client):
    """Test Step 1:
    1. POST /projects/{id}/exports accepts multipart file and stores unchanged with SHA-256 fingerprint.
    2. GET /exports/{id}/file returns stored file (signed-in staff only).
    3. Audit log entry written with who, vendor, run, file name, fingerprint.
    """
    # 1. Create project and vendor
    proj_res = client.post("/api/v1/projects", json={"name": "Stored Export Test Project"})
    assert proj_res.status_code == status.HTTP_201_CREATED
    project_id = proj_res.json()["id"]

    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Test Vendor Corp"})
    vendor_id = vnd_res.json()["id"]

    # 2. Prepare sample export file (e.g. Official vendor file "Prepare for vendor")
    file_bytes = b"Part Number,Description,Qty,Rack\nSW-101,Tor Switch,2,Rack-01\n"
    expected_fingerprint = hashlib.sha256(file_bytes).hexdigest()

    # 3. POST /projects/{id}/exports (multipart upload)
    upload_res = client.post(
        f"/api/v1/projects/{project_id}/exports",
        files={"file": ("Official_Vendor_Prepare_Scope.csv", io.BytesIO(file_bytes), "text/csv")},
        data={
            "type": "vendor",
            "vendor_id": vendor_id,
            "line_count": "1",
            "file_name": "Official_Vendor_Prepare_Scope.csv",
            "run_id": "run_test_001",
        },
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    exp_data = upload_res.json()

    export_id = exp_data["id"]
    assert exp_data["project_id"] == project_id
    assert exp_data["export_type"] == "vendor"
    assert exp_data["vendor_id"] == vendor_id
    assert exp_data["line_count"] == 1
    assert exp_data["file_name"] == "Official_Vendor_Prepare_Scope.csv"
    assert exp_data["checksum_sha256"] == expected_fingerprint
    assert exp_data["fingerprint"] == expected_fingerprint
    assert exp_data["run_id"] == "run_test_001"
    assert exp_data["file_path"] is not None

    # 4. GET /exports/{id}/file (signed-in staff only)
    # A. Unauthenticated should return 401
    unauth_res = unauth_client.get(f"/api/v1/exports/{export_id}/file")
    assert unauth_res.status_code == status.HTTP_401_UNAUTHORIZED

    # B. Authenticated via client session
    download_res = client.get(f"/api/v1/exports/{export_id}/file")
    assert download_res.status_code == status.HTTP_200_OK
    assert download_res.content == file_bytes
    assert "attachment" in download_res.headers["content-disposition"]
    assert "Official_Vendor_Prepare_Scope.csv" in download_res.headers["content-disposition"]
    assert download_res.headers.get("x-checksum-sha256") == expected_fingerprint

    # C. Root endpoint alias /exports/{id}/file
    root_dl = client.get(f"/exports/{export_id}/file")
    assert root_dl.status_code == status.HTTP_200_OK
    assert root_dl.content == file_bytes

    # D. Download using ?token= query parameter
    token_dl = unauth_client.get(f"/api/v1/exports/{export_id}/file?token={auth_token}")
    assert token_dl.status_code == status.HTTP_200_OK
    assert token_dl.content == file_bytes

    # 5. Requirement 3: Check Audit Log entry (who, vendor, run, file name, fingerprint)
    audit_res = client.get(f"/api/v1/projects/{project_id}/audit")
    assert audit_res.status_code == status.HTTP_200_OK
    audit_items = audit_res.json()["items"]

    export_audit = next((a for a in audit_items if a["action"] == "export" and a["resource_id"] == export_id), None)
    assert export_audit is not None
    details = export_audit["details"]
    assert details["who"] is not None
    assert details["vendor"] == vendor_id
    assert details["run"] == "run_test_001"
    assert details["file_name"] == "Official_Vendor_Prepare_Scope.csv"
    assert details["fingerprint"] == expected_fingerprint
    assert details["checksum_sha256"] == expected_fingerprint


def test_export_record_json_backward_compatibility(client):
    """Test that existing JSON body POST /projects/{id}/exports continues to work."""
    proj_res = client.post("/api/v1/projects", json={"name": "JSON Export Test"})
    project_id = proj_res.json()["id"]

    res = client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"type": "full", "line_count": 50, "file_name": "full_report_test.xlsx"},
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["project_id"] == project_id
    assert data["line_count"] == 50
    assert data["file_name"] == "full_report_test.xlsx"
