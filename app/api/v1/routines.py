from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.routine import DailyRoutine
from app.schemas.routine import DailyRoutineCreate, DailyRoutineUpdate, DailyRoutineResponse

router = APIRouter(prefix="/routines", tags=["24-Hour Daily Living Routine"])

@router.post("", response_model=DailyRoutineResponse)
async def create_routine(payload: DailyRoutineCreate, db: AsyncSession = Depends(get_db)):
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
    return routine

@router.get("", response_model=List[DailyRoutineResponse])
async def list_routines(elder_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(DailyRoutine)
        .where(DailyRoutine.elder_id == elder_id)
        .order_by(DailyRoutine.time_str)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{routine_id}", response_model=DailyRoutineResponse)
async def get_routine(routine_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
    return routine

@router.put("/{routine_id}", response_model=DailyRoutineResponse)
async def update_routine(
    routine_id: int,
    payload: DailyRoutineUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
        
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
    return routine

@router.post("/{routine_id}/toggle", response_model=DailyRoutineResponse)
async def toggle_routine_active(routine_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
    routine.is_active = not routine.is_active
    await db.commit()
    await db.refresh(routine)
    return routine

@router.delete("/{routine_id}")
async def delete_routine(routine_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DailyRoutine).where(DailyRoutine.id == routine_id)
    res = await db.execute(stmt)
    routine = res.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Routine milestone not found")
    await db.delete(routine)
    await db.commit()
    return {"status": "success", "message": f"Routine milestone {routine_id} deleted successfully."}
