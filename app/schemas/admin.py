from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _normalise_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise ValueError("A valid email address is required.")
    return email


class AdminUserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=128)
    email: Optional[str] = None
    phone_number: Optional[str] = Field(None, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    role: Literal["CAREGIVER", "ELDER", "ADMIN"] = "CAREGIVER"
    relationship_to_elder: Optional[str] = Field(None, max_length=64)

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: Optional[str]) -> Optional[str]:
        return _normalise_email(value) if value else None


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=128)
    role: Optional[Literal["CAREGIVER", "ELDER", "ADMIN"]] = None
    is_active: Optional[bool] = None


class AdminConnectionCreate(BaseModel):
    caregiver_id: int
    elder_id: int
