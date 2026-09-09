import secrets
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pairing import ElderPairing
from app.core.database import utc_now

class PairingService:
    @staticmethod
    async def create_pairing_code(db: AsyncSession, caregiver_id: int, elder_id: int) -> ElderPairing:
        code = str(secrets.randbelow(900000) + 100000)
        qr_payload = f"ELDERCARE:PAIR:{code}:{elder_id}"
        expires_at = utc_now() + timedelta(hours=24)
        
        pairing = ElderPairing(
            caregiver_id=caregiver_id,
            elder_id=elder_id,
            pair_code=code,
            qr_payload=qr_payload,
            status="PENDING",
            created_at=utc_now(),
            expires_at=expires_at,
        )
        db.add(pairing)
        await db.commit()
        await db.refresh(pairing)
        return pairing

    @staticmethod
    async def verify_and_activate(db: AsyncSession, pair_code: str, device_fingerprint: str = None) -> ElderPairing:
        stmt = select(ElderPairing).where(
            ElderPairing.pair_code == pair_code,
            ElderPairing.status.in_(["PENDING", "ACTIVE"])
        )
        result = await db.execute(stmt)
        pairing = result.scalar_one_or_none()
        
        if not pairing:
            return None
            
        pairing.status = "ACTIVE"
        pairing.device_fingerprint = device_fingerprint
        await db.commit()
        await db.refresh(pairing)
        return pairing

pairing_service = PairingService()
