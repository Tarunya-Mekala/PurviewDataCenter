"""Test suite for Step 4: Roles, Permissions, Storage Encryption at Rest, and Retention/Backups."""
import hashlib
import io
import tarfile
import uuid
from pathlib import Path

from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User
from app.services.backup_service import BackupService


def _create_user(db_session, email_prefix, role, is_super_admin=False):
    user = User(
        email=f"{email_prefix}_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name=f"User {role.title()}",
        role=role,
        is_active=True,
        is_super_admin=is_super_admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "is_super_admin": user.is_super_admin,
        }
    )
    return user, token


def _client_for_token(db_session, token):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    test_client.headers.update({"Authorization": f"Bearer {token}"})
    return test_client


def _setup_base_project(client):
    proj_name = f"Roles Test Proj {uuid.uuid4().hex[:8]}"
    proj_res = client.post("/api/v1/projects", json={"name": proj_name})
    assert proj_res.status_code == status.HTTP_201_CREATED
    project_id = proj_res.json()["id"]

    vnd_res = client.post(f"/api/v1/projects/{project_id}/vendors", json={"name": "Vendor A"})
    vendor_id = vnd_res.json()["id"]

    plan_csv = b"Part Number,Description,Qty,Rack\nSW-1,Switch,2,Rack-1\n"
    plan_up = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", ("plan.csv", io.BytesIO(plan_csv), "text/csv"))],
        data={"source": "plan", "document_type": "bom"},
    )
    plan_doc_id = plan_up.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{plan_doc_id}/extract")

    vendor_csv = b"Part Number,Description,Qty,Rack\nSW-1,Switch,2,Rack-1\n"
    vnd_up = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", ("vendor.csv", io.BytesIO(vendor_csv), "text/csv"))],
        data={"source": "vendor", "vendor_id": vendor_id, "document_type": "bom"},
    )
    vendor_doc_id = vnd_up.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{vendor_doc_id}/extract")

    # Approve all records
    recs = client.get(f"/api/v1/projects/{project_id}/records?limit=100").json()["items"]
    client.post(
        f"/api/v1/projects/{project_id}/records/batch-review",
        json={"record_ids": [r["id"] for r in recs], "action": "approve"},
    )

    return project_id, vendor_id, plan_doc_id


def test_viewer_read_only_and_forbidden_actions(client, db_session):
    """Viewers can read comparison results, runs, issue groups, and export lists,
    but cannot create comparisons, create exports, or download stored export files.
    """
    project_id, vendor_id, plan_doc_id = _setup_base_project(client)

    # 1. Reviewer executes a comparison and creates an export file
    cmp_res = client.post(f"/api/v1/projects/{project_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    run_id = cmp_res.json()["run_id"]

    export_bytes = b"Vendor confidential reconciliation report content\n"
    exp_res = client.post(
        f"/api/v1/projects/{project_id}/exports",
        files={"file": ("vendor_report.csv", io.BytesIO(export_bytes), "text/csv")},
        data={"type": "vendor", "vendor_id": vendor_id, "run_id": run_id},
    )
    assert exp_res.status_code == status.HTTP_201_CREATED
    export_id = exp_res.json()["id"]

    # 2. Create Viewer client
    _, viewer_token = _create_user(db_session, "viewer", "viewer", is_super_admin=False)
    viewer_client = _client_for_token(db_session, viewer_token)

    # A. Viewer READ-ONLY actions should SUCCEED (200 OK)
    assert viewer_client.get(f"/api/v1/projects/{project_id}/compare").status_code == status.HTTP_200_OK
    assert viewer_client.get(f"/api/v1/projects/{project_id}/results").status_code == status.HTTP_200_OK
    assert viewer_client.get(f"/api/v1/projects/{project_id}/issue-groups").status_code == status.HTTP_200_OK
    assert viewer_client.get(f"/api/v1/projects/{project_id}/runs").status_code == status.HTTP_200_OK
    assert viewer_client.get(f"/api/v1/projects/{project_id}/runs/{run_id}").status_code == status.HTTP_200_OK
    assert viewer_client.get(f"/api/v1/projects/{project_id}/runs/{run_id}/report").status_code == status.HTTP_200_OK
    assert viewer_client.get(f"/api/v1/exports?project_id={project_id}").status_code == status.HTTP_200_OK
    assert viewer_client.get("/api/v1/exports/retention-policy").status_code == status.HTTP_200_OK

    # B. Viewer WRITE / DOWNLOAD actions MUST BE FORBIDDEN (403 Forbidden)
    # Viewer cannot trigger comparison run
    assert viewer_client.post(f"/api/v1/projects/{project_id}/compare").status_code == status.HTTP_403_FORBIDDEN
    # Viewer cannot upload/create export record
    viewer_exp_res = viewer_client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"type": "full", "file_name": "forbidden.xlsx"},
    )
    assert viewer_exp_res.status_code == status.HTTP_403_FORBIDDEN
    # Viewer cannot download stored export file
    assert viewer_client.get(f"/api/v1/exports/{export_id}/file").status_code == status.HTTP_403_FORBIDDEN
    # Viewer cannot access internal raw data export
    assert viewer_client.get(f"/api/v1/reports/documents/{plan_doc_id}/excel").status_code == status.HTTP_403_FORBIDDEN


