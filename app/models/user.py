from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, utc_now

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(32), unique=True, index=True, nullable=False)
    full_name = Column(String(128), nullable=False)
    role = Column(String(32), nullable=False)  # CAREGIVER, ELDER, ADMIN
    relationship_to_elder = Column(String(64), nullable=True)
    preferred_language = Column(String(16), default="en")
    fcm_token = Column(String(256), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    
    health_profile = relationship("HealthProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="elder", foreign_keys="Medication.elder_id")
    adherence_logs = relationship("AdherenceLog", back_populates="elder")
    routines = relationship("DailyRoutine", back_populates="elder")
    emergency_contacts = relationship("EmergencyContact", back_populates="elder")

class HealthProfile(Base):
    __tablename__ = "health_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(16), nullable=True)
    blood_group = Column(String(8), nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    dietary_restrictions = Column(Text, nullable=True)
    pension_ppo_number = Column(String(64), nullable=True)
    emergency_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    
    user = relationship("User", back_populates="health_profile")
