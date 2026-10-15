from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.core.security import create_access_token, require_elder
from app.models.user import User, HealthProfile
from app.models.pairing import ElderPairing
from app.models.routine import DailyRoutine
from app.models.medication import Medication
from app.models.adherence import AdherenceLog
from app.models.vitals import VitalsLog
from app.models.directory import ServiceDirectory
from app.models.sos import EmergencyContact, SOSEvent
from app.schemas.user import PairDeviceRequest
from app.schemas.routine import TodayScheduleItem
from app.services.adherence_service import adherence_broadcaster
from app.services.daily_medication_service import ensure_daily_medication_logs
from app.services.gemini_voice_service import gemini_voice_service

router = APIRouter(prefix="/elder", tags=["Elder Client Flow"])

class VoiceCommandRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


class VoiceCommandConfirmRequest(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    target_id: Optional[int] = None
    scheduled_slot: Optional[str] = Field(default=None, max_length=20)

@router.post("/pair-device")
async def pair_elder_device(payload: PairDeviceRequest, db: AsyncSession = Depends(get_db)):
    # 15-second code pairing
    stmt = select(ElderPairing).where(
        ElderPairing.pair_code == payload.pair_code.strip(),
        ElderPairing.status.in_(["PENDING", "ACTIVE"])
    )
    result = await db.execute(stmt)
    pairing = result.scalar_one_or_none()
    
    if not pairing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid 6-digit code. Please check with your family member."
        )
    
    pairing.status = "ACTIVE"
    pairing.device_fingerprint = payload.device_fingerprint
    
    # Fetch elder
    elder_stmt = select(User).where(User.id == pairing.elder_id)
    elder_res = await db.execute(elder_stmt)
    elder = elder_res.scalar_one()
    
    if payload.fcm_token:
        elder.fcm_token = payload.fcm_token
    if payload.preferred_language:
        elder.preferred_language = payload.preferred_language
        
    await db.commit()
    
    # Generate token for Elder client
    token = create_access_token({
        "sub": str(elder.id),
        "role": "ELDER",
        "name": elder.full_name,
        "phone_number": elder.phone_number
    })
    
    return {
        "status": "success",
        "elder_id": elder.id,
        "full_name": elder.full_name,
        "access_token": token,
        "spoken_welcome": f"Welcome {elder.full_name}! Your daily schedule and family network are connected.",
        "preferred_language": elder.preferred_language
    }

@router.get("/{elder_id}/today-schedule")
async def get_today_schedule(elder_id: int, db: AsyncSession = Depends(get_db)):
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Ensures each recurring medicine starts the day as a fresh pending dose.
    await ensure_daily_medication_logs(db, elder_id)
    
    # Combine routines + medications into chronological list
    r_stmt = select(DailyRoutine).where(DailyRoutine.elder_id == elder_id, DailyRoutine.is_active == True)
    r_res = await db.execute(r_stmt)
    routines = r_res.scalars().all()
    
    m_stmt = select(Medication).where(Medication.elder_id == elder_id, Medication.is_active == True)
    m_res = await db.execute(m_stmt)
    medications = m_res.scalars().all()
    
    # Dynamic completion checks
    # 1. Check completed medications for today
    adh_stmt = select(AdherenceLog).where(
        AdherenceLog.elder_id == elder_id,
        AdherenceLog.status.in_(["TAKEN", "VERIFIED_BY_CAREGIVER"]),
        AdherenceLog.scheduled_time >= today_start
    )
    adh_res = await db.execute(adh_stmt)
    adh_logs = adh_res.scalars().all()
    completed_med_slots = {(log.medication_id, log.scheduled_slot) for log in adh_logs}
    
    # 2. Check completed routines for today (recorded in VitalsLog with vital_type='ROUTINE')
    v_stmt = select(VitalsLog).where(
        VitalsLog.elder_id == elder_id,
        VitalsLog.vital_type == "ROUTINE",
        VitalsLog.measured_at >= today_start
    )
    v_res = await db.execute(v_stmt)
    v_logs = v_res.scalars().all()
    completed_routine_ids = {int(v.value_primary) for v in v_logs}
    
    schedule_items = []
    
    for r in routines:
        is_done = r.id in completed_routine_ids
        schedule_items.append({
            "time_str": r.time_str,
            "category": "ROUTINE",
            "title": r.title,
            "description": r.description,
            "voice_prompt": r.voice_prompt,
            "action_type": r.category,
            "reference_id": r.id,
            "is_completed": is_done
        })
        
    for m in medications:
        times = [t.strip() for t in m.alarm_times_csv.split(",") if t.strip()]
        for t in times:
            is_done = (m.id, t) in completed_med_slots
            schedule_items.append({
                "time_str": t,
                "category": "MEDICATION",
                "title": f"Take {m.name} ({m.strength})",
                "description": f"{m.meal_relation} • {m.dosage_type}",
                "voice_prompt": f"Time to take your {m.name} {m.dosage_type}. {m.meal_relation}.",
                "action_type": "PILL",
                "reference_id": m.id,
                "is_completed": is_done
            })
            
    # Sort chronologically by HH:MM
    schedule_items.sort(key=lambda x: x["time_str"])
    
    return {
        "elder_id": elder_id,
        "total_items": len(schedule_items),
        "schedule": schedule_items
    }

