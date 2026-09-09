from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user_payload
from app.models.user import User
from app.schemas.auth import OTPRequest, OTPVerify, TokenResponse
from app.services.telephony_service import telephony_service

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/request-otp")
async def request_otp(payload: OTPRequest):
    # For rapid testing and local execution, default OTP is 123456
    otp = "123456"
    await telephony_service.send_sms(
        to_phone=payload.phone_number,
        body=f"Your ElderCare verification code is: {otp}"
    )
    return {
        "status": "success",
        "message": f"OTP sent to {payload.phone_number}",
        "dev_mock_otp": otp
    }

@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(payload: OTPVerify, db: AsyncSession = Depends(get_db)):
    # Standard check: accept 123456 or any 6 digits for testing
    if payload.otp_code != "123456" and len(payload.otp_code) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP code")
    
    stmt = select(User).where(User.phone_number == payload.phone_number)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            phone_number=payload.phone_number,
            full_name=payload.full_name or "Caregiver User",
            role="CAREGIVER",
            relationship_to_elder=payload.relationship or "Daughter",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "phone_number": user.phone_number,
        "name": user.full_name
    })
    
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        role=user.role,
        phone_number=user.phone_number,
        full_name=user.full_name
    )

@router.get("/me")
async def get_current_user(
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
):
    user_id = int(payload.get("sub"))
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "phone_number": user.phone_number,
        "full_name": user.full_name,
        "role": user.role,
        "relationship_to_elder": user.relationship_to_elder
    }
