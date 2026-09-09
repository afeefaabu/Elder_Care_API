from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User, HealthProfile
from app.models.pairing import ElderPairing
from app.models.routine import DailyRoutine
from app.models.medication import Medication
from app.models.sos import EmergencyContact
from app.schemas.user import PairDeviceRequest
from app.schemas.routine import TodayScheduleItem

router = APIRouter(prefix="/elder", tags=["Elder Client Flow"])

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
    # Combine routines + medications into chronological list
    r_stmt = select(DailyRoutine).where(DailyRoutine.elder_id == elder_id, DailyRoutine.is_active == True)
    r_res = await db.execute(r_stmt)
    routines = r_res.scalars().all()
    
    m_stmt = select(Medication).where(Medication.elder_id == elder_id, Medication.is_active == True)
    m_res = await db.execute(m_stmt)
    medications = m_res.scalars().all()
    
    schedule_items = []
    
    for r in routines:
        schedule_items.append({
            "time_str": r.time_str,
            "category": "ROUTINE",
            "title": r.title,
            "description": r.description,
            "voice_prompt": r.voice_prompt,
            "action_type": r.category,
            "reference_id": r.id,
            "is_completed": False
        })
        
    for m in medications:
        times = [t.strip() for t in m.alarm_times_csv.split(",") if t.strip()]
        for t in times:
            schedule_items.append({
                "time_str": t,
                "category": "MEDICATION",
                "title": f"Take {m.name} ({m.strength})",
                "description": f"{m.meal_relation} • {m.dosage_type}",
                "voice_prompt": f"Time to take your {m.name} {m.dosage_type}. {m.meal_relation}.",
                "action_type": "PILL",
                "reference_id": m.id,
                "is_completed": False
            })
            
    # Sort chronologically by HH:MM
    schedule_items.sort(key=lambda x: x["time_str"])
    
    return {
        "elder_id": elder_id,
        "total_items": len(schedule_items),
        "schedule": schedule_items
    }
