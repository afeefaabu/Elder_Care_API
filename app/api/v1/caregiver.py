from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.core.security import get_current_user_payload, require_caregiver
from app.models.user import User, HealthProfile
from app.models.pairing import ElderPairing
from app.models.routine import DailyRoutine
from app.models.sos import EmergencyContact
from app.models.adherence import AdherenceLog
from app.schemas.user import ElderProvisionRequest, ElderProvisionResponse
from app.services.pairing_service import pairing_service

router = APIRouter(prefix="/caregiver", tags=["Caregiver Operations"])

@router.post("/create-elder", response_model=ElderProvisionResponse)
async def provision_elder(
    payload: ElderProvisionRequest,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db)
):
    caregiver_id = int(current_user.get("sub"))
    phone = payload.phone_number or f"+919900{datetime.now().strftime('%M%S%f')[:6]}"
    
    # 1. Look up existing elder user or create new one
    user_stmt = select(User).where(User.phone_number == phone)
    user_res = await db.execute(user_stmt)
    elder_user = user_res.scalar_one_or_none()
    
    if not elder_user:
        elder_user = User(
            phone_number=phone,
            full_name=payload.full_name,
            role="ELDER",
            preferred_language=payload.preferred_language,
            relationship_to_elder="Self"
        )
        db.add(elder_user)
        await db.flush()
    else:
        elder_user.full_name = payload.full_name
        elder_user.preferred_language = payload.preferred_language
        await db.flush()
    
    # 2. Look up or create health profile
    prof_stmt = select(HealthProfile).where(HealthProfile.user_id == elder_user.id)
    prof_res = await db.execute(prof_stmt)
    profile = prof_res.scalar_one_or_none()
    
    if not profile:
        profile = HealthProfile(
            user_id=elder_user.id,
            age=payload.age,
            gender=payload.gender,
            blood_group=payload.blood_group,
            chronic_conditions=payload.chronic_conditions,
            allergies=payload.allergies,
            dietary_restrictions=payload.dietary_restrictions,
            pension_ppo_number=payload.pension_ppo_number
        )
        db.add(profile)
    else:
        profile.age = payload.age
        profile.gender = payload.gender
        profile.blood_group = payload.blood_group
        profile.chronic_conditions = payload.chronic_conditions
        profile.allergies = payload.allergies
        profile.dietary_restrictions = payload.dietary_restrictions
        profile.pension_ppo_number = payload.pension_ppo_number
    
    # 3. Add default Emergency Contact (Priority 1 = This Caregiver) if not already added
    cg_stmt = select(User).where(User.id == caregiver_id)
    cg_res = await db.execute(cg_stmt)
    caregiver = cg_res.scalar_one()
    
    contact_stmt = select(EmergencyContact).where(
        EmergencyContact.elder_id == elder_user.id,
        EmergencyContact.priority == 1
    )
    c_res = await db.execute(contact_stmt)
    existing_contact = c_res.scalar_one_or_none()
    if not existing_contact:
        contact = EmergencyContact(
            elder_id=elder_user.id,
            priority=1,
            name=caregiver.full_name,
            relationship_label=caregiver.relationship_to_elder or "Family Caregiver",
            phone_number=caregiver.phone_number
        )
        db.add(contact)
    
    # 4. Populate standard 24-hour routine items if not present
    r_stmt = select(DailyRoutine).where(DailyRoutine.elder_id == elder_user.id)
    r_res = await db.execute(r_stmt)
    if not r_res.first():
        default_routines = [
            ("06:30", "WAKEUP", "Wake Up & Morning Stretch", "Gentle wake up bell", "Good morning Ramanathan, time to begin your day."),
            ("07:00", "HYDRATION", "Warm Water (1 Glass)", "Drink 1 glass warm water", "Please drink a glass of warm water."),
            ("08:00", "MEAL", "Diabetic Breakfast", "Low-sugar Oats or Idli", "Time for breakfast: Low sugar options."),
            ("11:00", "HYDRATION", "Mid-Morning Water & Fruit", "Drink water and have a fresh fruit", "Drink water and take your light snack."),
            ("13:00", "MEAL", "Low-Salt Lunch", "Nutritious vegetables & brown rice", "Lunch time: Low salt BP diet."),
            ("15:00", "HYDRATION", "Afternoon Hydration", "Drink water", "Afternoon water chime: keep yourself hydrated."),
            ("17:00", "MOBILITY", "Chair Yoga & Exercise", "15-Minute Chair Yoga Video", "Time for your 15-minute chair mobility exercise."),
            ("19:30", "MEAL", "Light Dinner", "Soup and Roti", "Dinner time: Have a light wholesome meal."),
            ("22:00", "BEDTIME", "Sleep Well Mode", "Bedtime soundscape & alarm ready", "Goodnight Ramanathan, sleep well. Alarms are set.")
        ]
        
        for time_str, cat, title, desc, voice in default_routines:
            routine = DailyRoutine(
                elder_id=elder_user.id,
                time_str=time_str,
                category=cat,
                title=title,
                description=desc,
                voice_prompt=voice
            )
            db.add(routine)
    
    # 5. Generate 6-digit pair code e.g. "729140"
    pairing = await pairing_service.create_pairing_code(db, caregiver_id=caregiver_id, elder_id=elder_user.id)
    
    return ElderProvisionResponse(
        elder_id=elder_user.id,
        full_name=elder_user.full_name,
        pair_code=pairing.pair_code,
        qr_payload=pairing.qr_payload,
        expires_at=pairing.expires_at,
        message="Elder provisioned successfully. Share this 6-digit code with your elder."
    )

@router.get("/elders")
async def list_caregiver_elders(
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db)
):
    caregiver_id = int(current_user.get("sub"))
    stmt = (
        select(User, HealthProfile, ElderPairing)
        .join(ElderPairing, User.id == ElderPairing.elder_id)
        .outerjoin(HealthProfile, User.id == HealthProfile.user_id)
        .where(ElderPairing.caregiver_id == caregiver_id)
    )
    result = await db.execute(stmt)
    elders_data = []
    for user, profile, pairing in result.all():
        elders_data.append({
            "elder_id": user.id,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "pairing_code": pairing.pair_code,
            "pairing_status": pairing.status,
            "chronic_conditions": profile.chronic_conditions if profile else None,
            "allergies": profile.allergies if profile else None,
            "dietary_restrictions": profile.dietary_restrictions if profile else None,
            "pension_ppo": profile.pension_ppo_number if profile else None,
        })
    return elders_data

@router.get("/dashboard/{elder_id}")
async def get_guardian_dashboard(
    elder_id: int,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db)
):
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    stmt = select(AdherenceLog).where(
        AdherenceLog.elder_id == elder_id,
        AdherenceLog.scheduled_time >= today_start
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    taken_count = sum(1 for l in logs if l.status in ["TAKEN", "VERIFIED_BY_CAREGIVER"])
    pending_count = sum(1 for l in logs if l.status == "PENDING")
    missed_count = sum(1 for l in logs if l.status == "MISSED_UNACKNOWLEDGED")
    
    return {
        "elder_id": elder_id,
        "total_scheduled_today": len(logs),
        "taken": taken_count,
        "pending": pending_count,
        "missed_unacknowledged": missed_count,
        "overall_status": "NORMAL" if missed_count == 0 else "ATTENTION_REQUIRED"
    }
