from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, utc_now

class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    priority = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    relationship_label = Column(String(64), nullable=False)
    phone_number = Column(String(32), nullable=False)
    is_active = Column(Boolean, default=True)
    
    elder = relationship("User", back_populates="emergency_contacts")

class SOSEvent(Base):
    __tablename__ = "sos_events"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    trigger_type = Column(String(64), default="BIG_RED_BUTTON")
    status = Column(String(32), default="ACTIVE")
    broadcast_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(128), nullable=True)
