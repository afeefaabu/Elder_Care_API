from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class DailyRoutineCreate(BaseModel):
    elder_id: int
    time_str: str = Field(..., example="07:00")
    category: str = Field(..., example="HYDRATION") # WAKEUP, HYDRATION, MEAL, MOBILITY, BEDTIME
    title: str = Field(..., example="Warm Water")
    description: Optional[str] = Field(None, example="Drink 1 glass warm water")
    voice_prompt: Optional[str] = Field(None, example="Good morning Ramanathan, please drink one glass of warm water.")
    target_metric: Optional[str] = Field(None, example="250 ml")

class DailyRoutineUpdate(BaseModel):
    time_str: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    voice_prompt: Optional[str] = None
    target_metric: Optional[str] = None
    is_active: Optional[bool] = None

class DailyRoutineResponse(BaseModel):
    id: int
    elder_id: int
    time_str: str
    category: str
    title: str
    description: Optional[str]
    voice_prompt: Optional[str]
    target_metric: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TodayScheduleItem(BaseModel):
    time_str: str
    category: str # ROUTINE or MEDICATION
    title: str
    description: Optional[str] = None
    voice_prompt: Optional[str] = None
    is_completed: bool = False
    action_type: str # WATER, MEAL, PILL, WORKOUT, SLEEP
    reference_id: int
