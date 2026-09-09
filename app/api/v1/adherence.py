from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.models.adherence import AdherenceLog
from app.models.medication import Medication
from app.models.user import User
from app.schemas.adherence import AdherenceLogCreate, AdherenceLogResponse, CaregiverVerifyPillRequest
from app.services.adherence_service import adherence_broadcaster

router = APIRouter(prefix="/adherence", tags=["Adherence & Live Feed"])

@router.post("/log", response_model=AdherenceLogResponse)
async def log_adherence(payload: AdherenceLogCreate, db: AsyncSession = Depends(get_db)):
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    stmt = (
        select(AdherenceLog)
        .where(
            AdherenceLog.elder_id == payload.elder_id,
            AdherenceLog.medication_id == payload.medication_id,
            AdherenceLog.scheduled_slot == payload.scheduled_slot,
            AdherenceLog.scheduled_time >= today_start
        )
    )
    result = await db.execute(stmt)
    log = result.scalar_one_or_none()
    
    if not log:
        log = AdherenceLog(
            elder_id=payload.elder_id,
            medication_id=payload.medication_id,
            scheduled_slot=payload.scheduled_slot,
            scheduled_time=now,
            status=payload.status,
            actual_time=now,
            photo_verification_url=payload.photo_verification_url,
            notes=payload.notes
        )
        db.add(log)
    else:
        log.status = payload.status
        log.actual_time = now
        log.photo_verification_url = payload.photo_verification_url
        log.notes = payload.notes
        
    await db.commit()
    await db.refresh(log)
    
    med_stmt = select(Medication).where(Medication.id == log.medication_id)
    med_res = await db.execute(med_stmt)
    med = med_res.scalar_one_or_none()
    
    if med:
        await adherence_broadcaster.broadcast_to_caregiver(
            caregiver_id=med.caregiver_id,
            event_type="PILL_ADHERENCE_UPDATE",
            payload={
                "adherence_id": log.id,
                "elder_id": log.elder_id,
                "medication_name": med.name,
                "strength": med.strength,
                "scheduled_slot": log.scheduled_slot,
                "status": log.status,
                "actual_time": log.actual_time.isoformat() if log.actual_time else None,
                "photo_url": log.photo_verification_url,
                "message": f"Dose confirmed: {med.name} ({log.scheduled_slot}) marked as {log.status}."
            }
        )
        
    return AdherenceLogResponse(
        id=log.id,
        elder_id=log.elder_id,
        medication_id=log.medication_id,
        medication_name=med.name if med else "Medicine",
        scheduled_slot=log.scheduled_slot,
        scheduled_time=log.scheduled_time,
        actual_time=log.actual_time,
        status=log.status,
        photo_verification_url=log.photo_verification_url,
        escalation_notified=log.escalation_notified,
        notes=log.notes,
        created_at=log.created_at
    )

@router.post("/verify-by-caregiver")
async def verify_by_caregiver(payload: CaregiverVerifyPillRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(AdherenceLog).where(AdherenceLog.id == payload.adherence_id)
    res = await db.execute(stmt)
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Adherence log not found")
        
    log.status = "VERIFIED_BY_CAREGIVER"
    log.notes = payload.notes
    log.actual_time = utc_now()
    await db.commit()
    return {"status": "success", "message": "Medication marked as verified taken by caregiver."}

@router.get("/timeline")
async def get_adherence_timeline(elder_id: int, db: AsyncSession = Depends(get_db)):
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(AdherenceLog, Medication)
        .join(Medication, AdherenceLog.medication_id == Medication.id)
        .where(AdherenceLog.elder_id == elder_id, AdherenceLog.scheduled_time >= today_start)
        .order_by(AdherenceLog.scheduled_slot)
    )
    result = await db.execute(stmt)
    
    timeline = []
    for log, med in result.all():
        timeline.append({
            "adherence_id": log.id,
            "medication_id": med.id,
            "medication_name": med.name,
            "strength": med.strength,
            "dosage_type": med.dosage_type,
            "meal_relation": med.meal_relation,
            "scheduled_slot": log.scheduled_slot,
            "status": log.status,
            "actual_time": log.actual_time,
            "pill_photo_url": med.pill_photo_url,
            "escalation_alert_triggered": log.escalation_notified
        })
    return {"elder_id": elder_id, "timeline": timeline}
