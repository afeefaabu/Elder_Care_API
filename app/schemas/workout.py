from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class WorkoutCreate(BaseModel):
    elder_id: int
    title: str = Field(..., min_length=2, max_length=128)
    description: Optional[str] = None
    category: str = Field(default='CHAIR_YOGA')
    video_url: Optional[str] = None
    duration_minutes: int = Field(default=15, ge=1, le=120)
    scheduled_time: str = Field(default='17:00')
    instructions: Optional[str] = None
    voice_prompt: Optional[str] = None

class WorkoutUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    video_url: Optional[str] = None
    duration_minutes: Optional[int] = None
    scheduled_time: Optional[str] = None
    instructions: Optional[str] = None
    voice_prompt: Optional[str] = None
    is_active: Optional[bool] = None

class WorkoutResponse(BaseModel):
    id: int
    elder_id: int
    title: str
    description: Optional[str] = None
    category: str
    video_url: Optional[str] = None
    duration_minutes: int
    scheduled_time: str
    instructions: Optional[str] = None
    voice_prompt: Optional[str] = None
    is_active: bool
    last_completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class WorkoutLibraryItem(BaseModel):
    id: str
    title: str
    category: str
    default_duration: int
    description: str
    benefits: str
    default_video_url: str
    instructions: str
    default_voice_prompt: str

