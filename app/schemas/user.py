from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class ElderProvisionRequest(BaseModel):
    full_name: str = Field(..., example="Senior Citizen Name")
    phone_number: Optional[str] = Field(None, example="+919876543212")
    age: int = Field(..., example=70)
    gender: Optional[str] = Field(None, example="Male")
    blood_group: Optional[str] = Field(None, example="O+")
    chronic_conditions: Optional[str] = Field(None, example="None or list conditions")
    allergies: Optional[str] = Field(None, example="None or list allergies")
    dietary_restrictions: Optional[str] = Field(None, example="Regular or special diet")
    pension_ppo_number: Optional[str] = Field(None, example="PPO-XXXX-XXXXX")
    preferred_language: str = Field("en", example="en") # en, ta, hi

class ElderProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    chronic_conditions: Optional[str] = None
    allergies: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    pension_ppo_number: Optional[str] = None
    preferred_language: Optional[str] = None

class ElderProvisionResponse(BaseModel):
    elder_id: int
    full_name: str
    pair_code: str # e.g. "729140"
    qr_payload: str
    expires_at: datetime
    message: str

class PairDeviceRequest(BaseModel):
    pair_code: str = Field(..., example="729140")
    device_fingerprint: Optional[str] = Field(None, example="Samsung A14 - 4G")
    fcm_token: Optional[str] = Field(None)
    preferred_language: Optional[str] = Field("en")

class HealthProfileResponse(BaseModel):
    id: int
    age: Optional[int]
    gender: Optional[str]
    blood_group: Optional[str]
    chronic_conditions: Optional[str]
    allergies: Optional[str]
    dietary_restrictions: Optional[str]
    pension_ppo_number: Optional[str]

    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    id: int
    phone_number: Optional[str] = None
    full_name: str
    role: str
    preferred_language: str
    relationship_to_elder: Optional[str]
    health_profile: Optional[HealthProfileResponse] = None

    class Config:
        from_attributes = True
