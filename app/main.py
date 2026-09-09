import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import init_db, AsyncSessionLocal
from app.api.v1.router import api_router
from app.services.watchdog_service import watchdog_engine
from app.models.directory import ServiceDirectory
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("eldercare-api")

async def seed_city_directory():
    async with AsyncSessionLocal() as session:
        stmt = select(ServiceDirectory).where(ServiceDirectory.scope == "CITY_VERIFIED")
        res = await session.execute(stmt)
        if not res.first():
            logger.info("Seeding verified city emergency directory...")
            city_services = [
                ServiceDirectory(
                    scope="CITY_VERIFIED",
                    category="AMBULANCE",
                    name="108 Govt Emergency Medical Ambulance",
                    phone_number="108",
                    specialty_or_vehicle="Advanced Life Support Ambulance",
                    address_or_clinic="City Emergency Response Command",
                    is_favorite=True,
                    is_verified=True
                ),
                ServiceDirectory(
                    scope="CITY_VERIFIED",
                    category="HOSPITAL",
                    name="Apollo City Multi-Speciality Hospital",
                    phone_number="+914428290200",
                    specialty_or_vehicle="24x7 Emergency Trauma & Cardiology",
                    address_or_clinic="Greams Lane, Thousand Lights",
                    is_favorite=True,
                    is_verified=True
                ),
                ServiceDirectory(
                    scope="CITY_VERIFIED",
                    category="TAXI",
                    name="Senior City Rapid Taxi Dispatch",
                    phone_number="+914440005000",
                    specialty_or_vehicle="Wheelchair Accessible Sedan",
                    address_or_clinic="City Transport Hub",
                    is_favorite=False,
                    is_verified=True
                )
            ]
            session.add_all(city_services)
            await session.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    logger.info("Starting Elder Care Backend...")
    await init_db()
    await seed_city_directory()
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
    return {
        "status": "HEALTHY",
        "database": "CONNECTED",
        "watchdog_active": watchdog_engine.is_running
    }
