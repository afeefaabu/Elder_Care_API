from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class AdherenceLogCreate(BaseModel):
    elder_id: int
    medication_id: int
    scheduled_slot: str = Field(..., example="08:30")
    status: str = Field(..., example="TAKEN") # TAKEN, SKIPPED
    photo_verification_url: Optional[str] = None
    notes: Optional[str] = None

class AdherenceLogResponse(BaseModel):
    id: int
    elder_id: int
    medication_id: int
    medication_name: Optional[str] = None
    scheduled_slot: str
    scheduled_time: datetime
    actual_time: Optional[datetime] = None
    status: str
    photo_verification_url: Optional[str] = None
    escalation_notified: bool
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class CaregiverVerifyPillRequest(BaseModel):
    adherence_id: int
    notes: Optional[str] = "Verified taken by daughter over phone call"

class AdherenceTimelineItem(BaseModel):
    adherence_id: int
    medication_id: int
    medication_name: str
    strength: str
    scheduled_slot: str
    status: str
    actual_time: Optional[datetime] = None
    pill_photo_url: Optional[str] = None
    escalation_alert_triggered: bool = False
