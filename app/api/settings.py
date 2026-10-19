from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_roles
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.schemas.settings import SettingsResponse, SettingsUpdate

router = APIRouter(tags=["System Settings"])


def get_or_create_settings(db: Session) -> SystemSettings:
    settings_obj = db.get(SystemSettings, "global")
    if not settings_obj:
        settings_obj = SystemSettings(
            id="global",
            high_confidence_threshold=0.90,
            check_confidence_threshold=0.70,
            external_project_name="AI Data Center Project",
            inactivity_days=30,
        )
        db.add(settings_obj)
        db.commit()
        db.refresh(settings_obj)
    return settings_obj


@router.get(
    "/settings",
    response_model=SettingsResponse,
    summary="Get system settings",
    description="Retrieve system configuration including confidence thresholds, external project name, and inactivity days.",
)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return get_or_create_settings(db)


@router.put(
    "/settings",
    response_model=SettingsResponse,
    summary="Update system settings",
    description="Update system configuration thresholds. Only admins can modify settings.",
)
def update_settings(
    settings_in: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["super_admin", "admin"])),
):
    settings_obj = get_or_create_settings(db)
    if settings_in.high_confidence_threshold is not None:
        settings_obj.high_confidence_threshold = settings_in.high_confidence_threshold
    if settings_in.check_confidence_threshold is not None:
        settings_obj.check_confidence_threshold = settings_in.check_confidence_threshold
    if settings_in.external_project_name is not None:
        settings_obj.external_project_name = settings_in.external_project_name
    if settings_in.inactivity_days is not None:
        settings_obj.inactivity_days = settings_in.inactivity_days

    settings_obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings_obj)
    return settings_obj
