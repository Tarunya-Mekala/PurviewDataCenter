from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.extraction import router as extraction_router
from app.api.projects import router as projects_router
from app.api.review import router as review_router
from app.api.upload import router as upload_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(upload_router)
api_router.include_router(extraction_router)
api_router.include_router(review_router)
