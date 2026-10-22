"""Seed script to populate rich, realistic mock datacenter data across ALL tables
and create real mock documents on disk.
"""
import csv
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import (
    Base,
    User,
    Project,
    Vendor,
    Document,
    ExtractedRecord,
    RecordReviewAction,
    ComparisonRun,
    IssueGroup,
    ComparisonResultItem,
    ExportRecord,
    AuditLog,
    SystemSettings,
)
from app.utils.id_generator import generate_id


def utc_now():
    return datetime.now(timezone.utc)


def calculate_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def create_styled_excel(filepath: Path, sheets_data: dict):
    """Create a professionally styled multi-sheet Excel workbook."""
    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    data_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    first = True
    for sheet_name, table_info in sheets_data.items():
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(title=sheet_name)

        headers = table_info["headers"]
        rows = table_info["rows"]

        # Write headers
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Write data rows
        for row_idx, row_data in enumerate(rows, 2):
            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = data_font
                cell.border = thin_border
                if isinstance(val, (int, float)):
                    cell.alignment = Alignment(horizontal="right")

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    wb.save(filepath)
    return filepath


def create_csv(filepath: Path, headers: list, rows: list):
    """Create a formatted CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return filepath


def run_seed():
    print("=" * 60)
    print("AI DATA CENTER DOCUMENT COMPARISON - MOCK DATA SEEDER")
    print("=" * 60)
    print(f"Connecting to database: {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        now = utc_now()

        # =========================================================
        # 1. USERS
        # =========================================================
        print("\n[1/12] Seeding Users...")
        users_data = [
            {
                "id": "usr_superadmin",
                "email": settings.SUPERADMIN_EMAIL,
                "hashed_password": hash_password(settings.SUPERADMIN_PASSWORD),
                "full_name": settings.SUPERADMIN_NAME,
                "role": "super_admin",
                "is_active": True,
                "is_super_admin": True,
            },
            {
                "id": "usr_engineer",
                "email": "engineer@datacenter.ai",
                "hashed_password": hash_password("Engineer@12345"),
                "full_name": "Marcus Vance (Lead Infrastructure Engineer)",
                "role": "engineer",
                "is_active": True,
                "is_super_admin": False,
            },
            {
                "id": "usr_reviewer",
                "email": "reviewer@datacenter.ai",
                "hashed_password": hash_password("Reviewer@12345"),
                "full_name": "Elena Rostova (QA Data Reviewer)",
                "role": "reviewer",
                "is_active": True,
                "is_super_admin": False,
            },
            {
                "id": "usr_auditor",
                "email": "auditor@datacenter.ai",
                "hashed_password": hash_password("Auditor@12345"),
                "full_name": "David Sterling (Procurement Compliance Auditor)",
                "role": "auditor",
                "is_active": True,
                "is_super_admin": False,
            },
        ]
        for u_data in users_data:
            existing = db.execute(select(User).where(User.email == u_data["email"])).scalar_one_or_none()
            if not existing:
                user = User(**u_data)
                db.add(user)
            else:
                existing.full_name = u_data["full_name"]
                existing.role = u_data["role"]
                existing.is_active = True
                existing.is_super_admin = u_data["is_super_admin"]
        db.commit()
        print(f"  -> Users verified/seeded: {len(users_data)}")

        # =========================================================
        # 2. PROJECTS
        # =========================================================
        print("\n[2/12] Seeding Projects...")
        projects_data = [
            {
                "id": "proj_ashburn_dc4",
                "name": "Ashburn DC-4 Hyperscale Expansion",
                "description": "BOM and delivery reconciliation for 40MW Ashburn Tier IV data hall expansion including racks, 3-phase PDUs, and 100G interconnects.",
                "status": "active",
                "owner_id": "usr_superadmin",
                "created_by": settings.SUPERADMIN_EMAIL,
            },
            {
                "id": "proj_phoenix_dc2",
                "name": "Phoenix DC-2 Edge Facility Upgrade",
                "description": "Full lifecycle comparison and vendor quote reconciliation for edge colocation deployment.",
                "status": "complete",
                "owner_id": "usr_engineer",
                "created_by": "engineer@datacenter.ai",
            },
            {
                "id": "proj_santaclara_p3",
                "name": "Santa Clara Core Colocation Phase 3",
                "description": "Power infrastructure and modular cooling equipment verification across vendor deliveries.",
                "status": "active",
                "owner_id": "usr_reviewer",
                "created_by": "reviewer@datacenter.ai",
            },
        ]
        for p_data in projects_data:
            p = db.get(Project, p_data["id"])
            if not p:
                p = Project(**p_data)
                db.add(p)
            else:
                p.name = p_data["name"]
                p.description = p_data["description"]
                p.status = p_data["status"]
        db.commit()
        print(f"  -> Projects seeded: {len(projects_data)}")

        # =========================================================
        # 3. VENDORS
        # =========================================================
        print("\n[3/12] Seeding Vendors...")
        vendors_data = [
            {
                "id": "vnd_schneider_dc4",
                "project_id": "proj_ashburn_dc4",
                "name": "Schneider Electric IT Corp",
                "contact_person": "Sarah Jenkins (Enterprise Sales Director)",
                "contact_email": "sarah.j@se-datacenter.com",
                "contact_phone": "+1-571-555-0142",
            },
            {
                "id": "vnd_vertiv_dc4",
                "project_id": "proj_ashburn_dc4",
                "name": "Vertiv Critical Infrastructure",
                "contact_person": "Mark Vance (Data Center Specialist)",
                "contact_email": "mvance@vertiv.com",
                "contact_phone": "+1-614-555-0199",
            },
            {
                "id": "vnd_cisco_phx",
                "project_id": "proj_phoenix_dc2",
                "name": "Cisco Systems Data Center Solutions",
                "contact_person": "Dave Rodriguez (Account Executive)",
                "contact_email": "drodriguez@cisco-direct.com",
                "contact_phone": "+1-408-555-0123",
            },
            {
                "id": "vnd_eaton_sc",
                "project_id": "proj_santaclara_p3",
                "name": "Eaton Power Quality Division",
                "contact_person": "Elena Rostova (Power Systems Mgr)",
                "contact_email": "elena@eaton-power.com",
                "contact_phone": "+1-919-555-0188",
            },
        ]
        for v_data in vendors_data:
            v = db.get(Vendor, v_data["id"])
            if not v:
                v = Vendor(**v_data)
                db.add(v)
            else:
                v.name = v_data["name"]
                v.contact_person = v_data["contact_person"]
                v.contact_email = v_data["contact_email"]
                v.contact_phone = v_data["contact_phone"]
        db.commit()
        print(f"  -> Vendors seeded: {len(vendors_data)}")

        # =========================================================
        # 4. DOCUMENTS & PHYSICAL FILES
        # =========================================================
        print("\n[4/12] Creating Mock Files and Seeding Documents...")
        base_upload = Path(settings.UPLOAD_DIR)

        # File 1: Ashburn Plan BOM (Excel)
        doc1_filename = "Ashburn_DC4_Engineering_BOM.xlsx"
        doc1_rel = f"proj_ashburn_dc4/doc_ashburn_plan_{doc1_filename}"
        doc1_path = base_upload / doc1_rel
        create_styled_excel(
            doc1_path,
            {
                "Equipment_Racks": {
                    "headers": ["Part Number", "Description", "Category", "Qty", "Unit", "Rack ID", "U Position", "Power (kW)", "Manufacturer"],
                    "rows": [
                        ["AR3300", "NetShelter SX 42U Server Rack Enclosure 800x1200", "Rack", 20, "ea", "RK-01..20", "1U-42U", 0.0, "Schneider Electric"],
                        ["AR3350", "NetShelter SX 48U Network Cabinet 750x1070", "Rack", 8, "ea", "RK-NET-01..08", "1U-48U", 0.0, "Schneider Electric"],
                        ["AP8868", "Rack PDU 2G Metered ZeroU 60A 208V 3PH (18)C13 (6)C19", "PDU", 40, "ea", "RK-01..20", "0U", 17.2, "Schneider Electric"],
                        ["AP8959", "Rack PDU 2G Switched ZeroU 20A 120/208V (21)C13 (3)C19", "PDU", 16, "ea", "RK-NET-01..08", "0U", 5.7, "Schneider Electric"],
                    ],
                },
                "Critical_Power": {
                    "headers": ["Part Number", "Description", "Category", "Qty", "Unit", "Rack ID", "U Position", "Power (kW)", "Manufacturer"],
                    "rows": [
                        ["UPS-500K-MOD", "Modular 500kVA N+1 Redundant High-Efficiency UPS", "UPS", 2, "ea", "POWER-RM-A", "Floor", 500.0, "Schneider Electric"],
                        ["ATS-30A", "Automatic Static Transfer Switch 30A 208V Dual Input", "Power", 10, "ea", "RK-CORE-01..10", "1U", 6.2, "Schneider Electric"],
                    ],
                },
                "Cabling_Optics": {
                    "headers": ["Part Number", "Description", "Category", "Qty", "Unit", "Rack ID", "U Position", "Power (kW)", "Manufacturer"],
                    "rows": [
                        ["C6A-3M-BL", "Cat6A 10GbE Shielded Patch Cable 3-meter Blue Snagless", "Cable", 200, "pcs", "RK-ALL", "N/A", 0.0, "Panduit"],
                        ["MPO-100G-15M", "100G MPO-12 to MPO-12 OM4 Trunk Fiber Cable 15m", "Cable", 60, "pcs", "RK-TRUNK", "Overhead", 0.0, "Panduit"],
                        ["FPP-48-1U", "High-Density Fiber Patch Panel 48-Port 1U Angled", "Connectivity", 12, "ea", "RK-FIBER-01", "41U", 0.0, "Panduit"],
                    ],
                },
            },
        )

        # File 2: Schneider Quote (Excel) - Note intentional differences:
        # AP8868 has Qty 36 instead of 40 (discrepancy)
        # AR3300 matches Qty 20 (match)
        # MPO-100G-15M is omitted (exception)
        doc2_filename = "Schneider_Quote_Ashburn_DC4.xlsx"
        doc2_rel = f"proj_ashburn_dc4/doc_schneider_quote_{doc2_filename}"
        doc2_path = base_upload / doc2_rel
        create_styled_excel(
            doc2_path,
            {
                "Quotation_Items": {
                    "headers": ["Item Code", "Product Description", "Category", "Quoted Qty", "Unit", "Unit Price ($)", "Total Price ($)"],
                    "rows": [
                        ["AR3300", "NetShelter SX 42U Server Rack Enclosure 800x1200", "Rack", 20, "ea", 1850.00, 37000.00],
                        ["AR3350", "NetShelter SX 48U Network Cabinet 750x1070", "Rack", 8, "ea", 2150.00, 17200.00],
                        ["AP8868", "Rack PDU 2G Metered ZeroU 60A 208V 3PH (18)C13 (6)C19", "PDU", 36, "ea", 1450.00, 52200.00],
                        ["AP8959", "Rack PDU 2G Switched ZeroU 20A 120/208V (21)C13 (3)C19", "PDU", 16, "ea", 1250.00, 20000.00],
                        ["UPS-500K-MOD", "Modular 500kVA N+1 Redundant High-Efficiency UPS", "UPS", 2, "ea", 185000.00, 370000.00],
                        ["ATS-30A", "Automatic Static Transfer Switch 30A 208V Dual Input", "Power", 10, "ea", 2850.00, 28500.00],
                    ],
                }
            },
        )

        # File 3: Vertiv Quote (CSV)
        doc3_filename = "Vertiv_Cooling_Quote.csv"
        doc3_rel = f"proj_ashburn_dc4/doc_vertiv_{doc3_filename}"
        doc3_path = base_upload / doc3_rel
        create_csv(
            doc3_path,
            ["part_number", "description", "category", "quantity", "unit", "unit_price", "manufacturer"],
            [
                ["ACRD301P", "Liebert In-Row Direct Expansion Cooling Unit 35kW EC Fan", "Cooling", 6, "ea", 32500.00, "Vertiv"],
                ["ACDC2000", "SmartAisle Aisle Containment Modular Sliding Doors 42U/48U", "Containment", 4, "sets", 8500.00, "Vertiv"],
                ["SN-Z01", "Wireless Temperature and Humidity Rack Sensor Pods", "Sensor", 40, "pcs", 185.00, "Vertiv"],
            ],
        )

        # File 4: Phoenix Plan BOM (CSV)
        doc4_filename = "Phoenix_DC2_Plan_BOM.csv"
        doc4_rel = f"proj_phoenix_dc2/doc_phoenix_plan_{doc4_filename}"
        doc4_path = base_upload / doc4_rel
        create_csv(
            doc4_path,
            ["part_number", "equipment_name", "category", "quantity", "unit", "rack", "u_position", "power_kw", "manufacturer"],
            [
                ["N9K-C93180YC-FX3", "Cisco Nexus 93180YC-FX3 48p 10/25G SFP28 6p 100G QSFP28", "Network", 12, "ea", "RK-TOR-01..12", "42U", 0.45, "Cisco"],
                ["N9K-C9364C", "Cisco Nexus 9364C Spine Switch 64p 100G QSFP28 2RU", "Network", 4, "ea", "RK-SPINE-01..02", "38U", 1.25, "Cisco"],
                ["QSFP-100G-SR4-S", "Cisco 100GBASE-SR4 QSFP Transceiver Module MPO", "Optics", 48, "pcs", "RK-ALL", "N/A", 0.0, "Cisco"],
                ["CAB-C13-C14-2M", "Power Cord C13 to C14 10A 250V 2.0-meter Black", "Power Cable", 80, "pcs", "RK-ALL", "N/A", 0.0, "Cisco"],
            ],
        )

        # File 5: Cisco Quote (Excel) - Phoenix Vendor Quote
        doc5_filename = "Cisco_Switching_Quote.xlsx"
        doc5_rel = f"proj_phoenix_dc2/doc_cisco_quote_{doc5_filename}"
        doc5_path = base_upload / doc5_rel
        create_styled_excel(
            doc5_path,
            {
                "Cisco_Hardware": {
                    "headers": ["Part Number", "Description", "Category", "Quoted Quantity", "Unit", "Unit Price", "Lead Time (Weeks)"],
                    "rows": [
                        ["N9K-C93180YC-FX3", "Nexus 93180YC-FX3 48p 10/25G SFP28 6p 100G", "Network", 12, "ea", 8450.00, 4],
                        ["N9K-C9364C", "Nexus 9364C Spine Switch 64p 100G QSFP28 2RU", "Network", 4, "ea", 22500.00, 6],
                        ["QSFP-100G-SR4-S", "100GBASE-SR4 QSFP Transceiver Module MPO", "Optics", 44, "pcs", 450.00, 2],  # Discrepancy: 44 vs 48
                        ["CAB-C13-C14-2M", "Power Cord C13 to C14 10A 250V 2.0m", "Power Cable", 80, "pcs", 28.00, 1],
                    ],
                }
            },
        )

        # File 6: Santa Clara Power Plan (Excel)
        doc6_filename = "SantaClara_Power_Plan.xlsx"
        doc6_rel = f"proj_santaclara_p3/doc_sc_plan_{doc6_filename}"
        doc6_path = base_upload / doc6_rel
        create_styled_excel(
            doc6_path,
            {
                "Power_Distribution": {
                    "headers": ["Part Number", "Description", "Category", "Quantity", "Unit", "Rack", "Power (kW)"],
                    "rows": [
                        ["93PM-400kVA", "Eaton 93PM Modular 400kVA High Efficiency UPS", "UPS", 2, "ea", "UPS-BAY-1", 400.0],
                        ["ePDU-G3", "Eaton G3 Managed Rack PDU 30A 208V 3PH (24)C13 (6)C19", "PDU", 24, "ea", "RK-01..12", 8.6],
                    ],
                }
            },
        )

        documents_metadata = [
            {
                "id": "doc_ashburn_plan_bom",
                "project_id": "proj_ashburn_dc4",
                "filename": doc1_filename,
                "stored_filename": f"doc_ashburn_plan_{doc1_filename}",
                "file_path": f"/app/data/uploads/{doc1_rel}",
                "file_type": "xlsx",
                "file_size": doc1_path.stat().st_size,
                "document_type": "bom",
                "status": "extracted",
                "source": "plan",
                "vendor_id": None,
                "checksum_sha256": calculate_sha256(doc1_path),
                "metadata_json": {"sheet_names": ["Equipment_Racks", "Critical_Power", "Cabling_Optics"], "total_sheets": 3},
            },
            {
                "id": "doc_schneider_quote",
                "project_id": "proj_ashburn_dc4",
                "filename": doc2_filename,
                "stored_filename": f"doc_schneider_quote_{doc2_filename}",
                "file_path": f"/app/data/uploads/{doc2_rel}",
                "file_type": "xlsx",
                "file_size": doc2_path.stat().st_size,
                "document_type": "purchase",
                "status": "extracted",
                "source": "vendor",
                "vendor_id": "vnd_schneider_dc4",
                "checksum_sha256": calculate_sha256(doc2_path),
                "metadata_json": {"sheet_names": ["Quotation_Items"], "vendor": "Schneider Electric"},
            },
            {
                "id": "doc_vertiv_quote",
                "project_id": "proj_ashburn_dc4",
                "filename": doc3_filename,
                "stored_filename": f"doc_vertiv_{doc3_filename}",
                "file_path": f"/app/data/uploads/{doc3_rel}",
                "file_type": "csv",
                "file_size": doc3_path.stat().st_size,
                "document_type": "purchase",
                "status": "extracted",
                "source": "vendor",
                "vendor_id": "vnd_vertiv_dc4",
                "checksum_sha256": calculate_sha256(doc3_path),
                "metadata_json": {"rows": 3, "delimiter": ","},
            },
            {
                "id": "doc_phoenix_plan_bom",
                "project_id": "proj_phoenix_dc2",
                "filename": doc4_filename,
                "stored_filename": f"doc_phoenix_plan_{doc4_filename}",
                "file_path": f"/app/data/uploads/{doc4_rel}",
                "file_type": "csv",
                "file_size": doc4_path.stat().st_size,
                "document_type": "bom",
                "status": "extracted",
                "source": "plan",
                "vendor_id": None,
                "checksum_sha256": calculate_sha256(doc4_path),
                "metadata_json": {"rows": 4, "delimiter": ","},
            },
            {
                "id": "doc_cisco_quote",
                "project_id": "proj_phoenix_dc2",
                "filename": doc5_filename,
                "stored_filename": f"doc_cisco_quote_{doc5_filename}",
                "file_path": f"/app/data/uploads/{doc5_rel}",
                "file_type": "xlsx",
                "file_size": doc5_path.stat().st_size,
                "document_type": "purchase",
                "status": "extracted",
                "source": "vendor",
                "vendor_id": "vnd_cisco_phx",
                "checksum_sha256": calculate_sha256(doc5_path),
                "metadata_json": {"sheet_names": ["Cisco_Hardware"]},
            },
            {
                "id": "doc_santaclara_plan_bom",
                "project_id": "proj_santaclara_p3",
                "filename": doc6_filename,
                "stored_filename": f"doc_sc_plan_{doc6_filename}",
                "file_path": f"/app/data/uploads/{doc6_rel}",
                "file_type": "xlsx",
                "file_size": doc6_path.stat().st_size,
                "document_type": "bom",
                "status": "extracted",
                "source": "plan",
                "vendor_id": None,
                "checksum_sha256": calculate_sha256(doc6_path),
                "metadata_json": {"sheet_names": ["Power_Distribution"]},
            },
        ]

        for d_meta in documents_metadata:
            d = db.get(Document, d_meta["id"])
            if not d:
                d = Document(**d_meta)
                db.add(d)
            else:
                for k, v in d_meta.items():
                    setattr(d, k, v)
        db.commit()
        print(f"  -> Documents seeded and physical files created: {len(documents_metadata)}")

        # =========================================================
        # 5. EXTRACTED RECORDS
        # =========================================================
        print("\n[5/12] Seeding Extracted Records...")
        # Clear existing records for our seeded docs to ensure clean data
        seeded_doc_ids = [d["id"] for d in documents_metadata]
        db.execute(delete(ExtractedRecord).where(ExtractedRecord.document_id.in_(seeded_doc_ids)))
        db.commit()

        records_data = [
            # Ashburn Plan BOM Records (Document: doc_ashburn_plan_bom)
            {
                "id": "rec_ash_plan_ar3300",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "bom_item",
                "category": "Rack",
                "equipment_name": "NetShelter SX 42U Server Rack Enclosure 800x1200",
                "part_number": "AR3300",
                "cleaned_part_number": "AR3300",
                "model": "AR3300",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric",
                "quantity": 20.0,
                "unit": "ea",
                "rack_id": "RK-01..20",
                "rack": "RK-01..20",
                "u_position": "1U-42U",
                "location": "Data Hall 4, Col A-D",
                "power_kw": 0.0,
                "confidence_score": 0.98,
                "extraction_method": "table",
                "review_status": "approved",
                "reviewed_by": "reviewer@datacenter.ai",
                "reviewed_at": now - timedelta(days=1),
                "review_notes": "Verified against floor plan revision C",
            },
            {
                "id": "rec_ash_plan_ar3350",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "bom_item",
                "category": "Rack",
                "equipment_name": "NetShelter SX 48U Network Cabinet 750x1070",
                "part_number": "AR3350",
                "cleaned_part_number": "AR3350",
                "model": "AR3350",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric",
                "quantity": 8.0,
                "unit": "ea",
                "rack_id": "RK-NET-01..08",
                "rack": "RK-NET-01..08",
                "u_position": "1U-48U",
                "location": "Data Hall 4, Network Row",
                "power_kw": 0.0,
                "confidence_score": 0.96,
                "extraction_method": "table",
                "review_status": "approved",
                "reviewed_by": "engineer@datacenter.ai",
                "reviewed_at": now - timedelta(days=1),
            },
            {
                "id": "rec_ash_plan_ap8868",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "bom_item",
                "category": "PDU",
                "equipment_name": "Rack PDU 2G Metered ZeroU 60A 208V 3PH (18)C13 (6)C19",
                "part_number": "AP8868",
                "cleaned_part_number": "AP8868",
                "model": "AP8868",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric",
                "quantity": 40.0,
                "unit": "ea",
                "rack_id": "RK-01..20",
                "rack": "RK-01..20",
                "u_position": "0U",
                "power_kw": 17.2,
                "confidence_score": 0.99,
                "extraction_method": "table",
                "review_status": "approved",
                "reviewed_by": "reviewer@datacenter.ai",
                "reviewed_at": now - timedelta(hours=18),
            },
            {
                "id": "rec_ash_plan_ap8959",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "bom_item",
                "category": "PDU",
                "equipment_name": "Rack PDU 2G Switched ZeroU 20A 120/208V (21)C13 (3)C19",
                "part_number": "AP8959",
                "cleaned_part_number": "AP8959",
                "model": "AP8959",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric",
                "quantity": 16.0,
                "unit": "ea",
                "rack_id": "RK-NET-01..08",
                "rack": "RK-NET-01..08",
                "u_position": "0U",
                "power_kw": 5.7,
                "confidence_score": 0.95,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_plan_ups",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "bom_item",
                "category": "UPS",
                "equipment_name": "Modular 500kVA N+1 Redundant High-Efficiency UPS",
                "part_number": "UPS-500K-MOD",
                "cleaned_part_number": "UPS500KMOD",
                "model": "Galaxy VX 500",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric",
                "quantity": 2.0,
                "unit": "ea",
                "location": "Electrical Room A & B",
                "power_kw": 500.0,
                "confidence_score": 0.94,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_plan_ats",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "bom_item",
                "category": "Power",
                "equipment_name": "Automatic Static Transfer Switch 30A 208V Dual Input",
                "part_number": "ATS-30A",
                "cleaned_part_number": "ATS30A",
                "model": "AP4424",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric",
                "quantity": 10.0,
                "unit": "ea",
                "rack_id": "RK-CORE-01..10",
                "rack": "RK-CORE-01..10",
                "u_position": "1U",
                "power_kw": 6.2,
                "confidence_score": 0.92,
                "extraction_method": "table",
                "review_status": "pending_review",
            },
            {
                "id": "rec_ash_plan_c6a",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "cable",
                "category": "Cable",
                "equipment_name": "Cat6A 10GbE Shielded Patch Cable 3-meter Blue Snagless",
                "part_number": "C6A-3M-BL",
                "cleaned_part_number": "C6A3MBL",
                "manufacturer": "Panduit",
                "quantity": 200.0,
                "unit": "pcs",
                "cable_length_m": 3.0,
                "cable_type": "Cat6A Shielded",
                "confidence_score": 0.90,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_plan_mpo",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_ashburn_plan_bom",
                "record_type": "cable",
                "category": "Cable",
                "equipment_name": "100G MPO-12 to MPO-12 OM4 Trunk Fiber Cable 15m",
                "part_number": "MPO-100G-15M",
                "cleaned_part_number": "MPO100G15M",
                "manufacturer": "Panduit",
                "quantity": 60.0,
                "unit": "pcs",
                "cable_length_m": 15.0,
                "cable_type": "MPO-12 OM4",
                "confidence_score": 0.88,
                "extraction_method": "table",
                "review_status": "pending_review",
            },

            # Ashburn Vendor Quote Records (Document: doc_schneider_quote)
            {
                "id": "rec_ash_vnd_ar3300",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_schneider_quote",
                "record_type": "vendor_quote_item",
                "category": "Rack",
                "equipment_name": "NetShelter SX 42U Server Rack Enclosure 800x1200",
                "part_number": "AR3300",
                "cleaned_part_number": "AR3300",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric IT Corp",
                "quantity": 20.0,
                "unit": "ea",
                "confidence_score": 0.99,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_vnd_ar3350",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_schneider_quote",
                "record_type": "vendor_quote_item",
                "category": "Rack",
                "equipment_name": "NetShelter SX 48U Network Cabinet 750x1070",
                "part_number": "AR3350",
                "cleaned_part_number": "AR3350",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric IT Corp",
                "quantity": 8.0,
                "unit": "ea",
                "confidence_score": 0.98,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_vnd_ap8868",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_schneider_quote",
                "record_type": "vendor_quote_item",
                "category": "PDU",
                "equipment_name": "Rack PDU 2G Metered ZeroU 60A 208V 3PH (18)C13 (6)C19",
                "part_number": "AP8868",
                "cleaned_part_number": "AP8868",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric IT Corp",
                "quantity": 36.0,  # 36 delivered vs 40 planned (Discrepancy!)
                "unit": "ea",
                "confidence_score": 0.97,
                "extraction_method": "table",
                "review_status": "modified",
                "reviewed_by": "reviewer@datacenter.ai",
                "reviewed_at": now - timedelta(hours=10),
                "review_notes": "Vendor quoted 36 instead of 40 units due to factory allocation.",
            },
            {
                "id": "rec_ash_vnd_ap8959",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_schneider_quote",
                "record_type": "vendor_quote_item",
                "category": "PDU",
                "equipment_name": "Rack PDU 2G Switched ZeroU 20A 120/208V (21)C13 (3)C19",
                "part_number": "AP8959",
                "cleaned_part_number": "AP8959",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric IT Corp",
                "quantity": 16.0,
                "unit": "ea",
                "confidence_score": 0.96,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_vnd_ups",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_schneider_quote",
                "record_type": "vendor_quote_item",
                "category": "UPS",
                "equipment_name": "Modular 500kVA N+1 Redundant High-Efficiency UPS",
                "part_number": "UPS-500K-MOD",
                "cleaned_part_number": "UPS500KMOD",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric IT Corp",
                "quantity": 2.0,
                "unit": "ea",
                "confidence_score": 0.95,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_vnd_ats",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_schneider_quote",
                "record_type": "vendor_quote_item",
                "category": "Power",
                "equipment_name": "Automatic Static Transfer Switch 30A 208V Dual Input",
                "part_number": "ATS-30A",
                "cleaned_part_number": "ATS30A",
                "manufacturer": "Schneider Electric",
                "vendor": "Schneider Electric IT Corp",
                "quantity": 10.0,
                "unit": "ea",
                "confidence_score": 0.92,
                "extraction_method": "table",
                "review_status": "approved",
            },

            # Ashburn Vertiv Quote Records (Document: doc_vertiv_quote)
            {
                "id": "rec_ash_vnd_cooling",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_vertiv_quote",
                "record_type": "vendor_quote_item",
                "category": "Cooling",
                "equipment_name": "Liebert In-Row Direct Expansion Cooling Unit 35kW EC Fan",
                "part_number": "ACRD301P",
                "cleaned_part_number": "ACRD301P",
                "manufacturer": "Vertiv",
                "vendor": "Vertiv Critical Infrastructure",
                "quantity": 6.0,
                "unit": "ea",
                "confidence_score": 0.94,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_ash_vnd_containment",
                "project_id": "proj_ashburn_dc4",
                "document_id": "doc_vertiv_quote",
                "record_type": "vendor_quote_item",
                "category": "Containment",
                "equipment_name": "SmartAisle Aisle Containment Modular Sliding Doors 42U/48U",
                "part_number": "ACDC2000",
                "cleaned_part_number": "ACDC2000",
                "manufacturer": "Vertiv",
                "vendor": "Vertiv Critical Infrastructure",
                "quantity": 4.0,
                "unit": "sets",
                "confidence_score": 0.90,
                "extraction_method": "table",
                "review_status": "approved",
            },

            # Phoenix Plan & Cisco Records
            {
                "id": "rec_phx_plan_n9k_leaf",
                "project_id": "proj_phoenix_dc2",
                "document_id": "doc_phoenix_plan_bom",
                "record_type": "bom_item",
                "category": "Network",
                "equipment_name": "Cisco Nexus 93180YC-FX3 48p 10/25G SFP28 6p 100G QSFP28",
                "part_number": "N9K-C93180YC-FX3",
                "cleaned_part_number": "N9KC93180YCFX3",
                "manufacturer": "Cisco",
                "quantity": 12.0,
                "unit": "ea",
                "rack": "RK-TOR-01..12",
                "u_position": "42U",
                "power_kw": 0.45,
                "confidence_score": 0.98,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_phx_plan_n9k_spine",
                "project_id": "proj_phoenix_dc2",
                "document_id": "doc_phoenix_plan_bom",
                "record_type": "bom_item",
                "category": "Network",
                "equipment_name": "Cisco Nexus 9364C Spine Switch 64p 100G QSFP28 2RU",
                "part_number": "N9K-C9364C",
                "cleaned_part_number": "N9KC9364C",
                "manufacturer": "Cisco",
                "quantity": 4.0,
                "unit": "ea",
                "rack": "RK-SPINE-01..02",
                "u_position": "38U",
                "power_kw": 1.25,
                "confidence_score": 0.98,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_phx_plan_optics",
                "project_id": "proj_phoenix_dc2",
                "document_id": "doc_phoenix_plan_bom",
                "record_type": "bom_item",
                "category": "Optics",
                "equipment_name": "Cisco 100GBASE-SR4 QSFP Transceiver Module MPO",
                "part_number": "QSFP-100G-SR4-S",
                "cleaned_part_number": "QSFP100GSR4S",
                "manufacturer": "Cisco",
                "quantity": 48.0,
                "unit": "pcs",
                "confidence_score": 0.95,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_phx_vnd_optics",
                "project_id": "proj_phoenix_dc2",
                "document_id": "doc_cisco_quote",
                "record_type": "vendor_quote_item",
                "category": "Optics",
                "equipment_name": "100GBASE-SR4 QSFP Transceiver Module MPO",
                "part_number": "QSFP-100G-SR4-S",
                "cleaned_part_number": "QSFP100GSR4S",
                "manufacturer": "Cisco",
                "vendor": "Cisco Systems Data Center Solutions",
                "quantity": 44.0,  # 44 quoted vs 48 planned (Discrepancy!)
                "unit": "pcs",
                "confidence_score": 0.96,
                "extraction_method": "table",
                "review_status": "modified",
                "reviewed_by": "engineer@datacenter.ai",
                "reviewed_at": now - timedelta(days=2),
                "review_notes": "Shortage of 4 transceiver modules identified in quotation.",
            },

            # Santa Clara Plan Records
            {
                "id": "rec_sc_plan_ups",
                "project_id": "proj_santaclara_p3",
                "document_id": "doc_santaclara_plan_bom",
                "record_type": "bom_item",
                "category": "UPS",
                "equipment_name": "Eaton 93PM Modular 400kVA High Efficiency UPS",
                "part_number": "93PM-400kVA",
                "cleaned_part_number": "93PM400KVA",
                "manufacturer": "Eaton",
                "quantity": 2.0,
                "unit": "ea",
                "power_kw": 400.0,
                "confidence_score": 0.96,
                "extraction_method": "table",
                "review_status": "approved",
            },
            {
                "id": "rec_sc_plan_epdu",
                "project_id": "proj_santaclara_p3",
                "document_id": "doc_santaclara_plan_bom",
                "record_type": "bom_item",
                "category": "PDU",
                "equipment_name": "Eaton G3 Managed Rack PDU 30A 208V 3PH (24)C13 (6)C19",
                "part_number": "ePDU-G3",
                "cleaned_part_number": "EPDUG3",
                "manufacturer": "Eaton",
                "quantity": 24.0,
                "unit": "ea",
                "power_kw": 8.6,
                "confidence_score": 0.92,
                "extraction_method": "table",
                "review_status": "pending_review",
            },
        ]

        valid_cols = {c.name for c in ExtractedRecord.__table__.columns}
        for r_data in records_data:
            if "equipment_name" in r_data and "description" not in r_data:
                r_data["description"] = r_data["equipment_name"]
            if "rack_id" in r_data and "rack" not in r_data:
                r_data["rack"] = r_data["rack_id"]
            filtered_data = {k: v for k, v in r_data.items() if k in valid_cols}
            rec = ExtractedRecord(**filtered_data)
            db.add(rec)
        db.commit()
        print(f"  -> Extracted records seeded: {len(records_data)}")

        # =========================================================
        # 6. RECORD REVIEW ACTIONS
        # =========================================================
        print("\n[6/12] Seeding Record Review Actions...")
        review_actions_data = [
            {
                "id": "act_ash_ap8868_mod",
                "record_id": "rec_ash_vnd_ap8868",
                "action": "update",
                "old_values": {"quantity": 40.0, "review_status": "pending_review"},
                "new_values": {"quantity": 36.0, "review_status": "modified"},
                "reason": "Updated to reflect supplier's allocation limit of 36 units for batch 1 delivery.",
                "reviewer_id": "reviewer@datacenter.ai",
                "created_at": now - timedelta(hours=10),
            },
            {
                "id": "act_ash_ar3300_appr",
                "record_id": "rec_ash_plan_ar3300",
                "action": "review",
                "old_values": {"review_status": "pending_review"},
                "new_values": {"review_status": "approved"},
                "reason": "Rack dimensions, clearances, and quantities verified against architectural CAD drawings.",
                "reviewer_id": "reviewer@datacenter.ai",
                "created_at": now - timedelta(days=1),
            },
            {
                "id": "act_phx_optics_mod",
                "record_id": "rec_phx_vnd_optics",
                "action": "update",
                "old_values": {"quantity": 48.0, "review_status": "pending_review"},
                "new_values": {"quantity": 44.0, "review_status": "modified"},
                "reason": "Supplier confirmed quotation deficit of 4 optical transceivers.",
                "reviewer_id": "engineer@datacenter.ai",
                "created_at": now - timedelta(days=2),
            },
        ]
        for a_data in review_actions_data:
            existing_act = db.get(RecordReviewAction, a_data["id"])
            if not existing_act:
                act = RecordReviewAction(**a_data)
                db.add(act)
        db.commit()
        print(f"  -> Record review actions seeded: {len(review_actions_data)}")

        # =========================================================
        # 7. COMPARISON RUNS
        # =========================================================
        print("\n[7/12] Seeding Comparison Runs...")
        runs_data = [
            {
                "id": "run_ashburn_001",
                "project_id": "proj_ashburn_dc4",
                "run_number": 1,
                "status": "completed",
                "rule_set_version": "1.0",
                "total_expected": 156.0,
                "total_found": 152.0,
                "matches_count": 5,
                "discrepancies_count": 1,
                "exceptions_count": 1,
                "started_at": now - timedelta(hours=12),
                "finished_at": now - timedelta(hours=11, minutes=58),
            },
            {
                "id": "run_ashburn_002",
                "project_id": "proj_ashburn_dc4",
                "run_number": 2,
                "status": "completed",
                "rule_set_version": "1.1",
                "total_expected": 156.0,
                "total_found": 156.0,
                "matches_count": 6,
                "discrepancies_count": 0,
                "exceptions_count": 0,
                "started_at": now - timedelta(hours=4),
                "finished_at": now - timedelta(hours=3, minutes=58),
            },
            {
                "id": "run_phoenix_001",
                "project_id": "proj_phoenix_dc2",
                "run_number": 1,
                "status": "completed",
                "rule_set_version": "1.0",
                "total_expected": 144.0,
                "total_found": 140.0,
                "matches_count": 3,
                "discrepancies_count": 1,
                "exceptions_count": 0,
                "started_at": now - timedelta(days=2),
                "finished_at": now - timedelta(days=2) + timedelta(minutes=2),
            },
        ]
        for r_data in runs_data:
            r = db.get(ComparisonRun, r_data["id"])
            if not r:
                r = ComparisonRun(**r_data)
                db.add(r)
            else:
                for k, v in r_data.items():
                    setattr(r, k, v)
        db.commit()
        print(f"  -> Comparison runs seeded: {len(runs_data)}")

        # =========================================================
        # 8. ISSUE GROUPS
        # =========================================================
        print("\n[8/12] Seeding Issue Groups...")
        issue_groups_data = [
            {
                "id": "grp_ash_pdu_shortage",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "PDU",
                "cause": "Under-delivery in Vendor Quotation",
                "summary": "Schneider quoted 36 units of 60A 3-Phase PDUs (AP8868) against engineering BOM requirement of 40 units.",
                "total_lines": 1,
                "created_at": now - timedelta(hours=11, minutes=58),
            },
            {
                "id": "grp_ash_mpo_missing",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "Cable",
                "cause": "Item Omission / Out of Scope",
                "summary": "60 units of 100G MPO Trunk Cables (MPO-100G-15M) were omitted from quotation.",
                "total_lines": 1,
                "created_at": now - timedelta(hours=11, minutes=58),
            },
            {
                "id": "grp_phx_optics_shortage",
                "project_id": "proj_phoenix_dc2",
                "run_id": "run_phoenix_001",
                "vendor_id": "vnd_cisco_phx",
                "vendor_name": "Cisco Systems Data Center Solutions",
                "category": "Optics",
                "cause": "Quantity Mismatch",
                "summary": "Cisco quoted 44 optical modules (QSFP-100G-SR4-S) against required 48 modules.",
                "total_lines": 1,
                "created_at": now - timedelta(days=2),
            },
        ]
        for ig_data in issue_groups_data:
            ig = db.get(IssueGroup, ig_data["id"])
            if not ig:
                ig = IssueGroup(**ig_data)
                db.add(ig)
            else:
                for k, v in ig_data.items():
                    setattr(ig, k, v)
        db.commit()
        print(f"  -> Issue groups seeded: {len(issue_groups_data)}")

        # =========================================================
        # 9. COMPARISON RESULTS
        # =========================================================
        print("\n[9/12] Seeding Comparison Result Items...")
        db.execute(delete(ComparisonResultItem).where(ComparisonResultItem.run_id.in_(["run_ashburn_001", "run_phoenix_001"])))
        db.commit()

        results_data = [
            # Ashburn Run 1 Results
            {
                "id": "res_ash_ar3300",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "rack": "RK-01..20",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "Rack",
                "item": "NetShelter SX 42U Server Rack Enclosure 800x1200",
                "part_number": "AR3300",
                "field": "quantity",
                "expected": 20.0,
                "found": 20.0,
                "difference": 0.0,
                "result": "match",
                "action": "Verified and approved for procurement.",
                "cause": "Exact Match",
                "expected_source": "Ashburn_DC4_Engineering_BOM.xlsx",
                "found_source": "Schneider_Quote_Ashburn_DC4.xlsx",
                "rule_id": "RULE-EXACT-001",
                "condition_status": "ok",
                "condition_notes": "All dimensions and configurations align with tier IV spec.",
            },
            {
                "id": "res_ash_ar3350",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "rack": "RK-NET-01..08",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "Rack",
                "item": "NetShelter SX 48U Network Cabinet 750x1070",
                "part_number": "AR3350",
                "field": "quantity",
                "expected": 8.0,
                "found": 8.0,
                "difference": 0.0,
                "result": "match",
                "action": "Verified and approved.",
                "cause": "Exact Match",
                "expected_source": "Ashburn_DC4_Engineering_BOM.xlsx",
                "found_source": "Schneider_Quote_Ashburn_DC4.xlsx",
                "rule_id": "RULE-EXACT-001",
                "condition_status": "ok",
            },
            {
                "id": "res_ash_ap8868",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "rack": "RK-01..20",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "PDU",
                "item": "Rack PDU 2G Metered ZeroU 60A 208V 3PH (18)C13 (6)C19",
                "part_number": "AP8868",
                "field": "quantity",
                "expected": 40.0,
                "found": 36.0,
                "difference": -4.0,
                "result": "discrepancy",
                "action": "Issue change order / addendum request for 4 additional PDUs.",
                "cause": "Quantity Shortage",
                "issue_group_id": "grp_ash_pdu_shortage",
                "issue_summary": "4 PDU units missing from vendor delivery scope.",
                "expected_source": "Ashburn_DC4_Engineering_BOM.xlsx",
                "found_source": "Schneider_Quote_Ashburn_DC4.xlsx",
                "rule_id": "RULE-QTY-001",
                "condition_status": "discrepancy",
                "condition_notes": "Shortage impacts Rack rows C & D dual-cord redundancy.",
            },
            {
                "id": "res_ash_ups",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "rack": "POWER-RM",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "UPS",
                "item": "Modular 500kVA N+1 Redundant High-Efficiency UPS",
                "part_number": "UPS-500K-MOD",
                "field": "quantity",
                "expected": 2.0,
                "found": 2.0,
                "difference": 0.0,
                "result": "match",
                "action": "Approved for FAT factory witness testing.",
                "cause": "Exact Match",
                "expected_source": "Ashburn_DC4_Engineering_BOM.xlsx",
                "found_source": "Schneider_Quote_Ashburn_DC4.xlsx",
                "rule_id": "RULE-EXACT-001",
                "condition_status": "ok",
            },
            {
                "id": "res_ash_ats",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "rack": "RK-CORE",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "Power",
                "item": "Automatic Static Transfer Switch 30A 208V Dual Input",
                "part_number": "ATS-30A",
                "field": "quantity",
                "expected": 10.0,
                "found": 10.0,
                "difference": 0.0,
                "result": "match",
                "action": "Approved.",
                "cause": "Exact Match",
                "expected_source": "Ashburn_DC4_Engineering_BOM.xlsx",
                "found_source": "Schneider_Quote_Ashburn_DC4.xlsx",
                "rule_id": "RULE-EXACT-001",
                "condition_status": "ok",
            },
            {
                "id": "res_ash_mpo",
                "project_id": "proj_ashburn_dc4",
                "run_id": "run_ashburn_001",
                "rack": "RK-TRUNK",
                "vendor_id": "vnd_schneider_dc4",
                "vendor_name": "Schneider Electric IT Corp",
                "category": "Cable",
                "item": "100G MPO-12 to MPO-12 OM4 Trunk Fiber Cable 15m",
                "part_number": "MPO-100G-15M",
                "field": "quantity",
                "expected": 60.0,
                "found": 0.0,
                "difference": -60.0,
                "result": "exception",
                "action": "Procure via structured cabling vendor (Panduit/Corning).",
                "cause": "Item Not Quoted",
                "issue_group_id": "grp_ash_mpo_missing",
                "issue_summary": "Item not in Schneider scope; requires secondary cabling contract.",
                "expected_source": "Ashburn_DC4_Engineering_BOM.xlsx",
                "found_source": "Schneider_Quote_Ashburn_DC4.xlsx",
                "rule_id": "RULE-MISSING-001",
                "condition_status": "exception",
            },

            # Phoenix Run 1 Results
            {
                "id": "res_phx_n9k_leaf",
                "project_id": "proj_phoenix_dc2",
                "run_id": "run_phoenix_001",
                "rack": "RK-TOR-01..12",
                "vendor_id": "vnd_cisco_phx",
                "vendor_name": "Cisco Systems Data Center Solutions",
                "category": "Network",
                "item": "Cisco Nexus 93180YC-FX3 48p 10/25G SFP28 6p 100G QSFP28",
                "part_number": "N9K-C93180YC-FX3",
                "field": "quantity",
                "expected": 12.0,
                "found": 12.0,
                "difference": 0.0,
                "result": "match",
                "action": "Approved for DC edge deployment.",
                "cause": "Exact Match",
                "expected_source": "Phoenix_DC2_Plan_BOM.csv",
                "found_source": "Cisco_Switching_Quote.xlsx",
                "rule_id": "RULE-EXACT-001",
                "condition_status": "ok",
            },
            {
                "id": "res_phx_optics",
                "project_id": "proj_phoenix_dc2",
                "run_id": "run_phoenix_001",
                "rack": "RK-ALL",
                "vendor_id": "vnd_cisco_phx",
                "vendor_name": "Cisco Systems Data Center Solutions",
                "category": "Optics",
                "item": "Cisco 100GBASE-SR4 QSFP Transceiver Module MPO",
                "part_number": "QSFP-100G-SR4-S",
                "field": "quantity",
                "expected": 48.0,
                "found": 44.0,
                "difference": -4.0,
                "result": "discrepancy",
                "action": "Procure 4 additional transceiver modules from authorized reseller.",
                "cause": "Quantity Discrepancy",
                "issue_group_id": "grp_phx_optics_shortage",
                "issue_summary": "4 optics short in quote.",
                "expected_source": "Phoenix_DC2_Plan_BOM.csv",
                "found_source": "Cisco_Switching_Quote.xlsx",
                "rule_id": "RULE-QTY-001",
                "condition_status": "discrepancy",
            },
        ]
        for r_item in results_data:
            db.add(ComparisonResultItem(**r_item))
        db.commit()
        print(f"  -> Comparison result items seeded: {len(results_data)}")

        # =========================================================
        # 10. EXPORT RECORDS
        # =========================================================
        print("\n[10/12] Seeding Export Records...")
        exports_data = [
            {
                "id": "exp_ashburn_full_xlsx",
                "project_id": "proj_ashburn_dc4",
                "export_type": "full",
                "vendor_id": None,
                "file_name": "Ashburn_DC4_Full_BOM_Reconciliation.xlsx",
                "line_count": 28,
                "created_by": settings.SUPERADMIN_EMAIL,
                "created_at": now - timedelta(hours=3),
            },
            {
                "id": "exp_ashburn_issues_xlsx",
                "project_id": "proj_ashburn_dc4",
                "export_type": "issues",
                "vendor_id": "vnd_schneider_dc4",
                "file_name": "Ashburn_DC4_Schneider_Discrepancies.xlsx",
                "line_count": 2,
                "created_by": "reviewer@datacenter.ai",
                "created_at": now - timedelta(hours=2),
            },
            {
                "id": "exp_phoenix_vendor_xlsx",
                "project_id": "proj_phoenix_dc2",
                "export_type": "vendor",
                "vendor_id": "vnd_cisco_phx",
                "file_name": "Phoenix_DC2_Cisco_Reconciliation.xlsx",
                "line_count": 16,
                "created_by": "engineer@datacenter.ai",
                "created_at": now - timedelta(days=1),
            },
        ]
        for e_data in exports_data:
            e = db.get(ExportRecord, e_data["id"])
            if not e:
                e = ExportRecord(**e_data)
                db.add(e)
            else:
                for k, v in e_data.items():
                    setattr(e, k, v)
        db.commit()
        print(f"  -> Export records seeded: {len(exports_data)}")

        # =========================================================
        # 11. AUDIT LOGS
        # =========================================================
        print("\n[11/12] Seeding Audit Logs...")
        audit_logs_data = [
            {
                "id": "aud_proj_create_001",
                "project_id": "proj_ashburn_dc4",
                "user_id": "usr_superadmin",
                "user_email": settings.SUPERADMIN_EMAIL,
                "action": "project_created",
                "resource_type": "project",
                "resource_id": "proj_ashburn_dc4",
                "details": {"name": "Ashburn DC-4 Hyperscale Expansion", "status": "active"},
                "created_at": now - timedelta(days=3),
            },
            {
                "id": "aud_doc_upload_001",
                "project_id": "proj_ashburn_dc4",
                "user_id": "usr_engineer",
                "user_email": "engineer@datacenter.ai",
                "action": "upload",
                "resource_type": "document",
                "resource_id": "doc_ashburn_plan_bom",
                "details": {"filename": "Ashburn_DC4_Engineering_BOM.xlsx", "source": "plan", "type": "plan_bom"},
                "created_at": now - timedelta(days=2),
            },
            {
                "id": "aud_extract_001",
                "project_id": "proj_ashburn_dc4",
                "user_id": "usr_reviewer",
                "user_email": "reviewer@datacenter.ai",
                "action": "extract",
                "resource_type": "document",
                "resource_id": "doc_ashburn_plan_bom",
                "details": {"records_extracted": 8, "method": "table_and_ai"},
                "created_at": now - timedelta(days=1, hours=20),
            },
            {
                "id": "aud_review_001",
                "project_id": "proj_ashburn_dc4",
                "user_id": "usr_reviewer",
                "user_email": "reviewer@datacenter.ai",
                "action": "review",
                "resource_type": "record",
                "resource_id": "rec_ash_plan_ar3300",
                "details": {"action": "approve", "review_status": "approved"},
                "created_at": now - timedelta(days=1),
            },
            {
                "id": "aud_compare_001",
                "project_id": "proj_ashburn_dc4",
                "user_id": "usr_superadmin",
                "user_email": settings.SUPERADMIN_EMAIL,
                "action": "compare",
                "resource_type": "project",
                "resource_id": "proj_ashburn_dc4",
                "details": {"run_id": "run_ashburn_001", "matches": 5, "discrepancies": 1, "exceptions": 1},
                "created_at": now - timedelta(hours=12),
            },
            {
                "id": "aud_export_001",
                "project_id": "proj_ashburn_dc4",
                "user_id": "usr_superadmin",
                "user_email": settings.SUPERADMIN_EMAIL,
                "action": "export",
                "resource_type": "project",
                "resource_id": "proj_ashburn_dc4",
                "details": {"export_id": "exp_ashburn_full_xlsx", "format": "xlsx", "records": 28},
                "created_at": now - timedelta(hours=3),
            },
            {
                "id": "aud_settings_001",
                "project_id": None,
                "user_id": "usr_superadmin",
                "user_email": settings.SUPERADMIN_EMAIL,
                "action": "settings_change",
                "resource_type": "settings",
                "resource_id": "global",
                "details": {"high_confidence_threshold": 0.90, "check_confidence_threshold": 0.75},
                "created_at": now - timedelta(days=5),
            },
        ]
        for a_data in audit_logs_data:
            a = db.get(AuditLog, a_data["id"])
            if not a:
                a = AuditLog(**a_data)
                db.add(a)
            else:
                for k, v in a_data.items():
                    setattr(a, k, v)
        db.commit()
        print(f"  -> Audit logs seeded: {len(audit_logs_data)}")

        # =========================================================
        # 12. SYSTEM SETTINGS
        # =========================================================
        print("\n[12/12] Seeding System Settings...")
        settings_entry = db.get(SystemSettings, "global")
        if not settings_entry:
            settings_entry = SystemSettings(
                id="global",
                high_confidence_threshold=0.90,
                check_confidence_threshold=0.75,
                external_project_name="Purview Datacenter Enterprise Core",
                inactivity_days=45,
            )
            db.add(settings_entry)
        else:
            settings_entry.high_confidence_threshold = 0.90
            settings_entry.check_confidence_threshold = 0.75
            settings_entry.external_project_name = "Purview Datacenter Enterprise Core"
            settings_entry.inactivity_days = 45
        db.commit()
        print("  -> Global System Settings configured.")

    print("\n" + "=" * 60)
    print("SUCCESS: ALL 12 TABLES POPULATED WITH RICH MOCK DATA!")
    print("=" * 60)


if __name__ == "__main__":
    run_seed()
