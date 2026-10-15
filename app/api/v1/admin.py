from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import get_db
from app.core.security import get_password_hash, require_admin
from app.models.pairing import ElderPairing
from app.models.sos import SOSEvent
from app.models.user import HealthProfile, User
from app.schemas.admin import AdminConnectionCreate, AdminUserCreate, AdminUserUpdate
from app.services.pairing_service import pairing_service

router = APIRouter(prefix="/admin", tags=["Administration"])


async def _user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _user_payload(user: User, profile: HealthProfile | None, connection_count: int) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "role": user.role,
        "is_active": bool(user.is_active),
        "relationship_to_elder": user.relationship_to_elder,
        "preferred_language": user.preferred_language,
        "age": profile.age if profile else None,
        "created_at": user.created_at,
        "connection_count": connection_count,
    }


@router.get("/overview")
async def get_admin_overview(
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    async def count_users(role: str | None = None, active: bool | None = None) -> int:
        statement = select(func.count(User.id))
        if role:
            statement = statement.where(User.role == role)
        if active is not None:
            statement = statement.where(User.is_active == active)
        return int((await db.scalar(statement)) or 0)

    active_connections = int(
        (await db.scalar(select(func.count(ElderPairing.id)).where(ElderPairing.status == "ACTIVE")))
        or 0
    )
    pending_connections = int(
        (await db.scalar(select(func.count(ElderPairing.id)).where(ElderPairing.status == "PENDING")))
        or 0
    )
    active_sos = int(
        (await db.scalar(select(func.count(SOSEvent.id)).where(SOSEvent.status == "ACTIVE")))
        or 0
    )
    recent_result = await db.execute(select(User).order_by(User.created_at.desc()).limit(5))

    return {
        "total_users": await count_users(),
        "caregivers": await count_users("CAREGIVER"),
        "seniors": await count_users("ELDER"),
        "administrators": await count_users("ADMIN"),
        "inactive_users": await count_users(active=False),
        "active_connections": active_connections,
        "pending_connections": pending_connections,
        "active_sos": active_sos,
        "recent_users": [
            {
                "id": user.id,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": bool(user.is_active),
                "created_at": user.created_at,
            }
            for user in recent_result.scalars().all()
        ],
    }


@router.get("/users")
async def list_users(
    role: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=128),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    statement = select(User, HealthProfile).outerjoin(HealthProfile, User.id == HealthProfile.user_id)
    if role:
        statement = statement.where(User.role == role.upper())
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
                User.phone_number.ilike(term),
            )
        )
    result = await db.execute(statement.order_by(User.created_at.desc()).limit(250))
    pairings = (await db.execute(select(ElderPairing))).scalars().all()
    connection_counts: dict[int, int] = {}
    for pairing in pairings:
        if pairing.status == "REVOKED":
            continue
        connection_counts[pairing.caregiver_id] = connection_counts.get(pairing.caregiver_id, 0) + 1
        connection_counts[pairing.elder_id] = connection_counts.get(pairing.elder_id, 0) + 1

    return [
        _user_payload(user, profile, connection_counts.get(user.id, 0))
        for user, profile in result.all()
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not payload.email and not payload.phone_number:
        raise HTTPException(status_code=422, detail="Enter an email address or phone number.")

    duplicate_conditions = []
    if payload.email:
        duplicate_conditions.append(User.email == payload.email)
    if payload.phone_number:
        duplicate_conditions.append(User.phone_number == payload.phone_number.strip())
    duplicate = await db.scalar(select(User).where(or_(*duplicate_conditions)))
    if duplicate:
        raise HTTPException(status_code=409, detail="An account already uses this email address or phone number.")

    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email,
        phone_number=payload.phone_number.strip() if payload.phone_number else None,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        relationship_to_elder=payload.relationship_to_elder,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_payload(user, None, 0)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _user_or_404(db, user_id)
    current_user_id = int(current_user["sub"])
    admin_count = int((await db.scalar(select(func.count(User.id)).where(User.role == "ADMIN"))) or 0)

    removing_last_admin = (
        user.role == "ADMIN"
        and admin_count <= 1
        and (payload.role not in (None, "ADMIN") or payload.is_active is False)
    )
    if removing_last_admin:
        raise HTTPException(status_code=400, detail="The only administrator cannot be demoted or disabled.")
    if user.id == current_user_id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    profile = await db.scalar(select(HealthProfile).where(HealthProfile.user_id == user.id))
    return _user_payload(user, profile, 0)


@router.get("/connections")
async def list_connections(
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    caregiver = aliased(User)
    elder = aliased(User)
    statement = (
        select(ElderPairing, caregiver, elder)
        .join(caregiver, ElderPairing.caregiver_id == caregiver.id)
        .join(elder, ElderPairing.elder_id == elder.id)
        .order_by(ElderPairing.created_at.desc())
    )
    result = await db.execute(statement)
    return [
        {
            "id": pairing.id,
            "caregiver_id": caregiver_user.id,
            "caregiver_name": caregiver_user.full_name,
            "elder_id": elder_user.id,
            "elder_name": elder_user.full_name,
            "status": pairing.status,
            "pair_code": pairing.pair_code,
            "expires_at": pairing.expires_at,
            "created_at": pairing.created_at,
        }
        for pairing, caregiver_user, elder_user in result.all()
    ]


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: AdminConnectionCreate,
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    caregiver = await _user_or_404(db, payload.caregiver_id)
    elder = await _user_or_404(db, payload.elder_id)
    if caregiver.role != "CAREGIVER":
        raise HTTPException(status_code=422, detail="Choose a caregiver account.")
    if elder.role != "ELDER":
        raise HTTPException(status_code=422, detail="Choose a senior citizen account.")
    if not caregiver.is_active or not elder.is_active:
        raise HTTPException(status_code=422, detail="Both accounts must be active before connecting them.")

    pairing = await pairing_service.create_pairing_code(
        db,
        caregiver_id=caregiver.id,
        elder_id=elder.id,
    )
    return {
        "id": pairing.id,
        "caregiver_id": caregiver.id,
        "caregiver_name": caregiver.full_name,
        "elder_id": elder.id,
        "elder_name": elder.full_name,
        "status": pairing.status,
        "pair_code": pairing.pair_code,
        "expires_at": pairing.expires_at,
    }


@router.post("/connections/{connection_id}/disconnect")
async def disconnect_connection(
    connection_id: int,
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    pairing = await db.get(ElderPairing, connection_id)
    if not pairing:
        raise HTTPException(status_code=404, detail="Connection not found.")
    pairing.status = "REVOKED"
    pairing.device_fingerprint = None
    await db.commit()
    return {"status": "success", "message": "Caregiver and senior connection disconnected."}
