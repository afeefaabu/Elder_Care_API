from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


def _validate_alarm_times(alarm_times: List[str]) -> List[str]:
    if not alarm_times:
        raise ValueError("At least one alarm time is required")

    valid_times = []
    for alarm_time in alarm_times:
        try:
            datetime.strptime(alarm_time.strip(), "%H:%M")
        except (AttributeError, ValueError) as error:
            raise ValueError("Each alarm time must use 24-hour HH:MM format") from error
        valid_times.append(alarm_time.strip())
    return valid_times


class MedicationBase(BaseModel):
    name: str = Field(..., example="Metformin")
    dosage_type: str = Field(default="Tablet", example="Tablet")
    strength: str = Field(default="500 mg", example="500 mg")
    meal_relation: str = Field(default="After Food", example="After Food")
    alarm_times: List[str] = Field(..., min_length=1, example=["08:30", "20:30"])
    recurrence: str = Field(default="Daily", example="Daily")
    pill_photo_url: Optional[str] = Field(None)
    alarm_sound: str = Field(default="Loud Spoken Chime (90% Volume)")
    escalation_enabled: bool = Field(default=True)
    escalation_minutes: int = Field(default=25)
    is_critical: bool = Field(default=True)
    instructions: Optional[str] = Field(None, example="Take with full glass of water")

    @field_validator("alarm_times")
    @classmethod
    def validate_alarm_times(cls, alarm_times: List[str]) -> List[str]:
        return _validate_alarm_times(alarm_times)

class MedicationCreate(MedicationBase):
    elder_id: int

class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dosage_type: Optional[str] = None
    strength: Optional[str] = None
    meal_relation: Optional[str] = None
    alarm_times: Optional[List[str]] = None
    recurrence: Optional[str] = None
    pill_photo_url: Optional[str] = None
    alarm_sound: Optional[str] = None
    escalation_enabled: Optional[bool] = None
    escalation_minutes: Optional[int] = None
    is_critical: Optional[bool] = None
    instructions: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("alarm_times")
    @classmethod
    def validate_alarm_times(cls, alarm_times: Optional[List[str]]) -> Optional[List[str]]:
        return _validate_alarm_times(alarm_times) if alarm_times is not None else None

class MedicationResponse(BaseModel):
    id: int
    elder_id: int
    name: str
    dosage_type: str
    strength: str
    meal_relation: str
    alarm_times: List[str]
    recurrence: str
    pill_photo_url: Optional[str]
    alarm_sound: str
    escalation_enabled: bool
    escalation_minutes: int
    is_critical: bool
    instructions: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
