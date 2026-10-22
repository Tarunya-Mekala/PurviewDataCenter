"""Comprehensive endpoint verification test suite.
Validates that every single API endpoint across all routers is functioning properly
and complies with required request/response schemas.
"""
import io
import pytest
from fastapi import status


from app.core.config import settings


def test_root_and_health_endpoints(client):
    """Test root and healthcheck endpoints."""
    res_root = client.get("/")
    assert res_root.status_code == status.HTTP_200_OK
    assert "status" in res_root.json()

    res_health = client.get("/health")
    assert res_health.status_code == status.HTTP_200_OK
    assert res_health.json()["status"] in ["ok", "healthy"]


def test_auth_endpoints(unauth_client):
    """Test POST /auth/login and GET /auth/me."""
    # 1. Login with OAuth2 form data
    form_res = unauth_client.post(
        "/api/v1/auth/login",
        data={"username": settings.SUPERADMIN_EMAIL, "password": settings.SUPERADMIN_PASSWORD},
    )
    assert form_res.status_code == status.HTTP_200_OK
    assert "access_token" in form_res.json()
    token = form_res.json()["access_token"]

    # 2. Login with JSON body
    json_res = unauth_client.post(
        "/api/v1/auth/login/json",
        json={"email": settings.SUPERADMIN_EMAIL, "password": settings.SUPERADMIN_PASSWORD},
    )
    assert json_res.status_code == status.HTTP_200_OK
    assert "access_token" in json_res.json()

    # 3. GET /auth/me
    me_res = unauth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == status.HTTP_200_OK
    me_data = me_res.json()
    assert me_data["email"] == settings.SUPERADMIN_EMAIL
    assert me_data["role"] in ["super_admin", "admin"]


def test_projects_endpoints(client):
    """Test full CRUD and status update on /projects."""
    # 1. POST /projects
    create_res = client.post(
        "/api/v1/projects",
        json={"name": "Project Full Lifecycle", "description": "Testing project CRUD"},
    )
    assert create_res.status_code == status.HTTP_201_CREATED
    proj = create_res.json()
    proj_id = proj["id"]
    assert proj["name"] == "Project Full Lifecycle"
    assert proj["status"] == "active"
    assert "document_counts" in proj
    assert "record_counts" in proj

    # 2. GET /projects
    list_res = client.get("/api/v1/projects?skip=0&limit=10")
    assert list_res.status_code == status.HTTP_200_OK
    assert list_res.json()["total"] >= 1

    # 3. GET /projects/{id}
    get_res = client.get(f"/api/v1/projects/{proj_id}")
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.json()["id"] == proj_id

    # 4. PATCH /projects/{id} (rename and transition status to complete/archived)
    patch_res = client.patch(
        f"/api/v1/projects/{proj_id}",
        json={"name": "Project Renamed", "status": "complete"},
    )
    assert patch_res.status_code == status.HTTP_200_OK
    patched = patch_res.json()
    assert patched["name"] == "Project Renamed"
    assert patched["status"] == "complete"

    # 5. DELETE /projects/{id}
    del_res = client.delete(f"/api/v1/projects/{proj_id}")
    assert del_res.status_code == status.HTTP_204_NO_CONTENT
    assert client.get(f"/api/v1/projects/{proj_id}").status_code == status.HTTP_404_NOT_FOUND


