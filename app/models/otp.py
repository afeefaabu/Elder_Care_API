from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.core.database import Base, utc_now

class OTPVerification(Base):
    __tablename__ = "otp_verifications"
    
    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(128), index=True, nullable=False) # E.164 Phone or Email
    otp_code = Column(String(16), nullable=False)
    channel = Column(String(16), nullable=False) # PHONE or EMAIL
    is_verified = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now)
