from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class EmergencyContactCreate(BaseModel):
    elder_id: int
    priority: int = Field(..., description="1: Family, 2: Neighbor, 3: Hospital")
    name: str = Field(...)
    relationship_label: str = Field(...)
    phone_number: Optional[str] = Field(None)
    email: Optional[str] = Field(None)

class EmergencyContactUpdate(BaseModel):
    priority: Optional[int] = None
    name: Optional[str] = None
    relationship_label: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None

class EmergencyContactResponse(BaseModel):
    id: int
    elder_id: int
    priority: int
    name: str
    relationship_label: str
    phone_number: Optional[str]
    email: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True

class SOSTriggerRequest(BaseModel):
    elder_id: int
    latitude: Optional[float] = Field(13.0827, example=13.0827)
    longitude: Optional[float] = Field(80.2707, example=80.2707)
    trigger_type: str = Field("BIG_RED_BUTTON", example="BIG_RED_BUTTON") # BIG_RED_BUTTON, FALL_DETECTED

class SOSTriggerResponse(BaseModel):
    sos_id: int
    status: str
    message: str
    google_maps_link: str
    broadcast_recipients: List[str]
    triggered_at: datetime

class SOSResolveRequest(BaseModel):
    sos_id: int
    resolved_by: str = Field(..., example="Ananya (Daughter)")
    notes: Optional[str] = Field(None, example="Verified elder is safe and conscious.")

class SOSEventResponse(BaseModel):
    id: int
    elder_id: int
    latitude: Optional[float]
    longitude: Optional[float]
    trigger_type: str
    status: str
    broadcast_summary: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]

    class Config:
        from_attributes = True
