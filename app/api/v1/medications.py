import os
import secrets
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.core.security import get_current_user_payload, require_caregiver
from app.models.medication import Medication
from app.models.adherence import AdherenceLog
from app.schemas.medication import MedicationCreate, MedicationUpdate, MedicationResponse
from app.services.adherence_service import adherence_broadcaster
from app.services.access_control_service import require_care_plan_management, require_elder_access

router = APIRouter(prefix="/medications", tags=["Medications & Alarms"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_PILL_PHOTO_BYTES = 5 * 1024 * 1024


async def _save_pill_photo(file: UploadFile, destination: str) -> None:
    """Persist a small validated image without buffering an unbounded upload."""
    written = 0
    try:
        with open(destination, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_PILL_PHOTO_BYTES:
                    raise HTTPException(status_code=413, detail="Pill photos must be 5 MB or smaller.")
                buffer.write(chunk)
    except Exception:
        if os.path.exists(destination):
            os.remove(destination)
        raise
    finally:
        await file.close()

def _to_response(m: Medication) -> MedicationResponse:
    times = [t.strip() for t in m.alarm_times_csv.split(",") if t.strip()]
    return MedicationResponse(
        id=m.id,
        elder_id=m.elder_id,
        name=m.name,
        dosage_type=m.dosage_type,
        strength=m.strength,
        meal_relation=m.meal_relation,
        alarm_times=times,
        recurrence=m.recurrence,
        pill_photo_url=m.pill_photo_url,
        alarm_sound=m.alarm_sound,
        escalation_enabled=m.escalation_enabled,
        escalation_minutes=m.escalation_minutes,
        is_critical=m.is_critical,
        instructions=m.instructions,
        is_active=m.is_active,
        created_at=m.created_at
    )

@router.post("", response_model=MedicationResponse)
async def add_medication(
    payload: MedicationCreate,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db)
):
    await require_care_plan_management(db, current_user, payload.elder_id)
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
    await adherence_broadcaster.publish_elder_update(
        db, med.elder_id, "MEDICATION", "CREATED", medication_id=med.id
    )
    return _to_response(med)

@router.get("", response_model=List[MedicationResponse])
async def list_medications(
    elder_id: int,
    current_user: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    await require_elder_access(db, current_user, elder_id)
    stmt = select(Medication).where(Medication.elder_id == elder_id, Medication.is_active == True)
    result = await db.execute(stmt)
    meds = result.scalars().all()
    return [_to_response(m) for m in meds]

@router.put("/{med_id}", response_model=MedicationResponse)
async def update_medication(
    med_id: int,
    payload: MedicationUpdate,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Medication).where(Medication.id == med_id)
    res = await db.execute(stmt)
    med = res.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")
    await require_care_plan_management(db, current_user, med.elder_id)
        
    if payload.name is not None:
        med.name = payload.name
    if payload.dosage_type is not None:
        med.dosage_type = payload.dosage_type
    if payload.strength is not None:
        med.strength = payload.strength
    if payload.meal_relation is not None:
        med.meal_relation = payload.meal_relation
    if payload.recurrence is not None:
        med.recurrence = payload.recurrence
    if payload.pill_photo_url is not None:
        med.pill_photo_url = payload.pill_photo_url
    if payload.alarm_sound is not None:
        med.alarm_sound = payload.alarm_sound
    if payload.escalation_enabled is not None:
        med.escalation_enabled = payload.escalation_enabled
    if payload.escalation_minutes is not None:
        med.escalation_minutes = payload.escalation_minutes
    if payload.is_critical is not None:
        med.is_critical = payload.is_critical
    if payload.instructions is not None:
        med.instructions = payload.instructions
    if payload.is_active is not None:
        med.is_active = payload.is_active

    if payload.alarm_times is not None:
        med.alarm_times_csv = ",".join(payload.alarm_times)
        # Update today pending adherence logs
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        del_stmt = delete(AdherenceLog).where(
            AdherenceLog.medication_id == med.id,
            AdherenceLog.status == "PENDING",
            AdherenceLog.scheduled_time >= today_start
        )
        await db.execute(del_stmt)

        existing_slots_stmt = select(AdherenceLog.scheduled_slot).where(
            AdherenceLog.medication_id == med.id,
            AdherenceLog.scheduled_time >= today_start,
        )
        existing_slots_result = await db.execute(existing_slots_stmt)
        existing_slots = set(existing_slots_result.scalars().all())
        
        now = utc_now()
        for slot in payload.alarm_times:
            if slot in existing_slots:
                continue
            try:
                hour, minute = map(int, slot.split(":"))
                scheduled_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except Exception:
                scheduled_dt = now
            log = AdherenceLog(
                elder_id=med.elder_id,
                medication_id=med.id,
                scheduled_slot=slot,
                scheduled_time=scheduled_dt,
                status="PENDING"
            )
            db.add(log)
            existing_slots.add(slot)

    await db.commit()
    await db.refresh(med)
    await adherence_broadcaster.publish_elder_update(
        db, med.elder_id, "MEDICATION", "UPDATED", medication_id=med.id
    )
    return _to_response(med)

@router.delete("/{med_id}")
async def delete_medication(
    med_id: int,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Medication).where(Medication.id == med_id)
    res = await db.execute(stmt)
    med = res.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")
    await require_care_plan_management(db, current_user, med.elder_id)
        
    elder_id = med.elder_id
    await db.delete(med)
    await db.commit()
    await adherence_broadcaster.publish_elder_update(
        db, elder_id, "MEDICATION", "DELETED", medication_id=med_id
    )
    return {"status": "success", "message": f"Medication {med_id} deleted successfully."}

@router.post("/upload-photo")
async def upload_pill_photo(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_caregiver),
):
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    safe_name = os.path.basename(file.filename)
    if os.path.splitext(safe_name)[1].lower() not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, and WEBP images are allowed.")
    extension = os.path.splitext(safe_name)[1].lower()
    filename = f"pill_{secrets.token_hex(16)}{extension}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    await _save_pill_photo(file, filepath)
    return {
        "status": "success",
        "photo_url": f"/uploads/{filename}",
        "filename": filename
    }


@router.get("/{med_id}", response_model=MedicationResponse)
async def get_medication(
    med_id: int,
    current_user: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Medication).where(Medication.id == med_id)
    res = await db.execute(stmt)
    med = res.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")
    await require_elder_access(db, current_user, med.elder_id)
    return _to_response(med)
