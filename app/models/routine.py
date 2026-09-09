from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, utc_now

class DailyRoutine(Base):
    __tablename__ = "daily_routines"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    time_str = Column(String(16), nullable=False)
    category = Column(String(32), nullable=False)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    voice_prompt = Column(Text, nullable=True)
    target_metric = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    
    elder = relationship("User", back_populates="routines")