def test_vendors_endpoints(client):
    """Test vendor directory, creation, contact update, and deletion."""
    # Setup project
    proj_res = client.post("/api/v1/projects", json={"name": "Vendor Test Project"})
    proj_id = proj_res.json()["id"]

    # 1. POST /projects/{id}/vendors
    create_res = client.post(
        f"/api/v1/projects/{proj_id}/vendors",
        json={
            "name": "Optiline Cables",
            "contact_person": "Alice Smith",
            "contact_email": "alice@optiline.com",
            "contact_phone": "+1-555-0199",
        },
    )
    assert create_res.status_code == status.HTTP_201_CREATED
    vendor = create_res.json()
    vendor_id = vendor["id"]
    assert vendor["name"] == "Optiline Cables"
    assert vendor["contact_person"] == "Alice Smith"

    # 2. GET /projects/{id}/vendors
    list_proj_vnd = client.get(f"/api/v1/projects/{proj_id}/vendors")
    assert list_proj_vnd.status_code == status.HTTP_200_OK
    assert list_proj_vnd.json()["total"] == 1

    # 3. GET /vendors (cross-project directory)
    dir_res = client.get("/api/v1/vendors")
    assert dir_res.status_code == status.HTTP_200_OK
    assert dir_res.json()["total"] >= 1

    # 4. PATCH /vendors/{id}
    patch_res = client.patch(
        f"/api/v1/vendors/{vendor_id}",
        json={"name": "Optiline Cables International"},
    )
    assert patch_res.status_code == status.HTTP_200_OK
    assert patch_res.json()["name"] == "Optiline Cables International"

    # 5. PATCH /vendors/{id}/contact
    contact_res = client.patch(
        f"/api/v1/vendors/{vendor_id}/contact",
        json={"contact_person": "Bob Jones", "contact_email": "bob@optiline.com"},
    )
    assert contact_res.status_code == status.HTTP_200_OK
    assert contact_res.json()["contact_person"] == "Bob Jones"
    assert contact_res.json()["contact_email"] == "bob@optiline.com"

    # 6. DELETE /vendors/{id}
    del_res = client.delete(f"/api/v1/vendors/{vendor_id}")
    assert del_res.status_code == status.HTTP_204_NO_CONTENT


