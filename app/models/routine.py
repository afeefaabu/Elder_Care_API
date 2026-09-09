from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class DailyRoutine(Base):
    __tablename__ = "daily_routines"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    time_str = Column(String(16), nullable=False) # "07:00", "08:00", "15:00", "17:00", "22:00"
    category = Column(String(32), nullable=False) # WAKEUP, HYDRATION, MEAL, WORKOUT, BEDTIME
    title = Column(String(128), nullable=False)   # "Drink 1 glass warm water"
    description = Column(Text, nullable=True)     # "Diabetic Breakfast (Oats/Idli)"
    voice_prompt = Column(Text, nullable=True)    # Audio readout text
    target_metric = Column(String(64), nullable=True) # "250 ml", "15 mins"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    elder = relationship("User", back_populates="routines")
