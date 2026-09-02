"""SoilEdge Field System — FastAPI entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .config import get_settings
from .database import init_db
from .jobs.satellite_job import start_scheduler
from .routers import auth as auth_router
from .routers import data as data_router
from .routers import devices as devices_router
from .routers import fields as fields_router
from .routers import health as health_router
from .routers import model as model_router
from .routers import server as server_router
from .routers import telemetry as telemetry_router
from .routers import voice as voice_router

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("soiledge")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend for the SoilEdge Field System — telemetry, fields, "
                "Sentinel-2 NDVI/NDWI health, and automation logs.",
)

# ---------------------------------------------------------------------------
# CORS — allow the dashboard frontend
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(server_router.router)
app.include_router(auth_router.router)
app.include_router(fields_router.router)
app.include_router(devices_router.router)
app.include_router(telemetry_router.router)
app.include_router(data_router.router)
app.include_router(health_router.router)
app.include_router(model_router.router)
app.include_router(voice_router.router)


# ---------------------------------------------------------------------------
# Validation errors -> structured JSON
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": "validation_error", "details": exc.errors()},
    )


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    logger.info("Initialising database at %s", settings.database_url)
    init_db()
    try:
        start_scheduler(interval_days=5)
    except Exception:  # noqa: BLE001
        logger.exception("Could not start satellite scheduler (non-fatal).")


@app.on_event("shutdown")
def on_shutdown():
    from .jobs.satellite_job import stop_scheduler

    stop_scheduler()


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/login.html")


# Mount the frontend static files so opening http://localhost:8000/ loads frontend pages directly
from pathlib import Path
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
