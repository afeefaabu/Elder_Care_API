import re
from typing import Optional
from pydantic import BaseModel, Field, model_validator

PHONE_REGEX = re.compile(r"^\+[1-9]\d{9,14}$")
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

class UnifiedOTPRequest(BaseModel):
    identifier: Optional[str] = Field(None, description="Mobile number with country code or email address")
    phone_number: Optional[str] = Field(None, description="Phone number alias")
    channel: str = Field(default="PHONE") # PHONE or EMAIL
    role: str = Field(default="CAREGIVER")

    @model_validator(mode="after")
    def validate_identifier(self) -> "UnifiedOTPRequest":
        if not self.identifier and self.phone_number:
            self.identifier = self.phone_number
        if not self.identifier:
            raise ValueError("Phone number or email identifier is required.")
        self.identifier = self.identifier.strip()
        if self.channel == "PHONE":
            if not PHONE_REGEX.match(self.identifier):
                raise ValueError("Invalid phone number format. Must start with country code (e.g. +91...).")
        elif self.channel == "EMAIL":
            if not EMAIL_REGEX.match(self.identifier.lower()):
                raise ValueError("Invalid email address format.")
            self.identifier = self.identifier.lower()
        return self

class OTPVerify(BaseModel):
    phone_number: str = Field(...)
    otp_code: str = Field(...)
    relationship: Optional[str] = Field(default="Family")
    full_name: Optional[str] = Field(default=None)

class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=128)
    registration_type: str = Field(default="PHONE") # PHONE or EMAIL
    phone_number: Optional[str] = Field(None)
    email: Optional[str] = Field(None)
    otp_code: str = Field(..., min_length=6, max_length=6)
    password: Optional[str] = Field(None, min_length=6, max_length=128)
    role: str = Field(default="CAREGIVER") # CAREGIVER, ELDER, ADMIN
    relationship_to_elder: Optional[str] = Field(default="Family")
    preferred_language: Optional[str] = Field(default="en")

    @model_validator(mode="after")
    def validate_registration(self) -> "UserRegisterRequest":
        if self.registration_type == "PHONE":
            if not self.phone_number or not PHONE_REGEX.match(self.phone_number.strip()):
                raise ValueError("Valid phone number with country code is required for phone registration.")
            self.phone_number = self.phone_number.strip()
        elif self.registration_type == "EMAIL":
            if not self.email or not EMAIL_REGEX.match(self.email.strip().lower()):
                raise ValueError("Valid email address is required for email registration.")
            self.email = self.email.strip().lower()
        return self

class UserLoginRequest(BaseModel):
    identifier: str = Field(...) # Phone or Email
    login_method: str = Field(default="OTP") # OTP or PASSWORD
    otp_code: Optional[str] = Field(None)
    password: Optional[str] = Field(None)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    full_name: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    relationship_to_elder: Optional[str] = None
