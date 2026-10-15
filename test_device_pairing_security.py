"""Regression coverage for multi-device elder pairing and per-device revocation."""

import asyncio
import secrets

from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal, init_db, utc_now
from app.core.security import create_access_token
from app.main import app
from app.models.pairing import ElderPairing
from app.models.user import User


async def run_device_pairing_security_test() -> None:
    await init_db()
    suffix = secrets.token_hex(5)

    async with AsyncSessionLocal() as session:
        caregiver = User(
            full_name=f"Device Test Caregiver {suffix}",
            role="CAREGIVER",
            phone_number=f"+9197{secrets.randbelow(10**8):08d}",
        )
        elder = User(
            full_name=f"Device Test Elder {suffix}",
            role="ELDER",
        )
        session.add_all([caregiver, elder])
        await session.flush()
        pair_code = str(secrets.randbelow(900000) + 100000)
        session.add(
            ElderPairing(
                caregiver_id=caregiver.id,
                elder_id=elder.id,
                pair_code=pair_code,
                qr_payload=f"eldercare://pair/{pair_code}",
                status="PENDING",
                expires_at=utc_now(),
            )
        )
        await session.commit()

    caregiver_token = create_access_token(
        {"sub": str(caregiver.id), "role": "CAREGIVER", "name": caregiver.full_name}
    )
    headers = {"Authorization": f"Bearer {caregiver_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_pair = await client.post(
            "/api/v1/elder/pair-device",
            json={"pair_code": pair_code, "device_fingerprint": f"test-device-a-{suffix}"},
        )
        assert first_pair.status_code == 200, first_pair.text
        second_pair = await client.post(
            "/api/v1/elder/pair-device",
            json={"pair_code": pair_code, "device_fingerprint": f"test-device-b-{suffix}"},
        )
        assert second_pair.status_code == 200, second_pair.text

        devices = await client.get(f"/api/v1/elder/{elder.id}/devices", headers=headers)
        assert devices.status_code == 200, devices.text
        assert len(devices.json()) == 2
        first_device = next(
            item for item in devices.json() if item["device_fingerprint"] == f"test-device-a-{suffix}"
        )

        revoke = await client.delete(
            f"/api/v1/elder/{elder.id}/devices/{first_device['id']}", headers=headers
        )
        assert revoke.status_code == 200, revoke.text

        revoked_session = await client.get(
            "/api/v1/elder/session",
            headers={"Authorization": f"Bearer {first_pair.json()['access_token']}"},
        )
        assert revoked_session.status_code == 401, revoked_session.text

        active_session = await client.get(
            "/api/v1/elder/session",
            headers={"Authorization": f"Bearer {second_pair.json()['access_token']}"},
        )
        assert active_session.status_code == 200, active_session.text

    print("[PASS] Multi-device pairing and per-device revocation are isolated.")


if __name__ == "__main__":
    asyncio.run(run_device_pairing_security_test())