def test_documents_and_upload_lifecycle(client):
    """Test upload, list, get, replace (PUT), download, evidence token, and soft delete."""
    proj_res = client.post("/api/v1/projects", json={"name": "Doc Lifecycle Project"})
    proj_id = proj_res.json()["id"]

    # 1. POST /projects/{id}/documents (upload)
    csv_v1 = b"Part Number,Description,Qty,Rack\nSW-1,Switch 1,1,R1\n"
    files = [("files", ("switches.csv", io.BytesIO(csv_v1), "text/csv"))]
    upload_res = client.post(
        f"/api/v1/projects/{proj_id}/documents",
        files=files,
        data={"source": "plan", "document_type": "bom"},
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["successful"][0]["id"]

    # 2. GET /projects/{id}/documents
    list_docs = client.get(f"/api/v1/projects/{proj_id}/documents")
    assert list_docs.status_code == status.HTTP_200_OK
    assert list_docs.json()["total"] == 1

    # 3. GET /documents/{id}
    get_doc = client.get(f"/api/v1/documents/{doc_id}")
    assert get_doc.status_code == status.HTTP_200_OK
    assert get_doc.json()["version"] == 1

    # 4. GET /documents/{id}/download
    download_res = client.get(f"/api/v1/documents/{doc_id}/download")
    assert download_res.status_code == status.HTTP_200_OK
    assert b"SW-1" in download_res.content

    # 5. PUT /documents/{id} (file replace: version + 1)
    csv_v2 = b"Part Number,Description,Qty,Rack\nSW-1,Switch 1,2,R1\n"
    replace_files = {"file": ("switches_v2.csv", io.BytesIO(csv_v2), "text/csv")}
    replace_res = client.put(f"/api/v1/documents/{doc_id}", files=replace_files)
    assert replace_res.status_code == status.HTTP_200_OK
    doc_v2 = replace_res.json()
    assert doc_v2["id"] == doc_id
    assert doc_v2["version"] == 2

    # 6. DELETE /documents/{id}
    del_res = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == status.HTTP_204_NO_CONTENT
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == status.HTTP_404_NOT_FOUND


def test_ai_and_extraction_endpoints(client, monkeypatch):
    """AI status remains available and extract-all retains background execution."""
    from app.ai.llm import llm_client

    monkeypatch.setattr(llm_client, "is_available", lambda model=None: False)

    ai_status = client.get("/api/v1/ai/status")
    assert ai_status.status_code == status.HTTP_200_OK
    assert ai_status.json()["available"] is False

    proj_res = client.post("/api/v1/projects", json={"name": "AllEndpoints Extract All Test"})
    proj_id = proj_res.json()["id"]
    extract_all_res = client.post(f"/api/v1/projects/{proj_id}/extract-all")
    assert extract_all_res.status_code in [status.HTTP_200_OK, status.HTTP_202_ACCEPTED]



def test_review_records_audit_and_history(client):
    """Test manual record creation, review, patch, history, undo, evidence, batch-review, and summary."""
    proj_res = client.post("/api/v1/projects", json={"name": "Review Full Test"})
    proj_id = proj_res.json()["id"]

    # Upload & extract doc
    csv_bytes = b"Part Number,Description,Qty,Rack\nC9300-48P,Catalyst Switch,4,Rack-B02\n"
    files = [("files", ("c9300.csv", io.BytesIO(csv_bytes), "text/csv"))]
    upload_res = client.post(f"/api/v1/projects/{proj_id}/documents", files=files)
    doc_id = upload_res.json()["successful"][0]["id"]
    client.post(f"/api/v1/documents/{doc_id}/extract")

    records_res = client.get(f"/api/v1/projects/{proj_id}/records")
    items = records_res.json()["items"]
    rec_id = items[0]["id"]

    # 1. GET /records/{id}
    single_rec = client.get(f"/api/v1/records/{rec_id}")
    assert single_rec.status_code == status.HTTP_200_OK
    assert single_rec.json()["part_number"] == "C9300-48P"

    # 2. POST /records/{id}/review (approve)
    rev_res = client.post(
        f"/api/v1/records/{rec_id}/review",
        json={"status": "approved", "review_notes": "First pass approved"},
    )
    assert rev_res.status_code == status.HTTP_200_OK
    assert rev_res.json()["review_status"] == "approved"

    # 3. PATCH /records/{id} (modify quantity)
    patch_res = client.patch(f"/api/v1/records/{rec_id}", json={"quantity": 5.0})
    assert patch_res.status_code == status.HTTP_200_OK
    assert patch_res.json()["quantity"] == 5.0

    # 4. GET /records/{id}/history
    hist_res = client.get(f"/api/v1/records/{rec_id}/history")
    assert hist_res.status_code == status.HTTP_200_OK
    hist = hist_res.json()
    assert len(hist) >= 1

    # 5. POST /records/{id}/undo
    undo_res = client.post(f"/api/v1/records/{rec_id}/undo")
    assert undo_res.status_code == status.HTTP_200_OK

    # 6. GET /records/{id}/evidence
    ev_res = client.get(f"/api/v1/records/{rec_id}/evidence")
    assert ev_res.status_code == status.HTTP_200_OK
    assert ev_res.json()["evidence_type"] == "excel"

    # 7. POST /documents/{id}/records (manually add record)
    man_res = client.post(
        f"/api/v1/documents/{doc_id}/records",
        json={
            "record_type": "bom_item",
            "part_number": "PWR-C1-1100WAC",
            "quantity": 8.0,
            "vendor": "Cisco",
        },
    )
    assert man_res.status_code == status.HTTP_201_CREATED
    man_id = man_res.json()["id"]

    # 8. POST /projects/{id}/records/batch-review
    batch_res = client.post(
        f"/api/v1/projects/{proj_id}/records/batch-review",
        json={"record_ids": [man_id], "action": "approve"},
    )
    assert batch_res.status_code == status.HTTP_200_OK
    assert batch_res.json()["records_reviewed"] == 1

    # 9. GET /projects/{id}/review-summary
    summary_res = client.get(f"/api/v1/projects/{proj_id}/review-summary")
    assert summary_res.status_code == status.HTTP_200_OK
    summary = summary_res.json()
    assert summary["total_records"] == 2
    assert "by_vendor" in summary

    # 10. DELETE /records/{id}
    del_res = client.delete(f"/api/v1/records/{man_id}")
    assert del_res.status_code == status.HTTP_204_NO_CONTENT


def test_comparison_endpoints_complete(client):
    """Test POST & GET /compare, GET /results, GET /issue-groups, GET /runs."""
    proj_res = client.post("/api/v1/projects", json={"name": "Comparison Complete Test"})
    proj_id = proj_res.json()["id"]

    # 1. Run comparison (empty or populated)
    cmp_res = client.post(f"/api/v1/projects/{proj_id}/compare")
    assert cmp_res.status_code == status.HTTP_200_OK
    assert "summary" in cmp_res.json()
    assert "items" in cmp_res.json()

    # 2. GET /projects/{id}/compare
    get_cmp = client.get(f"/api/v1/projects/{proj_id}/compare")
    assert get_cmp.status_code == status.HTTP_200_OK

    # 3. GET /projects/{id}/results
    results_res = client.get(f"/api/v1/projects/{proj_id}/results?page=1&page_size=20")
    assert results_res.status_code == status.HTTP_200_OK
    assert "items" in results_res.json()

    # 4. GET /projects/{id}/issue-groups
    groups_res = client.get(f"/api/v1/projects/{proj_id}/issue-groups")
    assert groups_res.status_code == status.HTTP_200_OK
    assert "items" in groups_res.json()

    # 5. GET /projects/{id}/runs
    runs_res = client.get(f"/api/v1/projects/{proj_id}/runs")
    assert runs_res.status_code == status.HTTP_200_OK
    assert "items" in runs_res.json()


def test_audit_logs_endpoints(client):
    """Test GET /projects/{id}/audit and GET /audit."""
    proj_res = client.post("/api/v1/projects", json={"name": "AllEndpoints Audit Test Project"})
    proj_id = proj_res.json()["id"]

    # 1. GET /projects/{id}/audit
    proj_audit = client.get(f"/api/v1/projects/{proj_id}/audit")
    assert proj_audit.status_code == status.HTTP_200_OK
    assert "items" in proj_audit.json()

    # 2. GET /audit (system-wide)
    sys_audit = client.get("/api/v1/audit?skip=0&limit=50")
    assert sys_audit.status_code == status.HTTP_200_OK
    assert "items" in sys_audit.json()


def test_settings_endpoints(client):
    """Test GET /settings and PUT /settings."""
    # 1. GET /settings
    get_res = client.get("/api/v1/settings")
    assert get_res.status_code == status.HTTP_200_OK
    data = get_res.json()
    assert "high_confidence_threshold" in data
    assert "check_confidence_threshold" in data

    # 2. PUT /settings
    put_res = client.put(
        "/api/v1/settings",
        json={"high_confidence_threshold": 0.95, "inactivity_days": 45},
    )
    assert put_res.status_code == status.HTTP_200_OK
    updated = put_res.json()
    assert updated["high_confidence_threshold"] == 0.95
    assert updated["inactivity_days"] == 45


def test_exports_endpoints(client):
    """Test POST /projects/{id}/exports and GET /exports."""
    proj_res = client.post("/api/v1/projects", json={"name": "Export Test Project"})
    proj_id = proj_res.json()["id"]

    # 1. POST /projects/{id}/exports
    exp_res = client.post(
        f"/api/v1/projects/{proj_id}/exports",
        json={"type": "full", "line_count": 120, "file_name": "full_report.xlsx"},
    )
    assert exp_res.status_code == status.HTTP_201_CREATED
    exp_data = exp_res.json()
    assert exp_data["project_id"] == proj_id
    assert exp_data["line_count"] == 120

    # 2. GET /exports
    list_res = client.get("/api/v1/exports")
    assert list_res.status_code == status.HTTP_200_OK
    assert list_res.json()["total"] >= 1


def test_dashboard_summary_endpoint(client):
    """Test GET /dashboard/summary with scope=all and scope=mine."""
    res_all = client.get("/api/v1/dashboard/summary?scope=all")
    assert res_all.status_code == status.HTTP_200_OK
    data = res_all.json()
    assert "active_projects_count" in data
    assert "open_actions" in data
    assert "records_waiting_for_review" in data
    assert "failed_files" in data
    assert "top_5_urgent_items" in data
    assert "top_5_vendors_by_open_issues" in data

    res_mine = client.get("/api/v1/dashboard/summary?scope=mine")
    assert res_mine.status_code == status.HTTP_200_OK
