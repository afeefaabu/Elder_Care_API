from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, utc_now

class SeniorWorkout(Base):
    __tablename__ = 'senior_workouts'
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey('users.id'), index=True, nullable=False)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(32), default='CHAIR_YOGA', nullable=False)
    video_url = Column(Text, nullable=True)
    duration_minutes = Column(Integer, default=15, nullable=False)
    scheduled_time = Column(String(16), default='17:00', nullable=False)
    instructions = Column(Text, nullable=True)
    voice_prompt = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    last_completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    
    elder = relationship('User', back_populates='workouts')