@router.post("/{elder_id}/routine/{routine_id}/complete")
async def complete_routine(elder_id: int, routine_id: int, db: AsyncSession = Depends(get_db)):
    r_stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id, DailyRoutine.elder_id == elder_id)
    r_res = await db.execute(r_stmt)
    routine = r_res.scalar_one_or_none()
    
    if not routine:
        raise HTTPException(status_code=404, detail="Routine item not found")
        
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Check if already logged today
    v_stmt = select(VitalsLog).where(
        VitalsLog.elder_id == elder_id,
        VitalsLog.vital_type == "ROUTINE",
        VitalsLog.value_primary == float(routine_id),
        VitalsLog.measured_at >= today_start
    )
    v_res = await db.execute(v_stmt)
    existing = v_res.scalar_one_or_none()
    
    if not existing:
        log = VitalsLog(
            elder_id=elder_id,
            vital_type="ROUTINE",
            value_primary=float(routine_id),
            context_label=routine.time_str,
            unit="milestone",
            classification="COMPLETED",
            notes=f"Confirmed routine: {routine.title}",
            measured_at=now,
            created_at=now
        )
        db.add(log)
        await db.commit()
    
    # Broadcast to Caregiver
    p_stmt = select(ElderPairing).where(ElderPairing.elder_id == elder_id, ElderPairing.status == "ACTIVE")
    p_res = await db.execute(p_stmt)
    pairings = p_res.scalars().all()
    
    for p in pairings:
        await adherence_broadcaster.broadcast_to_caregiver(
            caregiver_id=p.caregiver_id,
            event_type="ROUTINE_COMPLETED",
            payload={
                "elder_id": elder_id,
                "routine_id": routine_id,
                "title": routine.title,
                "time_str": routine.time_str,
                "message": f"Routine completed: {routine.title} at {routine.time_str}."
            }
        )

    await adherence_broadcaster.publish_elder_update(
        db, elder_id, "ROUTINE", "COMPLETED", routine_id=routine_id
    )
        
    return {
        "status": "success",
        "routine_id": routine_id,
        "title": routine.title,
        "message": f"Routine '{routine.title}' confirmed completed!"
    }


