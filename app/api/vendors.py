"""Vendor endpoints for managing project suppliers and delivery sides."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_super_admin
from app.models.document import Document
from app.models.project import Project
from app.models.vendor import Vendor
from app.schemas.vendor import (
    VendorContactUpdate,
    VendorCreate,
    VendorListResponse,
    VendorResponse,
    VendorUpdate,
)
from app.utils.id_generator import generate_id

router = APIRouter(
    tags=["Vendors"],
    dependencies=[Depends(get_current_super_admin)],
)


@router.get(
    "/vendors",
    response_model=VendorListResponse,
    summary="List all vendors directory",
    description="Retrieve all registered vendor contacts across projects.",
)
def list_all_vendors(
    db: Session = Depends(get_db),
):
    stmt = select(Vendor).order_by(Vendor.name.asc())
    vendors = db.execute(stmt).scalars().all()
    return VendorListResponse(
        total=len(vendors),
        items=[VendorResponse.model_validate(v) for v in vendors],
    )


@router.get(
    "/projects/{project_id}/vendors",
    response_model=VendorListResponse,
    summary="List all vendors for a project",
    description="Retrieve all registered vendors/suppliers delivering equipment for this project.",
)
def list_project_vendors(
    project_id: str,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    stmt = select(Vendor).where(Vendor.project_id == project_id).order_by(Vendor.created_at.asc())
    vendors = db.execute(stmt).scalars().all()
    return VendorListResponse(
        total=len(vendors),
        items=[VendorResponse.model_validate(v) for v in vendors],
    )


@router.post(
    "/projects/{project_id}/vendors",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new vendor for a project",
    description="Register a new supplier for project deliveries.",
)
def create_project_vendor(
    project_id: str,
    vendor_in: VendorCreate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    vendor = Vendor(
        id=generate_id("vnd_"),
        project_id=project_id,
        name=vendor_in.name.strip(),
        contact_person=vendor_in.contact_person.strip() if vendor_in.contact_person else None,
        contact_email=vendor_in.contact_email.strip() if vendor_in.contact_email else None,
        contact_phone=vendor_in.contact_phone.strip() if vendor_in.contact_phone else None,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return VendorResponse.model_validate(vendor)


@router.patch(
    "/vendors/{vendor_id}",
    response_model=VendorResponse,
    summary="Update vendor details",
    description="Modify the supplier name and contact details.",
)
def update_vendor(
    vendor_id: str,
    vendor_in: VendorUpdate,
    db: Session = Depends(get_db),
):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    if vendor_in.name is not None:
        vendor.name = vendor_in.name.strip()
    if vendor_in.contact_person is not None:
        vendor.contact_person = vendor_in.contact_person.strip()
    if vendor_in.contact_email is not None:
        vendor.contact_email = vendor_in.contact_email.strip()
    if vendor_in.contact_phone is not None:
        vendor.contact_phone = vendor_in.contact_phone.strip()
    db.commit()
    db.refresh(vendor)
    return VendorResponse.model_validate(vendor)


@router.patch(
    "/vendors/{vendor_id}/contact",
    response_model=VendorResponse,
    summary="Update vendor contact information",
    description="Update contact person, email, and phone for a vendor.",
)
def update_vendor_contact(
    vendor_id: str,
    contact_in: VendorContactUpdate,
    db: Session = Depends(get_db),
):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    if contact_in.contact_person is not None:
        vendor.contact_person = contact_in.contact_person.strip()
    if contact_in.contact_email is not None:
        vendor.contact_email = contact_in.contact_email.strip()
    if contact_in.contact_phone is not None:
        vendor.contact_phone = contact_in.contact_phone.strip()

    db.commit()
    db.refresh(vendor)
    return VendorResponse.model_validate(vendor)


@router.delete(
    "/vendors/{vendor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete vendor and its documents",
    description="Delete a vendor and automatically remove all documents associated with that vendor.",
)
def delete_vendor(
    vendor_id: str,
    db: Session = Depends(get_db),
):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    # Delete all documents linked to this vendor
    stmt = select(Document).where(Document.vendor_id == vendor_id)
    docs = db.execute(stmt).scalars().all()
    for d in docs:
        db.delete(d)

    db.delete(vendor)
    db.commit()
    return None
