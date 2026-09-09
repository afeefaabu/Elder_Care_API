from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, utc_now

class AdherenceLog(Base):
    __tablename__ = "adherence_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    medication_id = Column(Integer, ForeignKey("medications.id"), index=True, nullable=False)
    scheduled_slot = Column(String(16), nullable=False)
    scheduled_time = Column(DateTime, index=True, nullable=False)
    actual_time = Column(DateTime, nullable=True)
    status = Column(String(32), default="PENDING")
    photo_verification_url = Column(String(512), nullable=True)
    escalation_notified = Column(Boolean, default=False)
    escalation_time = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    
    elder = relationship("User", back_populates="adherence_logs")
    medication = relationship("Medication", back_populates="adherence_logs")