@router.post("/{elder_id}/routine/{routine_id}/undo")
async def undo_routine_completion(
    elder_id: int,
    routine_id: int,
    current_user: dict = Depends(require_elder),
    db: AsyncSession = Depends(get_db),
):
    """Remove today's routine-completion record after an accidental tap."""
    if current_user.get("role") != "ADMIN" and int(current_user.get("sub")) != elder_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An elder can change only their own routine schedule.",
        )

    r_stmt = select(DailyRoutine).where(
        DailyRoutine.id == routine_id,
        DailyRoutine.elder_id == elder_id,
    )
    r_res = await db.execute(r_stmt)
    routine = r_res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine item not found")

    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    completed_stmt = select(VitalsLog).where(
        VitalsLog.elder_id == elder_id,
        VitalsLog.vital_type == "ROUTINE",
        VitalsLog.value_primary == float(routine_id),
        VitalsLog.measured_at >= today_start,
    )
    completed_res = await db.execute(completed_stmt)
    completion_logs = completed_res.scalars().all()
    if not completion_logs:
        raise HTTPException(status_code=404, detail="No completed routine was found for today.")

    for completion_log in completion_logs:
        await db.delete(completion_log)
    await db.commit()

    await adherence_broadcaster.publish_elder_update(
        db, elder_id, "ROUTINE", "REVERTED", routine_id=routine_id
    )
    return {
        "status": "success",
        "routine_id": routine_id,
        "title": routine.title,
        "message": f"Routine '{routine.title}' is marked as not done.",
    }

def _assert_elder_voice_access(elder_id: int, current_user: dict) -> None:
    if current_user.get("role") != "ADMIN" and int(current_user.get("sub")) != elder_id:
        raise HTTPException(status_code=403, detail="You can use voice help only for your own care plan.")


async def _active_voice_data(db: AsyncSession, elder_id: int):
    medications = (await db.execute(select(Medication).where(
        Medication.elder_id == elder_id, Medication.is_active == True
    ))).scalars().all()
    routines = (await db.execute(select(DailyRoutine).where(
        DailyRoutine.elder_id == elder_id, DailyRoutine.is_active == True
    ))).scalars().all()
    directory = (await db.execute(select(ServiceDirectory).where(
        ServiceDirectory.elder_id == elder_id, ServiceDirectory.is_active == True
    ))).scalars().all()
    return medications, routines, directory


async def _pending_medicine(db: AsyncSession, elder_id: int, target_name: str = ""):
    await ensure_daily_medication_logs(db, elder_id)
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    medications, _, _ = await _active_voice_data(db, elder_id)
    candidates = []
    for medication in medications:
        for slot in [value.strip() for value in medication.alarm_times_csv.split(",") if value.strip()]:
            logs = (await db.execute(select(AdherenceLog).where(
                AdherenceLog.elder_id == elder_id,
                AdherenceLog.medication_id == medication.id,
                AdherenceLog.scheduled_slot == slot,
                AdherenceLog.scheduled_time >= today_start,
            ).order_by(AdherenceLog.id.desc()))).scalars().all()
            if not any(log.status in {"TAKEN", "VERIFIED_BY_CAREGIVER"} for log in logs):
                candidates.append((medication, slot))
    if target_name:
        matched = next((item for item in candidates if target_name.lower() in item[0].name.lower()), None)
        if matched:
            return matched
    return min(candidates, key=lambda item: item[1]) if candidates else None


async def _incomplete_routine(db: AsyncSession, elder_id: int, target_name: str = ""):
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    _, routines, _ = await _active_voice_data(db, elder_id)
    completed = set((await db.execute(select(VitalsLog.value_primary).where(
        VitalsLog.elder_id == elder_id,
        VitalsLog.vital_type == "ROUTINE",
        VitalsLog.measured_at >= today_start,
    ))).scalars().all())
    choices = [routine for routine in routines if float(routine.id) not in completed]
    if target_name:
        matched = next((item for item in choices if target_name.lower() in item.title.lower()), None)
        if matched:
            return matched
    return min(choices, key=lambda item: item.time_str) if choices else None


def _confirmation(action: str, title: str, *, target_id: Optional[int] = None, scheduled_slot: Optional[str] = None):
    return {
        "requires_confirmation": True,
        "confirmation": {
            "action": action,
            "title": title,
            "target_id": target_id,
            "scheduled_slot": scheduled_slot,
        },
    }


