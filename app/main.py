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

    # Apply database migrations via Alembic automatically on startup
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        print(f"Alembic startup migration note: {e}")

    # Create tables and seed initial Super Admin
    try:
        Base.metadata.create_all(bind=engine)
        from app.core.database import SessionLocal
        from app.core.security import init_super_admin
        with SessionLocal() as db:
            init_super_admin(db)
    except Exception as e:
        print(f"Warning: Database initialization or super admin seeding failed: {e}")

    yield


from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered document extraction and BOM reconciliation system.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url="/redoc",
)

def _get_cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin")
    allowed_origin = origin if origin else "*"
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With, Range",
        "Access-Control-Expose-Headers": "*",
    }

@app.middleware("http")
async def outermost_cors_middleware(request: Request, call_next):
    """Ensure every response (including unexpected exceptions and 500s) has CORS headers."""
    if request.method == "OPTIONS":
        return JSONResponse(status_code=200, content={"status": "ok"}, headers=_get_cors_headers(request))

    try:
        response = await call_next(request)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        headers = _get_cors_headers(request)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal Server Error: {str(exc)}"},
            headers=headers,
        )

    for k, v in _get_cors_headers(request).items():
        response.headers[k] = v
    return response

@app.exception_handler(HTTPException)
async def http_exception_cors_handler(request: Request, exc: HTTPException):
    headers = _get_cors_headers(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_cors_handler(request: Request, exc: RequestValidationError):
    from fastapi.encoders import jsonable_encoder
    headers = _get_cors_headers(request)
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
        headers=headers,
    )

@app.exception_handler(Exception)
async def unhandled_exception_cors_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    headers = _get_cors_headers(request)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"},
        headers=headers,
    )

# Standard CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
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

SWAGGER_EYE_TOGGLE_SNIPPET = """
<style>
  .pwd-toggle-wrapper {
    position: relative !important;
    display: inline-flex !important;
    align-items: center !important;
    vertical-align: middle !important;
    width: fit-content !important;
    max-width: 100% !important;
    margin: 5px 0 !important;
    box-sizing: border-box !important;
  }
  .pwd-toggle-wrapper input {
    margin: 0 !important;
    padding-right: 34px !important;
    box-sizing: border-box !important;
  }
  .pwd-toggle-btn {
    position: absolute !important;
    right: 8px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    background: transparent !important;
    border: none !important;
    padding: 2px !important;
    cursor: pointer !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    color: #555e69 !important;
    opacity: 0.75 !important;
    transition: opacity 0.2s ease, color 0.2s ease !important;
    z-index: 10 !important;
    line-height: 1 !important;
  }
  .pwd-toggle-btn:hover {
    opacity: 1 !important;
    color: #111827 !important;
  }
  .pwd-toggle-btn svg {
    width: 18px !important;
    height: 18px !important;
    pointer-events: none !important;
  }
</style>
<script>
  (function() {
    var eyeOpenSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
    var eyeClosedSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg>';

    function attachEyeToggle(input) {
      if (!input || input.getAttribute('data-has-eye-toggle')) return;
      input.setAttribute('data-has-eye-toggle', 'true');

      var parent = input.parentElement;
      if (!parent) return;

      var wrapper;
      if (parent.classList.contains('pwd-toggle-wrapper')) {
        wrapper = parent;
      } else {
        wrapper = document.createElement('div');
        wrapper.className = 'pwd-toggle-wrapper';
        if (input.style.width) wrapper.style.width = input.style.width;
        parent.insertBefore(wrapper, input);
        wrapper.appendChild(input);
      }

      input.style.paddingRight = '34px';

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'pwd-toggle-btn';
      btn.title = 'Show password';
      btn.setAttribute('aria-label', 'Toggle password visibility');
      btn.innerHTML = eyeOpenSvg;

      btn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (input.type === 'password') {
          input.type = 'text';
          btn.innerHTML = eyeClosedSvg;
          btn.title = 'Hide password';
        } else {
          input.type = 'password';
          btn.innerHTML = eyeOpenSvg;
          btn.title = 'Show password';
        }
      });

      wrapper.appendChild(btn);
    }

    function scanInputs() {
      // Find all password inputs in Swagger UI (including Authorize modal & Try-it-out forms)
      var selector = 'input[type="password"], input[name="password"], input[name="client_secret"], input[data-name="password"], input[data-name="client_secret"]';
      var inputs = document.querySelectorAll(selector);
      for (var i = 0; i < inputs.length; i++) {
        attachEyeToggle(inputs[i]);
      }
    }

    var observer = new MutationObserver(function() {
      scanInputs();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    setInterval(scanInputs, 400);
    scanInputs();
  })();
</script>
"""


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html():
    base_response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - API Documentation",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_ui_parameters={"persistAuthorization": True},
    )
    content = base_response.body.decode("utf-8").replace("</body>", f"{SWAGGER_EYE_TOGGLE_SNIPPET}</body>")
    headers = dict(base_response.headers)
    headers.pop("content-length", None)
    return HTMLResponse(content=content, status_code=base_response.status_code, headers=headers)


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


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