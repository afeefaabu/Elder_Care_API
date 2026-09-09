from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from app.core.database import Base, utc_now

class ServiceDirectory(Base):
    __tablename__ = "service_directory"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    scope = Column(String(32), default="PERSONAL")
    category = Column(String(32), nullable=False)
    name = Column(String(128), nullable=False)
    phone_number = Column(String(32), nullable=False)
    specialty_or_vehicle = Column(String(128), nullable=True)
    address_or_clinic = Column(Text, nullable=True)
    is_favorite = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

class AppointmentRequest(Base):
    __tablename__ = "appointment_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    elder_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    directory_id = Column(Integer, ForeignKey("service_directory.id"), nullable=False)
    requested_datetime = Column(DateTime, nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(32), default="PENDING")
    created_at = Column(DateTime, default=utc_now)