@router.post("/{elder_id}/voice-command")
async def handle_voice_command(
    elder_id: int,
    payload: VoiceCommandRequest,
    current_user: dict = Depends(require_elder),
    db: AsyncSession = Depends(get_db),
):
    """Interpret speech with Gemini, but never make a care change without a tap."""
    _assert_elder_voice_access(elder_id, current_user)
    medications, routines, directory = await _active_voice_data(db, elder_id)
    context = {
        "medicines": [{"name": m.name, "times": m.alarm_times_csv, "meal": m.meal_relation} for m in medications],
        "routines": [{"title": r.title, "time": r.time_str} for r in routines],
        "doctors": [d.name for d in directory if d.category == "DOCTOR"],
        "taxis": [d.name for d in directory if d.category == "TAXI"],
    }
    result = await gemini_voice_service.understand(payload.query.strip(), context)
    intent = result["intent"]
    reply = result["reply"]

    if intent == "EMERGENCY":
        return {"status": "success", "intent": intent, "spoken_response": reply, "show_sos": True, "requires_confirmation": False}
    if intent == "PENSION_STATUS":
        month_name = utc_now().strftime("%B %Y")
        return {"status": "success", "intent": intent, "spoken_response": f"Your pension status for {month_name} is available in Pension. Please check with your bank for the final confirmation.", "requires_confirmation": False}
    if intent == "NEXT_MEDICINE":
        candidate = await _pending_medicine(db, elder_id, result["target_name"])
        if not candidate:
            reply = "There are no medicines left to take today."
        else:
            medication, slot = candidate
            reply = f"Your next medicine is {medication.name} {medication.strength} at {slot}, {medication.meal_relation.lower()}."
        return {"status": "success", "intent": intent, "spoken_response": reply, "requires_confirmation": False}
    if intent == "LOG_WATER":
        return {"status": "success", "intent": intent, "spoken_response": "Would you like me to record one glass of water?", **_confirmation("LOG_WATER", "YES, RECORD ONE GLASS")}
    if intent == "TAKE_MEDICINE":
        candidate = await _pending_medicine(db, elder_id, result["target_name"])
        if not candidate:
            return {"status": "success", "intent": intent, "spoken_response": "All scheduled medicines are already marked as taken today.", "requires_confirmation": False}
        medication, slot = candidate
        return {"status": "success", "intent": intent, "spoken_response": f"Did you take {medication.name} {medication.strength} scheduled for {slot}?", **_confirmation("TAKE_MEDICINE", "YES, I TOOK IT", target_id=medication.id, scheduled_slot=slot)}
    if intent == "COMPLETE_ROUTINE":
        routine = await _incomplete_routine(db, elder_id, result["target_name"])
        if not routine:
            return {"status": "success", "intent": intent, "spoken_response": "All routines are already completed today.", "requires_confirmation": False}
        return {"status": "success", "intent": intent, "spoken_response": f"Did you complete {routine.title}?", **_confirmation("COMPLETE_ROUTINE", "YES, I COMPLETED IT", target_id=routine.id)}
    if intent in {"BOOK_TAXI", "CALL_DOCTOR"}:
        category = "TAXI" if intent == "BOOK_TAXI" else "DOCTOR"
        contact = next((entry for entry in directory if entry.category == category), None)
        if not contact:
            return {"status": "success", "intent": intent, "spoken_response": f"No trusted {category.lower()} contact is set up yet. Please ask your caregiver to add one.", "requires_confirmation": False}
        action = "CALL_TAXI" if category == "TAXI" else "CALL_DOCTOR"
        return {"status": "success", "intent": intent, "spoken_response": f"Would you like to call {contact.name}?", **_confirmation(action, f"CALL {contact.name.upper()}", target_id=contact.id)}
    return {"status": "success", "intent": "GENERAL", "spoken_response": reply, "requires_confirmation": False}


