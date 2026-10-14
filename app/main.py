from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data storage directories exist
    for directory in [
        settings.UPLOAD_DIR,
        settings.EXTRACTED_DIR,
        settings.PROCESSED_DIR,
        settings.REPORT_DIR,
    ]:
        Path(directory).mkdir(parents=True, exist_ok=True)

    # Create tables if they do not exist
    try:
        Base.metadata.create_all(bind=engine)
        # Seed initial Super Admin if not present
        from app.core.database import SessionLocal
        from app.core.security import init_super_admin
        with SessionLocal() as db:
            init_super_admin(db)
    except Exception as e:
        print(f"Warning: Database initialization or super admin seeding failed: {e}")

    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered document extraction and BOM reconciliation system.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend clients (e.g. Firebase hosting, local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 API routes
app.include_router(api_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "status": "online",
    }


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "service": "ai-data-center-api",
    }