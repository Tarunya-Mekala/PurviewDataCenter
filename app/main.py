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


def patch_property_for_swagger_files(prop):
    """Ensure file properties use format: binary for Swagger UI native file picker."""
    if not isinstance(prop, dict):
        return
    # Array of files
    if prop.get("type") == "array" and isinstance(prop.get("items"), dict):
        items = prop["items"]
        if items.get("contentMediaType") == "application/octet-stream" or items.get("format") == "binary":
            items["type"] = "string"
            items["format"] = "binary"
            items.pop("contentMediaType", None)
    # Single file
    if prop.get("contentMediaType") == "application/octet-stream":
        prop["type"] = "string"
        prop["format"] = "binary"
        prop.pop("contentMediaType", None)
    if "properties" in prop:
        for p in prop["properties"].values():
            patch_property_for_swagger_files(p)
    for option in prop.get("anyOf", []):
        patch_property_for_swagger_files(option)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        openapi_version="3.0.3",
    )
    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        if isinstance(schema, dict):
            for prop in schema.get("properties", {}).values():
                patch_property_for_swagger_files(prop)

    for path_item in openapi_schema.get("paths", {}).values():
        for op in path_item.values():
            if isinstance(op, dict) and "requestBody" in op:
                content = op["requestBody"].get("content", {})
                for media in content.values():
                    if "schema" in media:
                        patch_property_for_swagger_files(media["schema"])

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


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