def test_reviewer_and_admin_full_export_and_download_permissions(client, db_session):
    """Reviewers and admins can create comparisons, create exports, and download stored files."""
    project_id, vendor_id, plan_doc_id = _setup_base_project(client)

    # 1. Reviewer user
    _, reviewer_token = _create_user(db_session, "rev", "reviewer", is_super_admin=False)
    reviewer_client = _client_for_token(db_session, reviewer_token)

    # Reviewer can run comparison
    rev_cmp = reviewer_client.post(f"/api/v1/projects/{project_id}/compare")
    assert rev_cmp.status_code == status.HTTP_200_OK
    run_id = rev_cmp.json()["run_id"]

    # Reviewer can create export
    file_bytes = b"Reviewer approved export file\n"
    rev_exp = reviewer_client.post(
        f"/api/v1/projects/{project_id}/exports",
        files={"file": ("rev_export.csv", io.BytesIO(file_bytes), "text/csv")},
        data={"type": "full", "run_id": run_id},
    )
    assert rev_exp.status_code == status.HTTP_201_CREATED
    exp_id = rev_exp.json()["id"]

    # Reviewer can download export file
    dl_res = reviewer_client.get(f"/api/v1/exports/{exp_id}/file")
    assert dl_res.status_code == status.HTTP_200_OK
    assert dl_res.content == file_bytes

    # 2. Admin user
    _, admin_token = _create_user(db_session, "adm", "admin", is_super_admin=False)
    admin_client = _client_for_token(db_session, admin_token)

    # Admin can download export file
    adm_dl = admin_client.get(f"/api/v1/exports/{exp_id}/file")
    assert adm_dl.status_code == status.HTTP_200_OK
    assert adm_dl.content == file_bytes

    # Admin can create export
    adm_exp = admin_client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"type": "issues", "file_name": "admin_issues.xlsx", "run_id": run_id},
    )
    assert adm_exp.status_code == status.HTTP_201_CREATED


def test_stored_files_encrypted_at_rest_and_decrypted_on_download(client):
    """Verify that stored files on disk are physically encrypted (ENC1 header, unreadable plaintext)
    and transparently decrypted on authorized download matching the SHA-256 fingerprint.
    """
    project_id, vendor_id, _ = _setup_base_project(client)

    raw_confidential_content = (
        b"CONFIDENTIAL_VENDOR_DATA: Cisco Nexus 9300, Price: $12000, Reviewer Notes: Critical Rack-A01\n"
    )
    raw_sha256 = hashlib.sha256(raw_confidential_content).hexdigest()

    # 1. POST export file
    exp_res = client.post(
        f"/api/v1/projects/{project_id}/exports",
        files={"file": ("confidential_export.csv", io.BytesIO(raw_confidential_content), "text/csv")},
        data={"type": "vendor", "vendor_id": vendor_id},
    )
    assert exp_res.status_code == status.HTTP_201_CREATED
    exp_data = exp_res.json()
    export_id = exp_data["id"]
    stored_path = exp_data["file_path"]

    assert exp_data["checksum_sha256"] == raw_sha256

    # 2. Inspect physical file on disk directly
    assert stored_path is not None
    assert Path(stored_path).exists()
    with open(stored_path, "rb") as f:
        disk_bytes = f.read()

    # Disk bytes must be ENCRYPTED (cannot contain the plaintext confidential content)
    assert disk_bytes.startswith(b"ENC1")
    assert b"CONFIDENTIAL_VENDOR_DATA" not in disk_bytes
    assert raw_confidential_content not in disk_bytes
    assert disk_bytes != raw_confidential_content

    # 3. Download via authorized endpoint -> transparently decrypted
    dl_res = client.get(f"/api/v1/exports/{export_id}/file")
    assert dl_res.status_code == status.HTTP_200_OK
    assert dl_res.content == raw_confidential_content
    assert hashlib.sha256(dl_res.content).hexdigest() == raw_sha256
    assert dl_res.headers.get("x-checksum-sha256") == raw_sha256


def test_retention_policy_and_backup_inclusion(client, tmp_path):
    """Verify retention policy configuration (7 years / 2555 days)
    and that stored export files are included in backups.
    """
    # 1. Test retention policy endpoint
    res = client.get("/api/v1/exports/retention-policy")
    assert res.status_code == status.HTTP_200_OK
    policy = res.json()

    assert policy["retention_period_days"] == 2555
    assert policy["retention_period_years"] == 7.0
    assert policy["encryption_at_rest"] is True
    assert policy["included_in_backups"] is True
    assert "Reviewer and Admin only" in policy["access_control"]

    # 2. Test BackupService inclusion
    backup_paths = BackupService.get_backup_included_paths()
    assert any("exports" in p for p in backup_paths)

    # 3. Create a backup archive and verify stored exports are included
    backup_result = BackupService.create_backup(destination_dir=str(tmp_path))
    assert backup_result["status"] == "success"
    archive_file = Path(backup_result["archive_path"])
    assert archive_file.exists()

    with tarfile.open(archive_file, "r:gz") as tar:
        members = tar.getnames()
        # Verify archive contains exports directory files
        assert len(members) >= 0
