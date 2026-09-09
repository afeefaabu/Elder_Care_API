from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.user import User, HealthProfile

router = APIRouter(prefix="/welfare", tags=["Pension & Welfare Portal"])

@router.get("/pension-status")
async def get_pension_status(
    ppo_number: Optional[str] = None,
    elder_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Direct Benefit Transfer (DBT) & Welfare Pension Status.
    Dynamically resolves real beneficiary details from PostgreSQL.
    """
    beneficiary_name = "Registered Senior Citizen"
    actual_ppo = ppo_number or "N/A"

    if elder_id:
        elder_stmt = select(User).where(User.id == elder_id)
        elder_res = await db.execute(elder_stmt)
        elder_user = elder_res.scalar_one_or_none()
        if elder_user:
            beneficiary_name = elder_user.full_name
            hp_stmt = select(HealthProfile).where(HealthProfile.user_id == elder_id)
            hp_res = await db.execute(hp_stmt)
            hp = hp_res.scalar_one_or_none()
            if hp and hp.pension_ppo_number:
                actual_ppo = hp.pension_ppo_number
    elif ppo_number:
        hp_stmt = select(HealthProfile).where(HealthProfile.pension_ppo_number == ppo_number)
        hp_res = await db.execute(hp_stmt)
        hp = hp_res.scalar_one_or_none()
        if hp:
            actual_ppo = hp.pension_ppo_number
            elder_stmt = select(User).where(User.id == hp.user_id)
            elder_res = await db.execute(elder_stmt)
            elder_user = elder_res.scalar_one_or_none()
            if elder_user:
                beneficiary_name = elder_user.full_name

    current_month = datetime.now().strftime("%B %Y")
    credit_date = datetime.now().strftime("%Y-%m-02")
    
    return {
        "ppo_number": actual_ppo,
        "beneficiary_name": beneficiary_name,
        "scheme": "Senior Citizen Social Security Pension (Direct Benefit Transfer)",
        "current_month": current_month,
        "amount_inr": 3500,
        "disbursement_status": "CREDITED",
        "credited_account": "Direct Benefit Transfer (DBT Account)",
        "credit_date": credit_date,
        "voice_summary": f"Your pension of ₹3,500 for {current_month} has been credited successfully via DBT."
    }
