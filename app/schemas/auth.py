from typing import Optional
from pydantic import BaseModel, Field

class OTPRequest(BaseModel):
    phone_number: str = Field(..., example="+919876543210")
    role: str = Field(default="CAREGIVER", example="CAREGIVER") # CAREGIVER, ELDER, ADMIN

class OTPVerify(BaseModel):
    phone_number: str = Field(..., example="+919876543210")
    otp_code: str = Field(..., example="123456")
    relationship: Optional[str] = Field(default="Daughter", example="Daughter")
    full_name: Optional[str] = Field(default="Ananya", example="Ananya")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    phone_number: str
    full_name: str
