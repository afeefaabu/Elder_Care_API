from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.core.security import require_elder
from app.models.adherence import AdherenceLog
from app.models.medication import Medication
from app.schemas.adherence import AdherenceLogCreate, AdherenceLogResponse, AdherenceUndoRequest
from app.services.adherence_service import adherence_broadcaster
from app.services.daily_medication_service import ensure_daily_medication_logs

router = APIRouter(prefix="/adherence", tags=["Adherence & Live Feed"])

@router.post("/log", response_model=AdherenceLogResponse)
async def log_adherence(
    payload: AdherenceLogCreate,
    current_user: dict = Depends(require_elder),
    db: AsyncSession = Depends(get_db),
):
    if current_user.get("role") != "ADMIN" and int(current_user.get("sub")) != payload.elder_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An elder can record medication only for their own schedule.",
        )

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
        .order_by(AdherenceLog.id.desc())
    )
    result = await db.execute(stmt)
    matching_logs = result.scalars().all()
    # A legacy edit can leave a missed log alongside a newer pending log for
    # the same daily dose. Always mark the current pending dose first.
    log = next((entry for entry in matching_logs if entry.status == "PENDING"), None)
    if log is None and matching_logs:
        log = matching_logs[0]
    
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
        await adherence_broadcaster.publish_elder_update(
            db, log.elder_id, "ADHERENCE", "UPDATED", adherence_id=log.id
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


@router.post("/undo", response_model=AdherenceLogResponse)
async def undo_adherence(
    payload: AdherenceUndoRequest,
    current_user: dict = Depends(require_elder),
    db: AsyncSession = Depends(get_db),
):
    """Return today's taken dose to its pending state after an accidental tap."""
    if current_user.get("role") != "ADMIN" and int(current_user.get("sub")) != payload.elder_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An elder can change only their own medication schedule.",
        )

    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(AdherenceLog)
        .where(
            AdherenceLog.elder_id == payload.elder_id,
            AdherenceLog.medication_id == payload.medication_id,
            AdherenceLog.scheduled_slot == payload.scheduled_slot,
            AdherenceLog.scheduled_time >= today_start,
            AdherenceLog.status.in_(["TAKEN", "VERIFIED_BY_CAREGIVER"]),
        )
        .order_by(AdherenceLog.id.desc())
    )
    result = await db.execute(stmt)
    log = result.scalars().first()
    if not log:
        raise HTTPException(status_code=404, detail="No completed dose was found for today.")

    log.status = "PENDING"
    log.actual_time = None
    log.photo_verification_url = None
    log.notes = "Marked as not taken by the senior."
    log.escalation_notified = False
    log.escalation_time = None
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
                "actual_time": None,
                "photo_url": None,
                "message": f"Dose changed: {med.name} ({log.scheduled_slot}) is pending again.",
            },
        )

    await adherence_broadcaster.publish_elder_update(
        db, log.elder_id, "ADHERENCE", "REVERTED", adherence_id=log.id
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
        created_at=log.created_at,
    )

@router.get("/timeline")
async def get_adherence_timeline(elder_id: int, db: AsyncSession = Depends(get_db)):
    await ensure_daily_medication_logs(db, elder_id)
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(AdherenceLog, Medication)
        .join(Medication, AdherenceLog.medication_id == Medication.id)
        .where(AdherenceLog.elder_id == elder_id, AdherenceLog.scheduled_time >= today_start)
        .order_by(AdherenceLog.scheduled_slot)
    )
    result = await db.execute(stmt)
    
    latest_by_dose = {}
    for log, med in result.all():
        key = (log.medication_id, log.scheduled_slot)
        current = latest_by_dose.get(key)
        if current is None or log.id > current[0].id:
            latest_by_dose[key] = (log, med)

    timeline = []
    for log, med in sorted(
        latest_by_dose.values(), key=lambda entry: (entry[0].scheduled_slot, entry[0].id)
    ):
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
