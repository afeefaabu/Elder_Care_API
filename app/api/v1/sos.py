from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.models.sos import EmergencyContact, SOSEvent
from app.models.user import User
from app.schemas.sos import (
    EmergencyContactCreate,
    EmergencyContactResponse,
    SOSTriggerRequest,
    SOSTriggerResponse,
    SOSResolveRequest
)
from app.services.telephony_service import telephony_service
from app.services.adherence_service import adherence_broadcaster

router = APIRouter(prefix="/sos", tags=["Emergency SOS Pipeline"])

@router.post("/trigger", response_model=SOSTriggerResponse)
async def trigger_emergency_sos(payload: SOSTriggerRequest, db: AsyncSession = Depends(get_db)):
    e_stmt = select(User).where(User.id == payload.elder_id)
    e_res = await db.execute(e_stmt)
    elder = e_res.scalar_one_or_none()
    elder_name = elder.full_name if elder else "Elder"
    
    maps_link = f"https://maps.google.com/?q={payload.latitude},{payload.longitude}"
    sos_event = SOSEvent(
        elder_id=payload.elder_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        trigger_type=payload.trigger_type,
        status="ACTIVE",
        created_at=utc_now()
    )
    db.add(sos_event)
    await db.flush()
    
    c_stmt = (
        select(EmergencyContact)
        .where(EmergencyContact.elder_id == payload.elder_id, EmergencyContact.is_active == True)
        .order_by(EmergencyContact.priority)
    )
    c_res = await db.execute(c_stmt)
    contacts = c_res.scalars().all()
    
    recipients = []
    for contact in contacts:
        alert_body = (
            f"🚨 CRITICAL EMERGENCY SOS: {elder_name} has triggered an Emergency Alarm! "
            f"Type: {payload.trigger_type}. "
            f"Live Location: {maps_link}. "
            f"Please respond immediately!"
        )
        await telephony_service.send_sms(to_phone=contact.phone_number, body=alert_body)
        recipients.append(f"{contact.relationship_label} ({contact.phone_number})")
        
    from app.models.pairing import ElderPairing
    p_stmt = select(ElderPairing).where(ElderPairing.elder_id == payload.elder_id)
    p_res = await db.execute(p_stmt)
    pairings = p_res.scalars().all()
    
    for p in pairings:
        await adherence_broadcaster.broadcast_to_caregiver(
            caregiver_id=p.caregiver_id,
            event_type="EMERGENCY_SOS_RED_ALERT",
            payload={
                "sos_id": sos_event.id,
                "elder_id": payload.elder_id,
                "elder_name": elder_name,
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "maps_link": maps_link,
                "trigger_type": payload.trigger_type,
                "timestamp": sos_event.created_at.isoformat(),
                "alarm_state": "CRITICAL_SIREN"
            }
        )
        
    sos_event.broadcast_summary = f"Alerted {len(recipients)} contacts."
    await db.commit()
    await db.refresh(sos_event)
    
    return SOSTriggerResponse(
        sos_id=sos_event.id,
        status="ACTIVE",
        message=f"SOS triggered. High-priority sirens and SMS dispatched to {len(recipients)} emergency contacts.",
        google_maps_link=maps_link,
        broadcast_recipients=recipients,
        triggered_at=sos_event.created_at
    )

@router.post("/resolve")
async def resolve_emergency_sos(payload: SOSResolveRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(SOSEvent).where(SOSEvent.id == payload.sos_id)
    res = await db.execute(stmt)
    sos = res.scalar_one_or_none()
    if not sos:
        raise HTTPException(status_code=404, detail="SOS event not found")
        
    sos.status = "RESOLVED"
    sos.resolved_at = utc_now()
    sos.resolved_by = payload.resolved_by
    await db.commit()
    
    return {"status": "success", "message": f"SOS {payload.sos_id} marked as resolved by {payload.resolved_by}."}

@router.get("/contacts", response_model=List[EmergencyContactResponse])
async def get_emergency_contacts(elder_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(EmergencyContact)
        .where(EmergencyContact.elder_id == elder_id, EmergencyContact.is_active == True)
        .order_by(EmergencyContact.priority)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/contacts", response_model=EmergencyContactResponse)
async def add_emergency_contact(payload: EmergencyContactCreate, db: AsyncSession = Depends(get_db)):
    contact = EmergencyContact(
        elder_id=payload.elder_id,
        priority=payload.priority,
        name=payload.name,
        relationship_label=payload.relationship_label,
        phone_number=payload.phone_number
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact
