import time
from fastapi import status
from sqlalchemy import inspect
from app.core.database import SessionLocal, engine
from app.models.vendor import Vendor
from app.models.comparison_run import ComparisonRun
from app.utils.id_generator import generate_id


def test_project_enrichment_vendor_names_and_latest_run(client, db_session):
    """Verify GET /api/v1/projects and GET /api/v1/projects/{id} include vendor names and latest run counts."""
    # 1. Create a project
    proj_name = f"Perf Project {generate_id('tst')}"
    res = client.post(
        "/api/v1/projects",
        json={"name": proj_name, "description": "Testing project enrichment"},
    )
    assert res.status_code == status.HTTP_201_CREATED
    project_id = res.json()["id"]

    # 2. Add vendor entries and comparison run in DB
    v1 = Vendor(
        id=generate_id("vnd"),
        project_id=project_id,
        name="Cisco Systems",
    )
    v2 = Vendor(
        id=generate_id("vnd"),
        project_id=project_id,
        name="Arista Networks",
    )
    db_session.add_all([v1, v2])

    # Run 1
    r1 = ComparisonRun(
        id=generate_id("run_"),
        project_id=project_id,
        run_number=1,
        status="completed",
        total_expected=100.0,
        total_found=90.0,
        matches_count=80,
        discrepancies_count=10,
        exceptions_count=10,
    )
    # Run 2 (latest)
    r2 = ComparisonRun(
        id=generate_id("run_"),
        project_id=project_id,
        run_number=2,
        status="completed",
        total_expected=120.0,
        total_found=115.0,
        matches_count=110,
        discrepancies_count=5,
        exceptions_count=5,
    )
    db_session.add_all([r1, r2])
    db_session.commit()

    # 3. Test GET /api/v1/projects (list endpoint)
    t0 = time.perf_counter()
    res = client.get("/api/v1/projects")
    t1 = time.perf_counter()
    assert res.status_code == status.HTTP_200_OK
    assert (t1 - t0) < 1.0  # Fast response time under 1 second

    data = res.json()
    assert "items" in data
    matching = [p for p in data["items"] if p["id"] == project_id]
    assert len(matching) == 1
    proj_data = matching[0]

    # Verify vendors
    assert "vendor_names" in proj_data
    assert "vendors" in proj_data
    assert sorted(proj_data["vendor_names"]) == ["Arista Networks", "Cisco Systems"]
    assert sorted(proj_data["vendors"]) == ["Arista Networks", "Cisco Systems"]

    # Verify latest run counts
    assert "latest_run" in proj_data
    assert "latest_run_counts" in proj_data
    assert proj_data["latest_run"] is not None
    assert proj_data["latest_run"]["run_number"] == 2
    assert proj_data["latest_run"]["matches_count"] == 110
    assert proj_data["latest_run"]["discrepancies_count"] == 5
    assert proj_data["latest_run"]["exceptions_count"] == 5
    assert proj_data["latest_run"]["total_expected"] == 120.0
    assert proj_data["latest_run"]["match_rate_percentage"] == round((110 / 120.0) * 100, 2)

    # 4. Test GET /api/v1/projects/{project_id} (single detail endpoint)
    res_single = client.get(f"/api/v1/projects/{project_id}")
    assert res_single.status_code == status.HTTP_200_OK
    single_data = res_single.json()

    assert sorted(single_data["vendor_names"]) == ["Arista Networks", "Cisco Systems"]
    assert sorted(single_data["vendors"]) == ["Arista Networks", "Cisco Systems"]
    assert single_data["latest_run"]["run_number"] == 2
    assert single_data["latest_run"]["matches_count"] == 110


def test_database_performance_indexes():
    """Verify performance indexes on project_id, document_id, review_status, etc. exist in database."""
    insp = inspect(engine)

    # Check extracted_records indexes
    rec_indexes = [idx["name"] for idx in insp.get_indexes("extracted_records")]
    assert any("project_id" in idx for idx in rec_indexes)
    assert any("document_id" in idx for idx in rec_indexes)
    assert any("review_status" in idx for idx in rec_indexes)
    assert "idx_extracted_records_proj_status_del" in rec_indexes or any("proj" in idx and "status" in idx for idx in rec_indexes)

    # Check documents indexes
    doc_indexes = [idx["name"] for idx in insp.get_indexes("documents")]
    assert any("project_id" in idx for idx in doc_indexes)
    assert any("status" in idx for idx in doc_indexes)
