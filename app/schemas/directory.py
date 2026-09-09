from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class ServiceDirectoryCreate(BaseModel):
    elder_id: Optional[int] = None
    scope: str = Field(default="PERSONAL", example="PERSONAL") # PERSONAL or CITY_VERIFIED
    category: str = Field(..., example="DOCTOR") # DOCTOR, TAXI, HOSPITAL, AMBULANCE
    name: str = Field(..., example="Dr. R. Swaminathan (Diabetologist)")
    phone_number: str = Field(..., example="+919840123456")
    specialty_or_vehicle: Optional[str] = Field(None, example="Diabetologist")
    address_or_clinic: Optional[str] = Field(None, example="Apollo Clinic, T. Nagar")
    is_favorite: bool = Field(default=True)

class ServiceDirectoryResponse(BaseModel):
    id: int
    elder_id: Optional[int]
    scope: str
    category: str
    name: str
    phone_number: str
    specialty_or_vehicle: Optional[str]
    address_or_clinic: Optional[str]
    is_favorite: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True

class AppointmentCreate(BaseModel):
    elder_id: int
    directory_id: int
    requested_datetime: datetime
    notes: Optional[str] = Field(None, example="Routine 3-month sugar checkup")

class AppointmentResponse(BaseModel):
    id: int
    elder_id: int
    directory_id: int
    doctor_name: Optional[str] = None
    requested_datetime: datetime
    notes: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
