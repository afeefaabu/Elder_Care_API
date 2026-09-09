from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.models.directory import ServiceDirectory, AppointmentRequest
from app.models.user import User
from app.schemas.directory import (
    ServiceDirectoryCreate,
    ServiceDirectoryUpdate,
    ServiceDirectoryResponse,
    AppointmentCreate,
    AppointmentResponse,
    TaxiBookingRequest,
    TaxiBookingResponse
)
from app.services.telephony_service import telephony_service

router = APIRouter(prefix="/directory", tags=["Personal & City Service Directory"])

@router.post("/personal", response_model=ServiceDirectoryResponse)
async def add_personal_contact(payload: ServiceDirectoryCreate, db: AsyncSession = Depends(get_db)):
    entry = ServiceDirectory(
        elder_id=payload.elder_id,
        scope="PERSONAL",
        category=payload.category.upper(),
        name=payload.name,
        phone_number=payload.phone_number,
        specialty_or_vehicle=payload.specialty_or_vehicle,
        address_or_clinic=payload.address_or_clinic,
        is_favorite=payload.is_favorite,
        is_verified=True,
        created_at=utc_now()
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry

@router.get("/doctors", response_model=List[ServiceDirectoryResponse])
async def get_doctors(elder_id: int, db: AsyncSession = Depends(get_db)):
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

@router.get("/{entry_id}", response_model=ServiceDirectoryResponse)
async def get_directory_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(ServiceDirectory).where(ServiceDirectory.id == entry_id)
    res = await db.execute(stmt)
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Directory entry not found")
    return entry

@router.put("/{entry_id}", response_model=ServiceDirectoryResponse)
async def update_directory_entry(
    entry_id: int,
    payload: ServiceDirectoryUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(ServiceDirectory).where(ServiceDirectory.id == entry_id)
    res = await db.execute(stmt)
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Directory entry not found")
        
    if payload.category is not None:
        entry.category = payload.category.upper()
    if payload.name is not None:
        entry.name = payload.name
    if payload.phone_number is not None:
        entry.phone_number = payload.phone_number
    if payload.specialty_or_vehicle is not None:
        entry.specialty_or_vehicle = payload.specialty_or_vehicle
    if payload.address_or_clinic is not None:
        entry.address_or_clinic = payload.address_or_clinic
    if payload.is_favorite is not None:
        entry.is_favorite = payload.is_favorite
        
    await db.commit()
    await db.refresh(entry)
    return entry

@router.delete("/{entry_id}")
async def delete_directory_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(ServiceDirectory).where(ServiceDirectory.id == entry_id)
    res = await db.execute(stmt)
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Directory entry not found")
    await db.delete(entry)
    await db.commit()
    return {"status": "success", "message": f"Directory entry {entry_id} deleted successfully."}

@router.post("/request-appointment", response_model=AppointmentResponse)
async def request_appointment(payload: AppointmentCreate, db: AsyncSession = Depends(get_db)):
    dir_stmt = select(ServiceDirectory).where(ServiceDirectory.id == payload.directory_id)
    d_res = await db.execute(dir_stmt)
    doc = d_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    # Get elder name
    e_stmt = select(User).where(User.id == payload.elder_id)
    e_res = await db.execute(e_stmt)
    elder = e_res.scalar_one_or_none()
    elder_name = elder.full_name if elder else f"Elder #{payload.elder_id}"

    appointment = AppointmentRequest(
        elder_id=payload.elder_id,
        directory_id=payload.directory_id,
        requested_datetime=payload.requested_datetime,
        notes=payload.notes,
        status="PENDING",
        created_at=utc_now()
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    
    # Send real SMS notification to clinic desk
    formatted_dt = payload.requested_datetime.strftime('%Y-%m-%d %H:%M')
    sms_body = (
        f"APPOINTMENT REQUEST: Patient {elder_name} has requested a consultation with "
        f"{doc.name} for {formatted_dt}. "
        f"Notes: {payload.notes or 'None'}. Please call to confirm."
    )
    await telephony_service.send_sms(to_phone=doc.phone_number, body=sms_body)
    
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

@router.get("/appointments", response_model=List[AppointmentResponse])
async def list_appointments(elder_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(AppointmentRequest, ServiceDirectory.name.label("doctor_name"))
        .join(ServiceDirectory, AppointmentRequest.directory_id == ServiceDirectory.id)
        .where(AppointmentRequest.elder_id == elder_id)
        .order_by(desc(AppointmentRequest.created_at))
    )
    res = await db.execute(stmt)
    results = []
    for appt, doc_name in res.all():
        results.append(AppointmentResponse(
            id=appt.id,
            elder_id=appt.elder_id,
            directory_id=appt.directory_id,
            doctor_name=doc_name,
            requested_datetime=appt.requested_datetime,
            notes=appt.notes,
            status=appt.status,
            created_at=appt.created_at
        ))
    return results

@router.post("/book-taxi", response_model=TaxiBookingResponse)
async def book_taxi(payload: TaxiBookingRequest, db: AsyncSession = Depends(get_db)):
    dir_stmt = select(ServiceDirectory).where(ServiceDirectory.id == payload.taxi_directory_id)
    d_res = await db.execute(dir_stmt)
    driver = d_res.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Taxi/Driver not found")
        
    e_stmt = select(User).where(User.id == payload.elder_id)
    e_res = await db.execute(e_stmt)
    elder = e_res.scalar_one_or_none()
    elder_name = elder.full_name if elder else f"Elder #{payload.elder_id}"

    # Dispatch SMS to taxi driver
    sms_body = (
        f"?? CAB DISPATCH REQUEST: Pickup {elder_name} at {payload.pickup_address} -> "
        f"Destination: {payload.destination_address}. "
        f"Special instructions: {payload.notes or 'None'}."
    )
    await telephony_service.send_sms(to_phone=driver.phone_number, body=sms_body)
    
    return TaxiBookingResponse(
        status="DISPATCHED",
        message=f"Cab request dispatched to {driver.name} ({driver.phone_number}). Driver arriving shortly.",
        elder_id=payload.elder_id,
        driver_name=driver.name,
        driver_phone=driver.phone_number,
        pickup_address=payload.pickup_address,
        destination_address=payload.destination_address,
        dispatched_at=utc_now()
    )
