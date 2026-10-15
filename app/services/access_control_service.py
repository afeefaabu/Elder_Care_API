"""Central authorization helpers for elder-owned health information."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pairing import ElderPairing


async def require_elder_access(
    db: AsyncSession,
    current_user: dict,
    elder_id: int,
    *,
    allow_caregiver: bool = True,
) -> None:
    """Allow an elder, an administrator, or an actively paired caregiver only."""
    role = current_user.get("role")
    user_id = int(current_user.get("sub", 0))
    if role == "ADMIN" or (role == "ELDER" and user_id == elder_id):
        return
    if role == "CAREGIVER" and allow_caregiver:
        pairing_id = await db.scalar(
            select(ElderPairing.id).where(
                ElderPairing.caregiver_id == user_id,
                ElderPairing.elder_id == elder_id,
                ElderPairing.status == "ACTIVE",
            ).limit(1)
        )
        if pairing_id is not None:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have an active connection to this senior's care data.",
    )


async def require_care_plan_management(
    db: AsyncSession,
    current_user: dict,
    elder_id: int,
) -> None:
    """Only an administrator or the senior's active caregiver may alter care plans."""
    if current_user.get("role") not in {"ADMIN", "CAREGIVER"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a caregiver or administrator can change a care plan.",
        )
    await require_elder_access(db, current_user, elder_id)
