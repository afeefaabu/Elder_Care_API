from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class Medication(Base):
    __tablename__ = "medications"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    caregiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(128), nullable=False)                 # Metformin, Amlodipine
    dosage_type = Column(String(64), default="Tablet")         # Tablet, Syrup, Injection
    strength = Column(String(64), default="500 mg")            # 500 mg, 5 ml
    meal_relation = Column(String(64), default="After Food")   # Before Food, After Food
    alarm_times_csv = Column(String(256), nullable=False)      # Comma-separated: "08:30,20:30"
    recurrence = Column(String(64), default="Daily")           # Daily, Mon-Fri
    pill_photo_url = Column(String(512), nullable=True)
    alarm_sound = Column(String(64), default="Loud Spoken Chime")
    escalation_enabled = Column(Boolean, default=True)
    escalation_minutes = Column(Integer, default=25)
    is_critical = Column(Boolean, default=True)
    instructions = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    elder = relationship("User", foreign_keys=[elder_id], back_populates="medications")
    adherence_logs = relationship("AdherenceLog", back_populates="medication", cascade="all, delete-orphan")
