from datetime import datetime
from fastapi import APIRouter

router = APIRouter(prefix="/welfare", tags=["Pension & Welfare Portal"])

@router.get("/pension-status")
async def get_pension_status(ppo_number: str = "PPO-TN-2024-98124"):
    # Government DBT / PFMS gateway mock
    current_month = datetime.now().strftime("%B %Y")
    return {
        "ppo_number": ppo_number,
        "beneficiary_name": "Ramanathan K.",
        "scheme": "Senior Citizen Social Security Pension (Direct Benefit Transfer)",
        "current_month": current_month,
        "amount_inr": 3500,
        "disbursement_status": "CREDITED",
        "credited_account": "State Bank of India (Ending in ...4819)",
        "credit_date": "2026-09-02",
        "voice_summary": f"Your pension of ₹3,500 for {current_month} has been credited successfully to your SBI bank account."
    }
