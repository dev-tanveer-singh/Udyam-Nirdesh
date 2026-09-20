import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (registers the tables on Base.metadata)
from .config import get_settings
from .database import Base, engine
from .routers import admin, applications, auth, documents, meta, partners, profile, readiness, schemes, tools
from .seed import run_seed

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("udyam")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # For production, manage the schema with Alembic migrations instead of create_all().
    Base.metadata.create_all(engine)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.seed_on_startup:
        run_seed()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Backend for Udyam-Nirdesh: profile, scheme matching, documents, partners, applications, readiness score.",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
)

# The API authenticates with a bearer token (not cookies), so credentials are not needed cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith(API_PREFIX):
        response.headers.setdefault("Cache-Control", "no-store")  # never cache personal data
    return response


for router in (meta.router, auth.router, profile.router, schemes.router, documents.router,
               partners.router, applications.router, readiness.router, tools.router, admin.router):
    app.include_router(router, prefix=API_PREFIX)

# Serve ../frontend from the same origin (so no CORS is needed). Must be mounted LAST.
if settings.serve_frontend and (settings.frontend_dir / "index.html").exists():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    log.info("Serving frontend from %s", settings.frontend_dir)
