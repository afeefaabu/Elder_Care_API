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
from app.models.workout import SeniorWorkout
from app.schemas.user import PairDeviceRequest
from app.schemas.routine import TodayScheduleItem
from app.services.adherence_service import adherence_broadcaster
from app.services.daily_medication_service import ensure_daily_medication_logs
from app.services.gemini_voice_service import gemini_voice_service
from app.services.project_knowledge_service import project_knowledge_service

router = APIRouter(prefix="/elder", tags=["Elder Client Flow"])

class VoiceCommandRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    language: str = Field(default="en", min_length=2, max_length=10)


class VoiceCommandConfirmRequest(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    target_id: Optional[int] = None
    scheduled_slot: Optional[str] = Field(default=None, max_length=20)
    language: str = Field(default="en", min_length=2, max_length=10)

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


def _voice_language(language: str) -> str:
    return "ml" if language.casefold().startswith("ml") else "en"


def _voice_text(language: str, english: str, malayalam: str) -> str:
    return malayalam if language == "ml" else english


async def _active_voice_data(db: AsyncSession, elder_id: int):
    medications = (await db.execute(select(Medication).where(
        Medication.elder_id == elder_id, Medication.is_active == True
    ))).scalars().all()
    routines = (await db.execute(select(DailyRoutine).where(
        DailyRoutine.elder_id == elder_id, DailyRoutine.is_active == True
    ))).scalars().all()
    directory = (await db.execute(select(ServiceDirectory).where(
        ServiceDirectory.elder_id == elder_id
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


async def _next_activity(db: AsyncSession, elder_id: int):
    """Return the earliest outstanding medicine or routine for today's clear answer."""
    medicine = await _pending_medicine(db, elder_id)
    routine = await _incomplete_routine(db, elder_id)
    choices = []
    if medicine:
        medication, slot = medicine
        choices.append((slot, "MEDICINE", f"Take {medication.name} {medication.strength}", medication.meal_relation))
    if routine:
        choices.append((routine.time_str, "ROUTINE", routine.title, routine.description or ""))
    return min(choices, key=lambda item: item[0]) if choices else None


async def _next_workout(db: AsyncSession, elder_id: int):
    """Return the first active workout that is not completed today."""
    workouts = (await db.execute(select(SeniorWorkout).where(
        SeniorWorkout.elder_id == elder_id,
        SeniorWorkout.is_active == True,
    ))).scalars().all()
    today = utc_now().date()
    pending = [
        workout for workout in workouts
        if workout.last_completed_at is None or workout.last_completed_at.date() != today
    ]
    return min(pending, key=lambda workout: workout.scheduled_time) if pending else None


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
    language = _voice_language(payload.language)
    medications, routines, directory = await _active_voice_data(db, elder_id)
    workouts = (await db.execute(select(SeniorWorkout).where(
        SeniorWorkout.elder_id == elder_id, SeniorWorkout.is_active == True
    ))).scalars().all()
    profile = (await db.execute(select(HealthProfile).where(
        HealthProfile.user_id == elder_id
    ))).scalar_one_or_none()
    latest_vitals = (await db.execute(select(VitalsLog).where(
        VitalsLog.elder_id == elder_id,
        VitalsLog.vital_type.in_(["BLOOD_SUGAR", "BLOOD_PRESSURE", "PULSE"]),
    ).order_by(desc(VitalsLog.measured_at)).limit(6))).scalars().all()
    context = {
        "assistant_capabilities": [
            "today's next medicine, routine, and workout",
            "mark a medicine, water, or routine only after the senior confirms",
            "call a trusted doctor or taxi only after confirmation",
            "pension information available in the app",
            "emergency SOS guidance",
        ],
        "project_features": [
            "a simple senior home screen that shows the next daily step",
            "medicine alarms, taken doses, missed-dose safety watch, and caregiver updates",
            "daily routines, workouts, workout videos, and completed-activity history",
            "doctor, taxi, pension, health-vital, SOS, caregiver, senior, and administrator sections",
            "caregivers manage an elder's schedule; seniors confirm their own completion",
            "voice help supports English and Malayalam, with a typed fallback",
        ],
        "medicines": [{"name": m.name, "times": m.alarm_times_csv, "meal": m.meal_relation} for m in medications],
        "routines": [{"title": r.title, "time": r.time_str} for r in routines],
        "doctors": [d.name for d in directory if d.category == "DOCTOR"],
        "taxis": [d.name for d in directory if d.category == "TAXI"],
        "workouts": [{"title": w.title, "time": w.scheduled_time, "duration_minutes": w.duration_minutes} for w in workouts],
        "health_notes": {
            "allergies": profile.allergies if profile else None,
            "dietary_restrictions": profile.dietary_restrictions if profile else None,
        },
        "latest_vitals": [
            {"type": item.vital_type, "value": item.value_primary, "secondary": item.value_secondary, "unit": item.unit, "classification": item.classification}
            for item in latest_vitals
        ],
        "project_knowledge": project_knowledge_service.context_for(payload.query.strip()),
    }
    result = await gemini_voice_service.understand(payload.query.strip(), context, language)
    intent = result["intent"]
    reply = result["reply"]

    if intent == "EMERGENCY":
        return {"status": "success", "intent": intent, "spoken_response": reply, "show_sos": True, "requires_confirmation": False}
    if intent == "PENSION_STATUS":
        month_name = utc_now().strftime("%B %Y")
        reply = _voice_text(language, f"Your pension status for {month_name} is available in Pension. Please check with your bank for the final confirmation.", "നിങ്ങളുടെ പെൻഷൻ നില Pension വിഭാഗത്തിൽ ലഭ്യമാണ്. അന്തിമ സ്ഥിരീകരണത്തിനായി ബാങ്കുമായി പരിശോധിക്കുക.")
        return {"status": "success", "intent": intent, "spoken_response": reply, "requires_confirmation": False}
    if intent == "NEXT_MEDICINE":
        candidate = await _pending_medicine(db, elder_id, result["target_name"])
        if not candidate:
            reply = _voice_text(language, "There are no medicines left to take today.", "ഇന്ന് കഴിക്കാൻ ബാക്കിയുള്ള മരുന്നുകളൊന്നുമില്ല.")
        else:
            medication, slot = candidate
            reply = _voice_text(language, f"Your next medicine is {medication.name} {medication.strength} at {slot}, {medication.meal_relation.lower()}.", f"നിങ്ങളുടെ അടുത്ത മരുന്ന് {medication.name} {medication.strength} ആണ്. സമയം {slot}.")
        return {"status": "success", "intent": intent, "spoken_response": reply, "requires_confirmation": False}
    if intent == "NEXT_ACTIVITY":
        activity = await _next_activity(db, elder_id)
        if not activity:
            reply = _voice_text(language, "You have completed all medicines and routines for today.", "ഇന്നത്തെ എല്ലാ മരുന്നുകളും പ്രവർത്തനങ്ങളും പൂർത്തിയായി.")
        else:
            time_str, category, title, detail = activity
            detail_text = f" {detail}." if detail else ""
            reply = _voice_text(language, f"Your next {category.lower()} is {title} at {time_str}.{detail_text}", f"നിങ്ങളുടെ അടുത്ത പ്രവർത്തനം {title} ആണ്. സമയം {time_str}.")
        return {"status": "success", "intent": intent, "spoken_response": reply, "requires_confirmation": False}
    if intent == "NEXT_WORKOUT":
        workout = await _next_workout(db, elder_id)
        if not workout:
            reply = _voice_text(language, "All workouts are completed for today.", "ഇന്നത്തെ എല്ലാ വ്യായാമങ്ങളും പൂർത്തിയായി.")
            return {"status": "success", "intent": intent, "spoken_response": reply, "requires_confirmation": False}
        reply = _voice_text(language, f"Opening your next workout: {workout.title}, scheduled for {workout.scheduled_time}.", f"നിങ്ങളുടെ അടുത്ത വ്യായാമം തുറക്കുന്നു: {workout.title}. സമയം {workout.scheduled_time}.")
        return {
            "status": "success",
            "intent": intent,
            "spoken_response": reply,
            "navigate_to": "WORKOUT_PLAYER",
            "workout_id": workout.id,
            "requires_confirmation": False,
        }
    if intent == "LOG_WATER":
        return {"status": "success", "intent": intent, "spoken_response": _voice_text(language, "Would you like me to record one glass of water?", "ഒരു ഗ്ലാസ് വെള്ളം രേഖപ്പെടുത്തട്ടേ?"), **_confirmation("LOG_WATER", _voice_text(language, "YES, RECORD ONE GLASS", "അതെ, രേഖപ്പെടുത്തുക"))}
    if intent == "TAKE_MEDICINE":
        candidate = await _pending_medicine(db, elder_id, result["target_name"])
        if not candidate:
            return {"status": "success", "intent": intent, "spoken_response": _voice_text(language, "All scheduled medicines are already marked as taken today.", "ഇന്നത്തെ എല്ലാ നിശ്ചയിച്ച മരുന്നുകളും എടുത്തതായി രേഖപ്പെടുത്തിയിട്ടുണ്ട്."), "requires_confirmation": False}
        medication, slot = candidate
        return {"status": "success", "intent": intent, "spoken_response": _voice_text(language, f"Did you take {medication.name} {medication.strength} scheduled for {slot}?", f"{slot} സമയത്തേക്കുള്ള {medication.name} എടുത്തോ?"), **_confirmation("TAKE_MEDICINE", _voice_text(language, "YES, I TOOK IT", "അതെ, ഞാൻ എടുത്തു"), target_id=medication.id, scheduled_slot=slot)}
    if intent == "COMPLETE_ROUTINE":
        routine = await _incomplete_routine(db, elder_id, result["target_name"])
        if not routine:
            return {"status": "success", "intent": intent, "spoken_response": _voice_text(language, "All routines are already completed today.", "ഇന്നത്തെ എല്ലാ പ്രവർത്തനങ്ങളും പൂർത്തിയായി."), "requires_confirmation": False}
        return {"status": "success", "intent": intent, "spoken_response": _voice_text(language, f"Did you complete {routine.title}?", f"{routine.title} പൂർത്തിയാക്കിയോ?"), **_confirmation("COMPLETE_ROUTINE", _voice_text(language, "YES, I COMPLETED IT", "അതെ, പൂർത്തിയാക്കി"), target_id=routine.id)}
    if intent in {"BOOK_TAXI", "CALL_DOCTOR"}:
        category = "TAXI" if intent == "BOOK_TAXI" else "DOCTOR"
        contact = next((entry for entry in directory if entry.category == category), None)
        if not contact:
            return {"status": "success", "intent": intent, "spoken_response": _voice_text(language, f"No trusted {category.lower()} contact is set up yet. Please ask your caregiver to add one.", "ഇതിനായി വിശ്വസ്ത കോൺടാക്ട് ഇപ്പോഴും ചേർത്തിട്ടില്ല. പരിചരിക്കുന്നയാളോട് ചേർക്കാൻ പറയുക."), "requires_confirmation": False}
        action = "CALL_TAXI" if category == "TAXI" else "CALL_DOCTOR"
        return {"status": "success", "intent": intent, "spoken_response": _voice_text(language, f"Would you like to call {contact.name}?", f"{contact.name} നെ വിളിക്കണോ?"), **_confirmation(action, _voice_text(language, f"CALL {contact.name.upper()}", "വിളിക്കുക"), target_id=contact.id)}
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
    language = _voice_language(payload.language)
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
        reply = _voice_text(language, f"One glass of water is recorded. You have {int(updated_glasses)} glasses today.", f"ഒരു ഗ്ലാസ് വെള്ളം രേഖപ്പെടുത്തി. ഇന്ന് നിങ്ങൾ {int(updated_glasses)} ഗ്ലാസ് വെള്ളം കുടിച്ചു.")
        return {"status": "success", "spoken_response": reply, "requires_confirmation": False}

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
        reply = _voice_text(language, f"{medication.name} is marked as taken. Your caregiver can see the update.", f"{medication.name} എടുത്തതായി രേഖപ്പെടുത്തി. പരിചരിക്കുന്നയാൾക്ക് ഈ വിവരം കാണാം.")
        return {"status": "success", "spoken_response": reply, "requires_confirmation": False}

    if action == "COMPLETE_ROUTINE":
        routine = await _incomplete_routine(db, elder_id)
        if not routine or routine.id != payload.target_id:
            raise HTTPException(status_code=409, detail="That routine is no longer waiting for confirmation. Please ask again.")
        await complete_routine(elder_id, routine.id, db)
        reply = _voice_text(language, f"{routine.title} is marked as completed.", f"{routine.title} പൂർത്തിയായതായി രേഖപ്പെടുത്തി.")
        return {"status": "success", "spoken_response": reply, "requires_confirmation": False}

    if action in {"CALL_DOCTOR", "CALL_TAXI"}:
        category = "DOCTOR" if action == "CALL_DOCTOR" else "TAXI"
        _, _, directory = await _active_voice_data(db, elder_id)
        contact = next((entry for entry in directory if entry.id == payload.target_id and entry.category == category), None)
        if not contact:
            raise HTTPException(status_code=404, detail="That trusted contact is no longer available.")
        reply = _voice_text(language, f"Calling {contact.name} now.", f"ഇപ്പോൾ {contact.name} നെ വിളിക്കുന്നു.")
        return {"status": "success", "spoken_response": reply, "call_phone": contact.phone_number, "requires_confirmation": False}

    raise HTTPException(status_code=400, detail="That voice action is not supported.")
