from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.models.vitals import VitalsLog
from app.schemas.vitals import VitalsLogCreate, VitalsLogResponse, VitalsSummaryResponse

router = APIRouter(prefix="/vitals", tags=["Health Vitals & Trends"])

def classify_vital(vital_type: str, primary: float, secondary: Optional[float], context: Optional[str]) -> str:
    vtype = vital_type.upper()
    ctx = (context or "").upper()
    
    if "SUGAR" in vtype:
        if "FASTING" in ctx:
            if primary < 70:
                return "LOW / HYPOGLYCEMIA"
            elif primary <= 100:
                return "NORMAL"
            elif primary <= 125:
                return "PRE-DIABETIC"
            elif primary <= 200:
                return "ELEVATED"
            else:
                return "CRITICAL HIGH"
        else: # Post-prandial / random
            if primary < 140:
                return "NORMAL"
            elif primary <= 199:
                return "ELEVATED"
            else:
                return "CRITICAL HIGH"
                
    elif "PRESSURE" in vtype:
        systolic = primary
        diastolic = secondary or 80.0
        if systolic > 180 or diastolic > 120:
            return "CRITICAL HYPERTENSIVE"
        elif systolic >= 140 or diastolic >= 90:
            return "HIGH"
        elif systolic >= 130 or diastolic >= 80:
            return "CONTROLLED"
        elif systolic >= 120 and diastolic < 80:
            return "ELEVATED"
        else:
            return "NORMAL"
            
    return "NORMAL"

@router.post("", response_model=VitalsLogResponse)
async def log_vital(payload: VitalsLogCreate, db: AsyncSession = Depends(get_db)):
    classification = classify_vital(
        payload.vital_type,
        payload.value_primary,
        payload.value_secondary,
        payload.context_label
    )
    
    vital = VitalsLog(
        elder_id=payload.elder_id,
        vital_type=payload.vital_type.upper(),
        value_primary=payload.value_primary,
        value_secondary=payload.value_secondary,
        context_label=payload.context_label.upper() if payload.context_label else None,
        unit=payload.unit or ("mmHg" if "PRESSURE" in payload.vital_type.upper() else "mg/dL"),
        classification=classification,
        notes=payload.notes,
        measured_at=payload.measured_at or utc_now(),
        created_at=utc_now()
    )
    db.add(vital)
    await db.commit()
    await db.refresh(vital)
    return vital

@router.get("", response_model=List[VitalsLogResponse])
async def list_vitals(
    elder_id: int,
    vital_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(VitalsLog).where(VitalsLog.elder_id == elder_id)
    if vital_type:
        stmt = stmt.where(VitalsLog.vital_type == vital_type.upper())
    stmt = stmt.order_by(desc(VitalsLog.measured_at))
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/summary/{elder_id}", response_model=VitalsSummaryResponse)
async def get_vitals_summary(elder_id: int, db: AsyncSession = Depends(get_db)):
    # Latest Blood Sugar
    sugar_stmt = (
        select(VitalsLog)
        .where(VitalsLog.elder_id == elder_id, VitalsLog.vital_type == "BLOOD_SUGAR")
        .order_by(desc(VitalsLog.measured_at))
        .limit(1)
    )
    sugar_res = await db.execute(sugar_stmt)
    latest_sugar = sugar_res.scalar_one_or_none()
    
    # Latest BP
    bp_stmt = (
        select(VitalsLog)
        .where(VitalsLog.elder_id == elder_id, VitalsLog.vital_type == "BLOOD_PRESSURE")
        .order_by(desc(VitalsLog.measured_at))
        .limit(1)
    )
    bp_res = await db.execute(bp_stmt)
    latest_bp = bp_res.scalar_one_or_none()
    
    overall = "NORMAL"
    if (latest_sugar and "CRITICAL" in latest_sugar.classification) or (latest_bp and "CRITICAL" in latest_bp.classification):
        overall = "CRITICAL"
    elif (latest_sugar and "ELEVATED" in latest_sugar.classification) or (latest_bp and "HIGH" in latest_bp.classification):
        overall = "ATTENTION_REQUIRED"
        
    return VitalsSummaryResponse(
        elder_id=elder_id,
        latest_blood_sugar=latest_sugar,
        latest_blood_pressure=latest_bp,
        overall_vitals_status=overall
    )

@router.delete("/{vital_id}")
async def delete_vital(vital_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(VitalsLog).where(VitalsLog.id == vital_id)
    res = await db.execute(stmt)
    vital = res.scalar_one_or_none()
    if not vital:
        raise HTTPException(status_code=404, detail="Vitals record not found")
    await db.delete(vital)
    await db.commit()
    return {"status": "success", "message": f"Vital record {vital_id} deleted successfully."}
