import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.core.security import get_current_user_payload, require_caregiver
from app.models.medication import Medication
from app.models.adherence import AdherenceLog
from app.schemas.medication import MedicationCreate, MedicationResponse

router = APIRouter(prefix="/medications", tags=["Medications & Alarms"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("", response_model=MedicationResponse)
async def add_medication(
    payload: MedicationCreate,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db)
):
    caregiver_id = int(current_user.get("sub"))
    times_csv = ",".join(payload.alarm_times)
    
    med = Medication(
        elder_id=payload.elder_id,
        caregiver_id=caregiver_id,
        name=payload.name,
        dosage_type=payload.dosage_type,
        strength=payload.strength,
        meal_relation=payload.meal_relation,
        alarm_times_csv=times_csv,
        recurrence=payload.recurrence,
        pill_photo_url=payload.pill_photo_url,
        alarm_sound=payload.alarm_sound,
        escalation_enabled=payload.escalation_enabled,
        escalation_minutes=payload.escalation_minutes,
        is_critical=payload.is_critical,
        instructions=payload.instructions
    )
    db.add(med)
    await db.flush()
    
    now = utc_now()
    for slot in payload.alarm_times:
        try:
            hour, minute = map(int, slot.split(":"))
            scheduled_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except Exception:
            scheduled_dt = now
            
        log = AdherenceLog(
            elder_id=payload.elder_id,
            medication_id=med.id,
            scheduled_slot=slot,
            scheduled_time=scheduled_dt,
            status="PENDING"
        )
        db.add(log)
        
    await db.commit()
    await db.refresh(med)
    
    return MedicationResponse(
        id=med.id,
        elder_id=med.elder_id,
        name=med.name,
        dosage_type=med.dosage_type,
        strength=med.strength,
        meal_relation=med.meal_relation,
        alarm_times=payload.alarm_times,
        recurrence=med.recurrence,
        pill_photo_url=med.pill_photo_url,
        alarm_sound=med.alarm_sound,
        escalation_enabled=med.escalation_enabled,
        escalation_minutes=med.escalation_minutes,
        is_critical=med.is_critical,
        instructions=med.instructions,
        is_active=med.is_active,
        created_at=med.created_at
    )

@router.get("", response_model=List[MedicationResponse])
async def list_medications(elder_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Medication).where(Medication.elder_id == elder_id, Medication.is_active == True)
    result = await db.execute(stmt)
    meds = result.scalars().all()
    
    response = []
    for m in meds:
        response.append(MedicationResponse(
            id=m.id,
            elder_id=m.elder_id,
            name=m.name,
            dosage_type=m.dosage_type,
            strength=m.strength,
            meal_relation=m.meal_relation,
            alarm_times=[t.strip() for t in m.alarm_times_csv.split(",") if t.strip()],
            recurrence=m.recurrence,
            pill_photo_url=m.pill_photo_url,
            alarm_sound=m.alarm_sound,
            escalation_enabled=m.escalation_enabled,
            escalation_minutes=m.escalation_minutes,
            is_critical=m.is_critical,
            instructions=m.instructions,
            is_active=m.is_active,
            created_at=m.created_at
        ))
    return response

@router.post("/upload-photo")
async def upload_pill_photo(file: UploadFile = File(...)):
    filename = f"{utc_now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        "status": "success",
        "photo_url": f"/uploads/{filename}",
        "filename": filename
    }
