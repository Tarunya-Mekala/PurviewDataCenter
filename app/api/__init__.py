from fastapi import APIRouter

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.comparison import router as comparison_router
from app.api.dashboard import router as dashboard_router
from app.api.exports import router as exports_router
from app.api.extraction import router as extraction_router
from app.api.projects import router as projects_router
from app.api.review import router as review_router
from app.api.settings import router as settings_router
from app.api.upload import router as upload_router
from app.api.vendors import router as vendors_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(vendors_router)
api_router.include_router(upload_router)
api_router.include_router(extraction_router)
api_router.include_router(review_router)
api_router.include_router(comparison_router)
api_router.include_router(audit_router)
api_router.include_router(settings_router)
api_router.include_router(exports_router)
api_router.include_router(dashboard_router)
