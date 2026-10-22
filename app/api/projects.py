from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_reviewer_or_admin, require_viewer_or_above
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.document_service import DocumentService

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
    description="Create an isolated project workspace for BOM and document reconciliation. Reviewer and admin only.",
)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin),
):
    project = DocumentService.create_project(db, project_in)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        owner_id=project.owner_id,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=0,
    )


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List all projects",
    description="Retrieve all projects with their document counts and metadata. Viewers permitted.",
)
def list_projects(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Limit for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer_or_above),
):
    total, projects = DocumentService.list_projects(db, skip=skip, limit=limit)
    return ProjectListResponse(total=total, items=projects)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details",
    description="Retrieve details of a specific project. Viewers permitted.",
)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer_or_above),
):
    project = DocumentService.get_project(db, project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        owner_id=project.owner_id,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=len(project.documents),
    )


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project name or status",
    description="Rename a project or transition status to 'active', 'complete', or 'archived'. Reviewer and admin only.",
)
def update_project(
    project_id: str,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin),
):
    project = DocumentService.update_project(db, project_id, project_in)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        owner_id=project.owner_id,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=len(project.documents) if project.documents else 0,
    )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    description="Delete a project and all its associated documents and stored files. Reviewer and admin only.",
)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer_or_admin),
):
    DocumentService.delete_project(db, project_id)
    return None
