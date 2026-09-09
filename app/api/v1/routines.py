from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.routine import DailyRoutine
from app.schemas.routine import DailyRoutineCreate, DailyRoutineResponse

router = APIRouter(prefix="/routines", tags=["24-Hour Daily Living Routine"])

@router.post("", response_model=DailyRoutineResponse)
async def create_routine(payload: DailyRoutineCreate, db: AsyncSession = Depends(get_db)):
    routine = DailyRoutine(
        elder_id=payload.elder_id,
        time_str=payload.time_str,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        voice_prompt=payload.voice_prompt,
        target_metric=payload.target_metric
    )
    db.add(routine)
    await db.commit()
    await db.refresh(routine)
    return routine

@router.get("", response_model=List[DailyRoutineResponse])
async def list_routines(elder_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(DailyRoutine)
        .where(DailyRoutine.elder_id == elder_id, DailyRoutine.is_active == True)
        .order_by(DailyRoutine.time_str)
    )
    res = await db.execute(stmt)
    return res.scalars().all()
