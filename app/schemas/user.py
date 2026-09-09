from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class ElderProvisionRequest(BaseModel):
    full_name: str = Field(..., example="Ramanathan")
    phone_number: Optional[str] = Field(None, example="+919876543212")
    age: int = Field(..., example=68)
    gender: str = Field("Male", example="Male")
    blood_group: Optional[str] = Field("O+", example="O+")
    chronic_conditions: str = Field("Type 2 Diabetes, High BP", example="Type 2 Diabetes, High BP")
    allergies: str = Field("Penicillin", example="Penicillin")
    dietary_restrictions: str = Field("Low-Sugar, Low-Salt, Vegetarian", example="Low-Sugar, Low-Salt, Vegetarian")
    pension_ppo_number: Optional[str] = Field("PPO-TN-2024-98124", example="PPO-TN-2024-98124")
    preferred_language: str = Field("en", example="en") # en, ta, hi

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
    phone_number: str
    full_name: str
    role: str
    preferred_language: str
    relationship_to_elder: Optional[str]
    health_profile: Optional[HealthProfileResponse] = None

    class Config:
        from_attributes = True
