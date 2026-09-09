from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class VitalsLogCreate(BaseModel):
    elder_id: int
    vital_type: str = Field(..., example="BLOOD_SUGAR")  # BLOOD_SUGAR, BLOOD_PRESSURE, PULSE
    value_primary: float = Field(..., example=124.0)     # Sugar mg/dL or BP Systolic
    value_secondary: Optional[float] = Field(None, example=84.0) # BP Diastolic
    context_label: Optional[str] = Field("FASTING", example="FASTING") # FASTING, POST_PRANDIAL, RANDOM, RESTING
    unit: Optional[str] = Field("mg/dL", example="mg/dL")
    notes: Optional[str] = Field(None, example="Morning test before breakfast")
    measured_at: Optional[datetime] = None

class VitalsLogResponse(BaseModel):
    id: int
    elder_id: int
    vital_type: str
    value_primary: float
    value_secondary: Optional[float] = None
    context_label: Optional[str] = None
    unit: str
    classification: str
    notes: Optional[str] = None
    measured_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

class VitalsSummaryResponse(BaseModel):
    elder_id: int
    latest_blood_sugar: Optional[VitalsLogResponse] = None
    latest_blood_pressure: Optional[VitalsLogResponse] = None
    overall_vitals_status: str = "NORMAL"
