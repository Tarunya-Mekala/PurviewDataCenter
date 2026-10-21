"""Master Test Suite for All Endpoints with Mock Data and Documents
Tests every endpoint in the API against the live service and database.
"""
import io
import time
import httpx
from app.core.config import settings
from app.core.security import create_evidence_token

BASE_URL = "http://localhost:8000"


class EndpointTester:
    def __init__(self, base_url: str = BASE_URL):
        self.client = httpx.Client(base_url=base_url, timeout=30.0)
        self.token = None
        self.headers = {}
        self.results = []
        self.created_resources = {}

    def log(self, category: str, method: str, path: str, status_code: int, expected_codes: list, detail: str = ""):
        passed = status_code in expected_codes
        symbol = "[PASS]" if passed else "[FAIL]"
        self.results.append({
            "category": category,
            "method": method,
            "path": path,
            "status": status_code,
            "passed": passed,
            "detail": detail,
        })
        print(f"  {symbol} {method:<6} {path:<48} -> {status_code} {detail}")
        if not passed:
            print(f"         EXPECTED: {expected_codes}, GOT: {status_code}")

    def run_all(self):
        print("=" * 72)
        print("STARTING COMPLETE ENDPOINT VALIDATION SUITE WITH MOCK DATA")
        print(f"Target Base URL: {BASE_URL}")
        print("=" * 72)

        self.test_system_health()
        self.test_authentication()
        self.test_projects()
        self.test_vendors()
        self.test_documents_and_uploads()
        self.test_extraction()
        self.test_records_and_review()
        self.test_comparison()
        self.test_reports_and_excel()
        self.test_exports()
        self.test_audit_logs()
        self.test_system_settings()
        self.test_dashboard()
        self.test_cleanup()

        self.print_summary()

    # -------------------------------------------------------------
    # 1. System & Health
    # -------------------------------------------------------------
    def test_system_health(self):
        print("\n--- [1] SYSTEM & HEALTH ENDPOINTS ---")
        # Root
        r = self.client.get("/")
        self.log("System", "GET", "/", r.status_code, [200], f"status: {r.json().get('status', 'online')}")

        # Health
        r = self.client.get("/health")
        self.log("System", "GET", "/health", r.status_code, [200], f"service: {r.json().get('service')}")

    # -------------------------------------------------------------
    # 2. Authentication
    # -------------------------------------------------------------
    def test_authentication(self):
        print("\n--- [2] AUTHENTICATION ENDPOINTS ---")
        # 1. OAuth2 form login
        form_data = {
            "username": settings.SUPERADMIN_EMAIL,
            "password": settings.SUPERADMIN_PASSWORD,
        }
        r = self.client.post("/api/v1/auth/login", data=form_data)
        self.log("Auth", "POST", "/api/v1/auth/login", r.status_code, [200], "OAuth2 form authentication")
        if r.status_code == 200:
            self.token = r.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}

        # 2. JSON body login
        json_data = {
            "email": settings.SUPERADMIN_EMAIL,
            "password": settings.SUPERADMIN_PASSWORD,
        }
        r = self.client.post("/api/v1/auth/login/json", json=json_data)
        self.log("Auth", "POST", "/api/v1/auth/login/json", r.status_code, [200], "JSON body authentication")

        # 3. GET /auth/me
        r = self.client.get("/api/v1/auth/me", headers=self.headers)
        self.log("Auth", "GET", "/api/v1/auth/me", r.status_code, [200], f"User: {r.json().get('email')}")

    # -------------------------------------------------------------
    # 3. Projects
    # -------------------------------------------------------------
    def test_projects(self):
        print("\n--- [3] PROJECTS ENDPOINTS ---")
        # 1. List projects
        r = self.client.get("/api/v1/projects?skip=0&limit=10", headers=self.headers)
        self.log("Projects", "GET", "/api/v1/projects", r.status_code, [200], f"Total projects: {r.json().get('total')}")

        # 2. Create project
        test_proj_payload = {
            "name": f"Automated E2E Test Project {int(time.time() * 1000)}",
            "description": "Temporary project for full endpoint coverage test run",
        }
        r = self.client.post("/api/v1/projects", json=test_proj_payload, headers=self.headers)
        self.log("Projects", "POST", "/api/v1/projects", r.status_code, [201], f"Created project: {r.json().get('id')}")
        if r.status_code == 201:
            self.created_resources["test_project_id"] = r.json()["id"]

        test_proj_id = self.created_resources.get("test_project_id", "proj_ashburn_dc4")

        # 3. Get project by ID
        r = self.client.get(f"/api/v1/projects/{test_proj_id}", headers=self.headers)
        self.log("Projects", "GET", "/api/v1/projects/{id}", r.status_code, [200], f"Retrieved: {r.json().get('name')}")

        # 4. Patch project
        patch_payload = {
            "name": f"Automated E2E Test Project Updated {int(time.time() * 1000)}",
            "status": "active",
        }
        r = self.client.patch(f"/api/v1/projects/{test_proj_id}", json=patch_payload, headers=self.headers)
        self.log("Projects", "PATCH", "/api/v1/projects/{id}", r.status_code, [200], f"Status: {r.json().get('status')}")

        # 5. Project-specific audit logs
        r = self.client.get("/api/v1/projects/proj_ashburn_dc4/audit", headers=self.headers)
        self.log("Projects", "GET", "/api/v1/projects/{id}/audit", r.status_code, [200], f"Logs count: {r.json().get('total')}")

    # -------------------------------------------------------------
    # 4. Vendors
    # -------------------------------------------------------------
    def test_vendors(self):
        print("\n--- [4] VENDORS ENDPOINTS ---")
        test_proj_id = self.created_resources.get("test_project_id", "proj_ashburn_dc4")

        # 1. Global vendors directory
        r = self.client.get("/api/v1/vendors", headers=self.headers)
        self.log("Vendors", "GET", "/api/v1/vendors", r.status_code, [200], f"Total vendors: {r.json().get('total')}")

        # 2. List vendors by project
        r = self.client.get(f"/api/v1/projects/{test_proj_id}/vendors", headers=self.headers)
        self.log("Vendors", "GET", "/api/v1/projects/{id}/vendors", r.status_code, [200], f"Project vendors count: {len(r.json())}")

        # 3. Create vendor in project
        vendor_payload = {
            "name": f"Test Vendor Solutions {int(time.time() * 1000)}",
            "contact_person": "Alex Mercer",
            "contact_email": "alex.m@testvendor.com",
            "contact_phone": "+1-800-555-9876",
        }
        r = self.client.post(f"/api/v1/projects/{test_proj_id}/vendors", json=vendor_payload, headers=self.headers)
        self.log("Vendors", "POST", "/api/v1/projects/{id}/vendors", r.status_code, [201], f"Created vendor: {r.json().get('id')}")
        if r.status_code == 201:
            self.created_resources["test_vendor_id"] = r.json()["id"]

        test_vnd_id = self.created_resources.get("test_vendor_id", "vnd_schneider_dc4")

        # 4. Patch vendor details
        r = self.client.patch(f"/api/v1/vendors/{test_vnd_id}", json={"name": "Test Vendor Updated LLC"}, headers=self.headers)
        self.log("Vendors", "PATCH", "/api/v1/vendors/{id}", r.status_code, [200], f"Updated name: {r.json().get('name')}")

        # 5. Patch vendor contact
        r = self.client.patch(
            f"/api/v1/vendors/{test_vnd_id}/contact",
            json={"contact_person": "Alex Mercer (Senior Director)", "contact_phone": "+1-800-555-1122"},
            headers=self.headers,
        )
        self.log("Vendors", "PATCH", "/api/v1/vendors/{id}/contact", r.status_code, [200], f"Contact: {r.json().get('contact_person')}")

    # -------------------------------------------------------------
    # 5. Documents & Uploads
    # -------------------------------------------------------------
    def test_documents_and_uploads(self):
        print("\n--- [5] DOCUMENTS & UPLOAD ENDPOINTS ---")
        test_proj_id = self.created_resources.get("test_project_id", "proj_ashburn_dc4")

        # 1. Upload new document
        csv_content = b"part_number,description,category,quantity,unit\nMOD-TEST-01,Modular Test Hardware Unit,Hardware,5,ea\n"
        files = [("files", ("test_live_upload.csv", io.BytesIO(csv_content), "text/csv"))]
        data = {"source": "plan", "document_type": "bom"}
        r = self.client.post(f"/api/v1/projects/{test_proj_id}/documents", files=files, data=data, headers=self.headers)
        self.log("Documents", "POST", "/api/v1/projects/{id}/documents", r.status_code, [201], f"Uploaded: {len(r.json().get('successful', []))} doc(s)")
        if r.status_code == 201 and r.json().get("successful"):
            self.created_resources["test_doc_id"] = r.json()["successful"][0]["id"]

        test_doc_id = self.created_resources.get("test_doc_id", "doc_ashburn_plan_bom")

        # 2. List project documents
        r = self.client.get(f"/api/v1/projects/{test_proj_id}/documents", headers=self.headers)
        self.log("Documents", "GET", "/api/v1/projects/{id}/documents", r.status_code, [200], f"Total docs: {r.json().get('total')}")

        # 3. Get single document
        r = self.client.get(f"/api/v1/documents/{test_doc_id}", headers=self.headers)
        self.log("Documents", "GET", "/api/v1/documents/{id}", r.status_code, [200], f"Document: {r.json().get('filename')}")

        # 4. Patch document metadata
        r = self.client.patch(f"/api/v1/documents/{test_doc_id}", json={"document_type": "bom"}, headers=self.headers)
        self.log("Documents", "PATCH", "/api/v1/documents/{id}", r.status_code, [200], f"Updated type: {r.json().get('document_type')}")

        # 5. Download document file
        r = self.client.get(f"/api/v1/documents/{test_doc_id}/download", headers=self.headers)
        self.log("Documents", "GET", "/api/v1/documents/{id}/download", r.status_code, [200], f"Downloaded {len(r.content)} bytes")

        # 6. Reprocess document
        r = self.client.post(f"/api/v1/documents/{test_doc_id}/reprocess", headers=self.headers)
        self.log("Documents", "POST", "/api/v1/documents/{id}/reprocess", r.status_code, [200], f"Status: {r.json().get('status')}")

        # 7. Replace document file (PUT)
        new_csv_content = b"part_number,description,category,quantity,unit\nMOD-TEST-02,Replaced Hardware Unit,Hardware,10,ea\n"
        replace_files = {"file": ("test_replaced.csv", io.BytesIO(new_csv_content), "text/csv")}
        r = self.client.put(f"/api/v1/documents/{test_doc_id}", files=replace_files, headers=self.headers)
        self.log("Documents", "PUT", "/api/v1/documents/{id}", r.status_code, [200], f"Replaced file: {r.json().get('filename')}")

        # 8. Evidence image with signed token
        evidence_token = create_evidence_token(test_doc_id)
        r = self.client.get(f"/api/v1/documents/{test_doc_id}/evidence-image?token={evidence_token}", headers=self.headers)
        self.log("Documents", "GET", "/api/v1/documents/{id}/evidence-image", r.status_code, [200], f"Evidence bytes: {len(r.content)}")

    # -------------------------------------------------------------
    # 6. Extraction
    # -------------------------------------------------------------
    def test_extraction(self):
        print("\n--- [6] EXTRACTION ENDPOINTS ---")
        doc_id = "doc_ashburn_plan_bom"
        proj_id = "proj_ashburn_dc4"

        # 1. Extraction status
        r = self.client.get(f"/api/v1/documents/{doc_id}/extraction-status", headers=self.headers)
        self.log("Extraction", "GET", "/api/v1/documents/{id}/extraction-status", r.status_code, [200], f"Extraction status: {r.json().get('status')}")

        # 2. Extract single document
        r = self.client.post(f"/api/v1/documents/{doc_id}/extract", headers=self.headers)
        self.log("Extraction", "POST", "/api/v1/documents/{id}/extract", r.status_code, [200, 202], f"Status: {r.json().get('status')}")

        # 3. Extract all project documents
        r = self.client.post(f"/api/v1/projects/{proj_id}/extract-all", headers=self.headers)
        self.log("Extraction", "POST", "/api/v1/projects/{id}/extract-all", r.status_code, [200, 202], f"Extracted docs: {r.json().get('total_documents', r.json().get('message'))}")

    # -------------------------------------------------------------
    # 7. Records & Review
    # -------------------------------------------------------------
    def test_records_and_review(self):
        print("\n--- [7] RECORDS & REVIEW ENDPOINTS ---")
        proj_id = "proj_ashburn_dc4"
        doc_id = "doc_ashburn_plan_bom"

        # 1. List project records
        r = self.client.get(f"/api/v1/projects/{proj_id}/records?skip=0&limit=10", headers=self.headers)
        self.log("Records", "GET", "/api/v1/projects/{id}/records", r.status_code, [200], f"Project records: {r.json().get('total')}")

        # 2. List document records
        r = self.client.get(f"/api/v1/documents/{doc_id}/records", headers=self.headers)
        self.log("Records", "GET", "/api/v1/documents/{id}/records", r.status_code, [200], f"Doc records: {r.json().get('total')}")

        # 3. Manually create record
        create_payload = {
            "part_number": "TEST-MANUAL-REC-01",
            "equipment_name": "Test Manually Created Item",
            "category": "PDU",
            "quantity": 2.0,
            "unit": "ea",
        }
        r = self.client.post(f"/api/v1/documents/{doc_id}/records", json=create_payload, headers=self.headers)
        self.log("Records", "POST", "/api/v1/documents/{id}/records", r.status_code, [201], f"Created record: {r.json().get('id')}")
        if r.status_code == 201:
            self.created_resources["test_record_id"] = r.json()["id"]

        rec_id = self.created_resources.get("test_record_id", "rec_ash_plan_ar3300")

        # 4. Get record by ID
        r = self.client.get(f"/api/v1/records/{rec_id}", headers=self.headers)
        self.log("Records", "GET", "/api/v1/records/{id}", r.status_code, [200], f"Record part: {r.json().get('part_number')}")

        # 5. Patch record fields
        r = self.client.patch(f"/api/v1/records/{rec_id}", json={"quantity": 3.0, "unit": "ea"}, headers=self.headers)
        self.log("Records", "PATCH", "/api/v1/records/{id}", r.status_code, [200], f"Updated qty: {r.json().get('quantity')}")

        # 6. Review action (Approve)
        review_payload = {
            "status": "approved",
            "review_notes": "Verified against design engineering specification.",
        }
        r = self.client.post(f"/api/v1/records/{rec_id}/review", json=review_payload, headers=self.headers)
        self.log("Records", "POST", "/api/v1/records/{id}/review", r.status_code, [200], f"Review status: {r.json().get('review_status')}")

        # 7. Record review history
        r = self.client.get(f"/api/v1/records/{rec_id}/history", headers=self.headers)
        self.log("Records", "GET", "/api/v1/records/{id}/history", r.status_code, [200], f"History events: {len(r.json())}")

        # 8. Record evidence URL
        r = self.client.get(f"/api/v1/records/{rec_id}/evidence", headers=self.headers)
        self.log("Records", "GET", "/api/v1/records/{id}/evidence", r.status_code, [200], f"Evidence doc: {r.json().get('document_id')}")

        # 9. Undo review action
        r = self.client.post(f"/api/v1/records/{rec_id}/undo", headers=self.headers)
        self.log("Records", "POST", "/api/v1/records/{id}/undo", r.status_code, [200], f"Undone status: {r.json().get('review_status')}")

        # 10. Batch review
        batch_payload = {
            "record_ids": [rec_id],
            "action": "approve",
            "review_notes": "Batch verified",
        }
        r = self.client.post(f"/api/v1/projects/{proj_id}/records/batch-review", json=batch_payload, headers=self.headers)
        self.log("Records", "POST", "/api/v1/projects/{id}/records/batch-review", r.status_code, [200], f"Batch modified: {r.json().get('modified_count')}")

        # 11. Review summary
        r = self.client.get(f"/api/v1/projects/{proj_id}/review-summary", headers=self.headers)
        self.log("Records", "GET", "/api/v1/projects/{id}/review-summary", r.status_code, [200], f"Summary total: {r.json().get('total_records')}")

    # -------------------------------------------------------------
    # 8. Comparison & Reconciliation
    # -------------------------------------------------------------
    def test_comparison(self):
        print("\n--- [8] COMPARISON & RECONCILIATION ENDPOINTS ---")
        proj_id = "proj_ashburn_dc4"

        # 1. Trigger comparison
        r = self.client.post(f"/api/v1/projects/{proj_id}/compare", headers=self.headers)
        self.log("Comparison", "POST", "/api/v1/projects/{id}/compare", r.status_code, [200], f"Run id: {r.json().get('run_id')}, Matches: {r.json().get('matches_count')}")

        # 2. Get latest comparison summary
        r = self.client.get(f"/api/v1/projects/{proj_id}/compare", headers=self.headers)
        self.log("Comparison", "GET", "/api/v1/projects/{id}/compare", r.status_code, [200], f"Matches: {r.json().get('matches_count')}, Discrepancies: {r.json().get('discrepancies_count')}")

        # 3. List comparison runs
        r = self.client.get(f"/api/v1/projects/{proj_id}/runs", headers=self.headers)
        self.log("Comparison", "GET", "/api/v1/projects/{id}/runs", r.status_code, [200], f"Total runs: {len(r.json())}")

        # 4. List comparison result items
        r = self.client.get(f"/api/v1/projects/{proj_id}/results", headers=self.headers)
        self.log("Comparison", "GET", "/api/v1/projects/{id}/results", r.status_code, [200], f"Itemized results: {len(r.json())}")

        # 5. List issue groups
        r = self.client.get(f"/api/v1/projects/{proj_id}/issue-groups", headers=self.headers)
        self.log("Comparison", "GET", "/api/v1/projects/{id}/issue-groups", r.status_code, [200], f"Issue groups: {len(r.json())}")

    # -------------------------------------------------------------
    # 9. Reports & Excel Export
    # -------------------------------------------------------------
    def test_reports_and_excel(self):
        print("\n--- [9] REPORTS & EXCEL ENDPOINTS ---")
        doc_id = "doc_ashburn_plan_bom"
        proj_id = "proj_ashburn_dc4"

        # Document level Excel
        r = self.client.get(f"/api/v1/documents/{doc_id}/excel", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/documents/{id}/excel", r.status_code, [200], f"Excel bytes: {len(r.content)}")

        r = self.client.get(f"/api/v1/documents/{doc_id}/export/excel", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/documents/{id}/export/excel", r.status_code, [200], f"Alias bytes: {len(r.content)}")

        r = self.client.get(f"/api/v1/documents/{doc_id}/excel/view", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/documents/{id}/excel/view", r.status_code, [200], f"HTML view: {len(r.content)} chars")

        r = self.client.get(f"/api/v1/documents/{doc_id}/excel/preview", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/documents/{id}/excel/preview", r.status_code, [200], f"JSON grid rows: {len(r.json().get('rows', []))}")

        # Project level Excel
        r = self.client.get(f"/api/v1/projects/{proj_id}/excel", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/projects/{id}/excel", r.status_code, [200], f"Project excel bytes: {len(r.content)}")

        r = self.client.get(f"/api/v1/projects/{proj_id}/export/excel", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/projects/{id}/export/excel", r.status_code, [200], f"Project alias bytes: {len(r.content)}")

        r = self.client.get(f"/api/v1/projects/{proj_id}/excel/view", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/projects/{id}/excel/view", r.status_code, [200], f"HTML view: {len(r.content)} chars")

        r = self.client.get(f"/api/v1/projects/{proj_id}/excel/preview", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/projects/{id}/excel/preview", r.status_code, [200], f"JSON grid rows: {len(r.json().get('rows', []))}")

        # /reports prefix paths
        r = self.client.get(f"/api/v1/reports/documents/{doc_id}/excel", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/reports/documents/{id}/excel", r.status_code, [200], "Report document excel")

        r = self.client.get(f"/api/v1/reports/documents/{doc_id}/excel/preview", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/reports/documents/{id}/excel/preview", r.status_code, [200], "Report document preview")

        r = self.client.get(f"/api/v1/reports/documents/{doc_id}/excel/view", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/reports/documents/{id}/excel/view", r.status_code, [200], "Report document view")

        r = self.client.get(f"/api/v1/reports/projects/{proj_id}/excel", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/reports/projects/{id}/excel", r.status_code, [200], "Report project excel")

        r = self.client.get(f"/api/v1/reports/projects/{proj_id}/excel/preview", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/reports/projects/{id}/excel/preview", r.status_code, [200], "Report project preview")

        r = self.client.get(f"/api/v1/reports/projects/{proj_id}/excel/view", headers=self.headers)
        self.log("Reports", "GET", "/api/v1/reports/projects/{id}/excel/view", r.status_code, [200], "Report project view")

    # -------------------------------------------------------------
    # 10. Exports
    # -------------------------------------------------------------
    def test_exports(self):
        print("\n--- [10] EXPORTS ENDPOINTS ---")
        proj_id = "proj_ashburn_dc4"

        # 1. Trigger export
        export_payload = {
            "type": "full",
            "file_name": "Ashburn_DC4_Live_Export.xlsx",
            "line_count": 25,
        }
        r = self.client.post(f"/api/v1/projects/{proj_id}/exports", json=export_payload, headers=self.headers)
        self.log("Exports", "POST", "/api/v1/projects/{id}/exports", r.status_code, [201], f"Exported file: {r.json().get('file_name')}")

        # 2. List exports
        r = self.client.get("/api/v1/exports", headers=self.headers)
        self.log("Exports", "GET", "/api/v1/exports", r.status_code, [200], f"Export records count: {r.json().get('total', len(r.json()))}")

    # -------------------------------------------------------------
    # 11. Audit Logs
    # -------------------------------------------------------------
    def test_audit_logs(self):
        print("\n--- [11] AUDIT LOGS ENDPOINTS ---")
        r = self.client.get("/api/v1/audit?skip=0&limit=10", headers=self.headers)
        self.log("Audit", "GET", "/api/v1/audit", r.status_code, [200], f"Audit entries: {r.json().get('total')}")

    # -------------------------------------------------------------
    # 12. Settings
    # -------------------------------------------------------------
    def test_system_settings(self):
        print("\n--- [12] SYSTEM SETTINGS ENDPOINTS ---")
        # 1. Get settings
        r = self.client.get("/api/v1/settings", headers=self.headers)
        self.log("Settings", "GET", "/api/v1/settings", r.status_code, [200], f"Confidence threshold: {r.json().get('high_confidence_threshold')}")

        # 2. Update settings
        settings_payload = {
            "high_confidence_threshold": 0.90,
            "check_confidence_threshold": 0.75,
            "external_project_name": "Purview Datacenter Enterprise Core",
            "inactivity_days": 45,
        }
        r = self.client.put("/api/v1/settings", json=settings_payload, headers=self.headers)
        self.log("Settings", "PUT", "/api/v1/settings", r.status_code, [200], f"Updated project name: {r.json().get('external_project_name')}")

    # -------------------------------------------------------------
    # 13. Dashboard
    # -------------------------------------------------------------
    def test_dashboard(self):
        print("\n--- [13] DASHBOARD ENDPOINTS ---")
        r = self.client.get("/api/v1/dashboard/summary", headers=self.headers)
        self.log("Dashboard", "GET", "/api/v1/dashboard/summary", r.status_code, [200], f"Active projects: {r.json().get('active_projects_count')}, Urgent items: {len(r.json().get('top_5_urgent_items', []))}")

    # -------------------------------------------------------------
    # 14. Cleanup & Deletion
    # -------------------------------------------------------------
    def test_cleanup(self):
        print("\n--- [14] DELETE & CLEANUP ENDPOINTS ---")
        # Delete test record
        if "test_record_id" in self.created_resources:
            rec_id = self.created_resources["test_record_id"]
            r = self.client.delete(f"/api/v1/records/{rec_id}", headers=self.headers)
            self.log("Cleanup", "DELETE", "/api/v1/records/{id}", r.status_code, [200, 204], f"Deleted record: {rec_id}")

        # Delete test document
        if "test_doc_id" in self.created_resources:
            doc_id = self.created_resources["test_doc_id"]
            r = self.client.delete(f"/api/v1/documents/{doc_id}", headers=self.headers)
            self.log("Cleanup", "DELETE", "/api/v1/documents/{id}", r.status_code, [200, 204], f"Deleted document: {doc_id}")

        # Delete test vendor
        if "test_vendor_id" in self.created_resources:
            vnd_id = self.created_resources["test_vendor_id"]
            r = self.client.delete(f"/api/v1/vendors/{vnd_id}", headers=self.headers)
            self.log("Cleanup", "DELETE", "/api/v1/vendors/{id}", r.status_code, [200, 204], f"Deleted vendor: {vnd_id}")

        # Delete test project
        if "test_project_id" in self.created_resources:
            proj_id = self.created_resources["test_project_id"]
            r = self.client.delete(f"/api/v1/projects/{proj_id}", headers=self.headers)
            self.log("Cleanup", "DELETE", "/api/v1/projects/{id}", r.status_code, [200, 204], f"Deleted project: {proj_id}")

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    def print_summary(self):
        total = len(self.results)
        passed = sum(1 for res in self.results if res["passed"])
        failed = total - passed

        print("\n" + "=" * 72)
        print("ENDPOINT TESTING COMPLETE")
        print(f"Total Endpoints Tested : {total}")
        print(f"Passed                 : {passed}")
        print(f"Failed                 : {failed}")
        print(f"Success Rate           : {(passed / total) * 100:.1f}%")
        print("=" * 72)

        if failed > 0:
            print("\nFAILED ENDPOINTS:")
            for res in self.results:
                if not res["passed"]:
                    print(f"  - {res['method']} {res['path']} (HTTP {res['status']}): {res['detail']}")


if __name__ == "__main__":
    tester = EndpointTester()
    tester.run_all()