@router.post("/{elder_id}/voice-command/confirm")
async def confirm_voice_command(
    elder_id: int,
    payload: VoiceCommandConfirmRequest,
    current_user: dict = Depends(require_elder),
    db: AsyncSession = Depends(get_db),
):
    """Execute one validated action after the senior taps a clear confirmation."""
    _assert_elder_voice_access(elder_id, current_user)
    action = payload.action.upper()
    now = utc_now()

    if action == "LOG_WATER":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        latest_water = (await db.execute(
            select(VitalsLog).where(
                VitalsLog.elder_id == elder_id,
                VitalsLog.vital_type == "WATER",
                VitalsLog.measured_at >= today_start,
            ).order_by(VitalsLog.measured_at.desc()).limit(1)
        )).scalars().first()
        updated_glasses = (latest_water.value_primary if latest_water else 0) + 1
        db.add(VitalsLog(elder_id=elder_id, vital_type="WATER", value_primary=updated_glasses, context_label="HYDRATION", unit="glasses", classification="NORMAL", notes="Confirmed through Gemini voice assistant", measured_at=now, created_at=now))
        await db.commit()
        await adherence_broadcaster.publish_elder_update(db, elder_id, "VITAL", "CREATED")
        return {"status": "success", "spoken_response": f"One glass of water is recorded. You have {int(updated_glasses)} glasses today.", "requires_confirmation": False}

    if action == "TAKE_MEDICINE":
        candidate = await _pending_medicine(db, elder_id)
        if not candidate or candidate[0].id != payload.target_id or candidate[1] != payload.scheduled_slot:
            raise HTTPException(status_code=409, detail="That medicine is no longer waiting for confirmation. Please ask again.")
        medication, slot = candidate
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        logs = (await db.execute(select(AdherenceLog).where(AdherenceLog.elder_id == elder_id, AdherenceLog.medication_id == medication.id, AdherenceLog.scheduled_slot == slot, AdherenceLog.scheduled_time >= today_start).order_by(AdherenceLog.id.desc()))).scalars().all()
        log = next((entry for entry in logs if entry.status == "PENDING"), logs[0] if logs else None)
        if log is None:
            log = AdherenceLog(elder_id=elder_id, medication_id=medication.id, scheduled_slot=slot, scheduled_time=now, status="TAKEN", actual_time=now, notes="Confirmed through Gemini voice assistant")
            db.add(log)
        else:
            log.status, log.actual_time, log.notes = "TAKEN", now, "Confirmed through Gemini voice assistant"
        await db.commit()
        await adherence_broadcaster.broadcast_to_caregiver(caregiver_id=medication.caregiver_id, event_type="PILL_ADHERENCE_UPDATE", payload={"elder_id": elder_id, "medication_name": medication.name, "scheduled_slot": slot, "status": "TAKEN", "message": f"Dose confirmed: {medication.name} ({slot}) was marked taken by the senior."})
        await adherence_broadcaster.publish_elder_update(db, elder_id, "ADHERENCE", "UPDATED")
        return {"status": "success", "spoken_response": f"{medication.name} is marked as taken. Your caregiver can see the update.", "requires_confirmation": False}

    if action == "COMPLETE_ROUTINE":
        routine = await _incomplete_routine(db, elder_id)
        if not routine or routine.id != payload.target_id:
            raise HTTPException(status_code=409, detail="That routine is no longer waiting for confirmation. Please ask again.")
        return await complete_routine(elder_id, routine.id, db)

    if action in {"CALL_DOCTOR", "CALL_TAXI"}:
        category = "DOCTOR" if action == "CALL_DOCTOR" else "TAXI"
        _, _, directory = await _active_voice_data(db, elder_id)
        contact = next((entry for entry in directory if entry.id == payload.target_id and entry.category == category), None)
        if not contact:
            raise HTTPException(status_code=404, detail="That trusted contact is no longer available.")
        return {"status": "success", "spoken_response": f"Calling {contact.name} now.", "call_phone": contact.phone_number, "requires_confirmation": False}

    raise HTTPException(status_code=400, detail="That voice action is not supported.")
