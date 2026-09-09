from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.core.database import Base, utc_now

class ElderPairing(Base):
    __tablename__ = "elder_pairings"
    
    id = Column(Integer, primary_key=True, index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    elder_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pair_code = Column(String(16), unique=True, index=True, nullable=False)
    qr_payload = Column(String(256), nullable=False)
    status = Column(String(32), default="PENDING")
    device_fingerprint = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
