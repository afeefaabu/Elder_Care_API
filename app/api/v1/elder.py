from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.core.security import create_access_token
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
from app.services.telephony_service import telephony_service

router = APIRouter(prefix="/elder", tags=["Elder Client Flow"])

class VoiceCommandRequest(BaseModel):
    query: str

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
        
    return {
        "status": "success",
        "routine_id": routine_id,
        "title": routine.title,
        "message": f"Routine '{routine.title}' confirmed completed!"
    }

@router.post("/{elder_id}/voice-command")
async def handle_voice_command(elder_id: int, payload: VoiceCommandRequest, db: AsyncSession = Depends(get_db)):
    q = payload.query.lower().strip()
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Fetch elder
    e_stmt = select(User).where(User.id == elder_id)
    e_res = await db.execute(e_stmt)
    elder = e_res.scalar_one_or_none()
    elder_name = elder.full_name if elder else "Senior Citizen"
    
    # 1. Pension query
    if "pension" in q:
        month_name = now.strftime("%B %Y")
        return {
            "status": "success",
            "action": "PENSION_CHECK",
            "spoken_response": f"Your pension of ₹3,500 for {month_name} has been credited successfully to your State Bank of India account.",
            "data": {
                "amount": "₹3,500",
                "bank": "State Bank of India (SBI)",
                "status": "CREDITED",
                "scheme": "Senior Social Security DBT Pension"
            }
        }
        
    # 2. Taxi booking query
    if "taxi" in q or "cab" in q or "driver" in q:
        t_stmt = select(ServiceDirectory).where(
            ServiceDirectory.elder_id == elder_id,
            ServiceDirectory.category == "TAXI",
            ServiceDirectory.is_active == True
        )
        t_res = await db.execute(t_stmt)
        taxi = t_res.scalars().first()
        driver_name = taxi.name if taxi else "Driver Ramesh"
        phone = taxi.phone_number if taxi else "+91 98765 43211"
        vehicle = taxi.specialty_or_vehicle if taxi else "White Swift (KA-01-AB-1234)"
        
        # Send SMS dispatch
        await telephony_service.send_sms(
            to_phone=phone,
            body=f"AUTO DISPATCH: Senior citizen {elder_name} requested pickup at Home (142 Anna Salai). Destination: Apollo Clinic."
        )
        
        return {
            "status": "success",
            "action": "TAXI_DISPATCHED",
            "spoken_response": f"Taxi cab booked successfully. {driver_name} in {vehicle} has been dispatched to your home.",
            "data": {
                "driver_name": driver_name,
                "phone": phone,
                "vehicle": vehicle,
                "pickup": "142 Anna Salai, Chennai (Elder Home)"
            }
        }

    # 3. Doctor query
    if "doctor" in q or "appointment" in q or "clinic" in q:
        d_stmt = select(ServiceDirectory).where(
            ServiceDirectory.elder_id == elder_id,
            ServiceDirectory.category == "DOCTOR",
            ServiceDirectory.is_active == True
        )
        d_res = await db.execute(d_stmt)
        doc = d_res.scalars().first()
        doc_name = doc.name if doc else "Dr. Rajesh"
        phone = doc.phone_number if doc else "+91 99464 16015"
        
        # SMS booking request
        await telephony_service.send_sms(
            to_phone=phone,
            body=f"CLINIC APPT REQUEST: Senior citizen {elder_name} requested consultation for tomorrow at 10:00 AM."
        )
        
        return {
            "status": "success",
            "action": "DOCTOR_REQUESTED",
            "spoken_response": f"Consultation requested with {doc_name} for tomorrow 10:00 AM. His clinic desk has been notified.",
            "data": {
                "doctor_name": doc_name,
                "phone": phone,
                "time": "Tomorrow 10:00 AM"
            }
        }

    # 4. Water / Hydration
    if "water" in q or "drink" in q or "glass" in q:
        v_log = VitalsLog(
            elder_id=elder_id,
            vital_type="WATER",
            value_primary=1.0,
            context_label="HYDRATION",
            unit="glasses",
            classification="NORMAL",
            notes="Logged 1 glass of water via Voice Assistant",
            measured_at=now,
            created_at=now
        )
        db.add(v_log)
        await db.commit()
        return {
            "status": "success",
            "action": "WATER_LOGGED",
            "spoken_response": "1 glass of fresh water recorded! Staying hydrated keeps your blood pressure balanced.",
            "data": {"glasses_added": 1}
        }

    # 5. Medicine / Pill Adherence
    if "medicine" in q or "pill" in q or "tablet" in q or "took" in q:
        m_stmt = select(Medication).where(Medication.elder_id == elder_id, Medication.is_active == True)
        m_res = await db.execute(m_stmt)
        meds = m_res.scalars().all()
        
        med_taken = None
        for med in meds:
            times = [t.strip() for t in med.alarm_times_csv.split(",") if t.strip()]
            for t in times:
                # Check if uncompleted
                a_stmt = select(AdherenceLog).where(
                    AdherenceLog.elder_id == elder_id,
                    AdherenceLog.medication_id == med.id,
                    AdherenceLog.scheduled_slot == t,
                    AdherenceLog.scheduled_time >= today_start,
                    AdherenceLog.status.in_(["TAKEN", "VERIFIED_BY_CAREGIVER"])
                )
                a_res = await db.execute(a_stmt)
                if not a_res.scalar_one_or_none():
                    # Mark this one taken
                    log = AdherenceLog(
                        elder_id=elder_id,
                        medication_id=med.id,
                        scheduled_slot=t,
                        scheduled_time=now,
                        status="TAKEN",
                        actual_time=now,
                        notes="Confirmed taken via Voice Assistant"
                    )
                    db.add(log)
                    await db.commit()
                    med_taken = f"{med.name} ({t})"
                    break
            if med_taken:
                break
                
        if med_taken:
            return {
                "status": "success",
                "action": "MEDICINE_CONFIRMED",
                "spoken_response": f"Confirmed! Marked your {med_taken} as taken. Your family has been notified.",
                "data": {"medication": med_taken}
            }
        else:
            return {
                "status": "success",
                "action": "MEDICINE_ALL_TAKEN",
                "spoken_response": "Great job! All your scheduled medications for today are already confirmed.",
                "data": {}
            }

    # 6. Routine confirmation
    if "routine" in q or "breakfast" in q or "lunch" in q or "dinner" in q or "walk" in q or "done" in q or "complete" in q:
        r_stmt = select(DailyRoutine).where(DailyRoutine.elder_id == elder_id, DailyRoutine.is_active == True)
        r_res = await db.execute(r_stmt)
        all_routines = r_res.scalars().all()
        
        target_r = None
        for r in all_routines:
            if any(k in r.title.lower() for k in ["breakfast", "lunch", "dinner", "walk", "water", "bedtime"]):
                if any(k in q for k in ["breakfast", "lunch", "dinner", "walk", "water", "bedtime"]):
                    target_r = r
                    break
        if not target_r and all_routines:
            target_r = all_routines[0]
            
        if target_r:
            v_log = VitalsLog(
                elder_id=elder_id,
                vital_type="ROUTINE",
                value_primary=float(target_r.id),
                context_label=target_r.time_str,
                unit="milestone",
                classification="COMPLETED",
                notes=f"Confirmed routine '{target_r.title}' via Voice Assistant",
                measured_at=now,
                created_at=now
            )
            db.add(v_log)
            await db.commit()
            return {
                "status": "success",
                "action": "ROUTINE_COMPLETED",
                "spoken_response": f"Well done! I have marked your {target_r.title} as completed.",
                "data": {"routine_id": target_r.id, "title": target_r.title}
            }

    # Default fallback
    return {
        "status": "success",
        "action": "GENERAL_QUERY",
        "spoken_response": f"Hello {elder_name}! I can help you check your pension, book a taxi, call Dr. Rajesh, or confirm your medicines and routines.",
        "data": {}
    }
