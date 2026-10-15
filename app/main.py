import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import init_db, engine
from app.api.v1.router import api_router
from app.services.admin_seed_service import seed_default_admin
from app.services.watchdog_service import watchdog_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("eldercare-api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    logger.info("Starting Elder Care Backend...")
    await init_db()
    await seed_default_admin()
    await watchdog_engine.start()
    yield
    # Shutdown:
    logger.info("Shutting down Elder Care Backend...")
    await watchdog_engine.stop()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Production-Ready API for Elder Care System (Senior Citizen, Caregiver & Admin)",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Uploads Directory for Pill Photos
upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

# Include master API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "ONLINE",
        "docs_url": "/docs",
        "health_check": f"{settings.API_V1_STR}/health"
    }

@app.get(f"{settings.API_V1_STR}/health")
async def health_check():
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness database check failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "NOT_READY", "database": "UNAVAILABLE"},
        )

    external_delivery = "REAL" if settings.has_real_sms_delivery else "SIMULATED"
    return {
        "status": "HEALTHY",
        "database": "CONNECTED",
        "watchdog_active": watchdog_engine.is_running,
        "environment": settings.ENVIRONMENT,
        "sms_delivery": external_delivery,
        "production_configuration_ready": (
            settings.is_production
            and settings.SECRET_KEY != "temporary-secret-key-for-elder-care-change-in-production"
            and settings.has_real_sms_delivery
        ),
    }
