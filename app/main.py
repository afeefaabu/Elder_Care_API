import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import init_db
from app.api.v1.router import api_router
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
    allow_origins=["*"],
    allow_origin_regex=r"https?://.*",
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
    return {
        "status": "HEALTHY",
        "database": "CONNECTED",
        "watchdog_active": watchdog_engine.is_running
    }
