from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user_payload, require_caregiver
from app.models.routine import DailyRoutine
from app.schemas.routine import DailyRoutineCreate, DailyRoutineUpdate, DailyRoutineResponse
from app.services.adherence_service import adherence_broadcaster
from app.services.access_control_service import require_care_plan_management, require_elder_access

router = APIRouter(prefix="/routines", tags=["24-Hour Daily Living Routine"])

@router.post("", response_model=DailyRoutineResponse)
async def create_routine(
    payload: DailyRoutineCreate,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db),
):
    await require_care_plan_management(db, current_user, payload.elder_id)
    routine = DailyRoutine(
        elder_id=payload.elder_id,
        time_str=payload.time_str,
        category=payload.category.upper(),
        title=payload.title,
        description=payload.description,
        voice_prompt=payload.voice_prompt,
        target_metric=payload.target_metric,
        is_active=True
    )
    db.add(routine)
    await db.commit()
    await db.refresh(routine)
    await adherence_broadcaster.publish_elder_update(
        db, routine.elder_id, "ROUTINE", "CREATED", routine_id=routine.id
    )
    return routine

@router.get("", response_model=List[DailyRoutineResponse])
async def list_routines(
    elder_id: int,
    current_user: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    await require_elder_access(db, current_user, elder_id)
    stmt = (
        select(DailyRoutine)
        .where(DailyRoutine.elder_id == elder_id)
        .order_by(DailyRoutine.time_str)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{routine_id}", response_model=DailyRoutineResponse)
async def get_routine(
    routine_id: int,
    current_user: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
    await require_elder_access(db, current_user, routine.elder_id)
    return routine

@router.put("/{routine_id}", response_model=DailyRoutineResponse)
async def update_routine(
    routine_id: int,
    payload: DailyRoutineUpdate,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
    await require_care_plan_management(db, current_user, routine.elder_id)
        
    if payload.time_str is not None:
        routine.time_str = payload.time_str
    if payload.category is not None:
        routine.category = payload.category.upper()
    if payload.title is not None:
        routine.title = payload.title
    if payload.description is not None:
        routine.description = payload.description
    if payload.voice_prompt is not None:
        routine.voice_prompt = payload.voice_prompt
    if payload.target_metric is not None:
        routine.target_metric = payload.target_metric
    if payload.is_active is not None:
        routine.is_active = payload.is_active
        
    await db.commit()
    await db.refresh(routine)
    await adherence_broadcaster.publish_elder_update(
        db, routine.elder_id, "ROUTINE", "UPDATED", routine_id=routine.id
    )
    return routine

@router.post("/{routine_id}/toggle", response_model=DailyRoutineResponse)
async def toggle_routine_active(
    routine_id: int,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
    await require_care_plan_management(db, current_user, routine.elder_id)
    routine.is_active = not routine.is_active
    await db.commit()
    await db.refresh(routine)
    await adherence_broadcaster.publish_elder_update(
        db, routine.elder_id, "ROUTINE", "UPDATED", routine_id=routine.id
    )
    return routine

@router.delete("/{routine_id}")
async def delete_routine(
    routine_id: int,
    current_user: dict = Depends(require_caregiver),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
    await require_care_plan_management(db, current_user, routine.elder_id)
    elder_id = routine.elder_id
    await db.delete(routine)
    await db.commit()
    await adherence_broadcaster.publish_elder_update(
        db, elder_id, "ROUTINE", "DELETED", routine_id=routine_id
    )
    return {"status": "success", "message": f"Routine milestone {routine_id} deleted successfully."}
