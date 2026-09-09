from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, utc_now

class VitalsLog(Base):
    __tablename__ = "vitals_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    vital_type = Column(String(32), nullable=False)  # BLOOD_SUGAR, BLOOD_PRESSURE, PULSE, WEIGHT
    value_primary = Column(Float, nullable=False)    # Blood Sugar mg/dL or BP Systolic
    value_secondary = Column(Float, nullable=True)   # BP Diastolic (if BP)
    context_label = Column(String(32), nullable=True) # FASTING, POST_PRANDIAL, RANDOM, RESTING
    unit = Column(String(16), default="mg/dL")       # mg/dL, mmHg, bpm
    classification = Column(String(32), default="NORMAL") # NORMAL, CONTROLLED, ELEVATED, CRITICAL
    notes = Column(Text, nullable=True)
    measured_at = Column(DateTime, default=utc_now)
    created_at = Column(DateTime, default=utc_now)
    
    elder = relationship("User", back_populates="vitals")
