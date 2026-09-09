from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.directory import ServiceDirectory, AppointmentRequest
from app.schemas.directory import (
    ServiceDirectoryCreate,
    ServiceDirectoryResponse,
    AppointmentCreate,
    AppointmentResponse
)
from app.services.telephony_service import telephony_service

router = APIRouter(prefix="/directory", tags=["Personal & City Service Directory"])

@router.post("/personal", response_model=ServiceDirectoryResponse)
async def add_personal_contact(payload: ServiceDirectoryCreate, db: AsyncSession = Depends(get_db)):
    entry = ServiceDirectory(
        elder_id=payload.elder_id,
        scope="PERSONAL",
        category=payload.category,
        name=payload.name,
        phone_number=payload.phone_number,
        specialty_or_vehicle=payload.specialty_or_vehicle,
        address_or_clinic=payload.address_or_clinic,
        is_favorite=payload.is_favorite,
        is_verified=True
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry

@router.get("/doctors", response_model=List[ServiceDirectoryResponse])
async def get_doctors(elder_id: int, db: AsyncSession = Depends(get_db)):
    # Returns elder's personal family doctors + admin city verified hospitals/doctors
    stmt = (
        select(ServiceDirectory)
        .where(
            ServiceDirectory.category.in_(["DOCTOR", "HOSPITAL"]),
            or_(
                ServiceDirectory.elder_id == elder_id,
                ServiceDirectory.scope == "CITY_VERIFIED"
            )
        )
        .order_by(ServiceDirectory.is_favorite.desc(), ServiceDirectory.name)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/taxis", response_model=List[ServiceDirectoryResponse])
async def get_taxis(elder_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ServiceDirectory)
        .where(
            ServiceDirectory.category.in_(["TAXI", "AMBULANCE"]),
            or_(
                ServiceDirectory.elder_id == elder_id,
                ServiceDirectory.scope == "CITY_VERIFIED"
            )
        )
        .order_by(ServiceDirectory.is_favorite.desc(), ServiceDirectory.name)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/request-appointment", response_model=AppointmentResponse)
async def request_appointment(payload: AppointmentCreate, db: AsyncSession = Depends(get_db)):
    dir_stmt = select(ServiceDirectory).where(ServiceDirectory.id == payload.directory_id)
    d_res = await db.execute(dir_stmt)
    doc = d_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    appointment = AppointmentRequest(
        elder_id=payload.elder_id,
        directory_id=payload.directory_id,
        requested_datetime=payload.requested_datetime,
        notes=payload.notes,
        status="PENDING"
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    
    # Send SMS notification to clinic desk
    await telephony_service.send_sms(
        to_phone=doc.phone_number,
        body=(
            f"APPOINTMENT REQUEST: Elder ID {payload.elder_id} requested consultation with "
            f"{doc.name} for {payload.requested_datetime.strftime('%Y-%m-%d %H:%M')}. "
            f"Notes: {payload.notes or 'None'}"
        )
    )
    
    return AppointmentResponse(
        id=appointment.id,
        elder_id=appointment.elder_id,
        directory_id=appointment.directory_id,
        doctor_name=doc.name,
        requested_datetime=appointment.requested_datetime,
        notes=appointment.notes,
        status=appointment.status,
        created_at=appointment.created_at
    )
