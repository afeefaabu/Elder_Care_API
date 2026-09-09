from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from app.core.database import Base

class ServiceDirectory(Base):
    __tablename__ = "service_directory"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), nullable=True) # NULL for city-wide directory
    scope = Column(String(32), default="PERSONAL") # PERSONAL, CITY_VERIFIED
    category = Column(String(32), nullable=False)  # DOCTOR, TAXI, HOSPITAL, AMBULANCE
    name = Column(String(128), nullable=False)     # "Dr. R. Swaminathan (Diabetologist)" / "Ramesh Auto"
    phone_number = Column(String(32), nullable=False)
    specialty_or_vehicle = Column(String(128), nullable=True) # "Diabetologist", "Maruti Dzire AC"
    address_or_clinic = Column(Text, nullable=True)           # "Apollo Clinic, T. Nagar"
    is_favorite = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AppointmentRequest(Base):
    __tablename__ = "appointment_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    directory_id = Column(Integer, ForeignKey("service_directory.id"), nullable=False)
    requested_datetime = Column(DateTime, nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(32), default="PENDING") # PENDING, CONFIRMED, CANCELLED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
