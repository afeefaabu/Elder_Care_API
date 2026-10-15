import secrets
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pairing import ElderPairing
from app.core.database import as_naive_utc, utc_now

class PairingService:
    @staticmethod
    async def create_pairing_code(db: AsyncSession, caregiver_id: int, elder_id: int) -> ElderPairing:
        code = str(secrets.randbelow(900000) + 100000)
        qr_payload = f"ELDERCARE:PAIR:{code}:{elder_id}"
        # The family pairing code is long-lived and is reused for each trusted
        # senior device. The database column remains populated for backwards
        # compatibility; validation no longer expires an established code.
        expires_at = utc_now() + timedelta(days=36500)
        
        # Check if pairing already exists between this caregiver and elder
        stmt = (
            select(ElderPairing)
            .where(
                ElderPairing.caregiver_id == caregiver_id,
                ElderPairing.elder_id == elder_id
            )
            .order_by(ElderPairing.id.desc())
        )
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            # Preserve the first generated code, QR payload, and activation
            # state. Repair only old expiry metadata from the former 24-hour
            # policy so the returned record is not misleading.
            if as_naive_utc(existing.expires_at) < utc_now():
                existing.expires_at = expires_at
                await db.commit()
                await db.refresh(existing)
            return existing
        
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
        stmt = select(ElderPairing).where(ElderPairing.pair_code == pair_code)
        result = await db.execute(stmt)
        pairing = result.scalar_one_or_none()
        
        if not pairing or pairing.status not in {"PENDING", "ACTIVE"}:
            return None

        if pairing.status == "PENDING":
            pairing.status = "ACTIVE"
            pairing.device_fingerprint = device_fingerprint
            await db.commit()
            await db.refresh(pairing)
        return pairing

pairing_service = PairingService()
