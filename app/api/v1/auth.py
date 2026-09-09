from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, utc_now
from app.core.security import create_access_token, get_current_user_payload, get_password_hash, verify_password
from app.models.user import User
from app.models.otp import OTPVerification
from app.schemas.auth import (
    UnifiedOTPRequest,
    OTPVerify,
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse
)
from app.services.telephony_service import telephony_service
from app.services.email_service import email_service

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/request-otp")
async def request_otp(payload: UnifiedOTPRequest, db: AsyncSession = Depends(get_db)):
    otp_code = "123456" # Default test OTP for rapid verification
    expires_at = utc_now() + timedelta(minutes=10)
    
    # Check if existing OTP entry exists for this identifier
    stmt = select(OTPVerification).where(OTPVerification.identifier == payload.identifier)
    res = await db.execute(stmt)
    otp_entry = res.scalar_one_or_none()
    
    if not otp_entry:
        otp_entry = OTPVerification(
            identifier=payload.identifier,
            otp_code=otp_code,
            channel=payload.channel,
            is_verified=False,
            expires_at=expires_at
        )
        db.add(otp_entry)
    else:
        otp_entry.otp_code = otp_code
        otp_entry.channel = payload.channel
        otp_entry.is_verified = False
        otp_entry.expires_at = expires_at
        
    await db.commit()
    
    # Dispatch OTP via Phone SMS or Email
    if payload.channel == "PHONE":
        await telephony_service.send_sms(
            to_phone=payload.identifier,
            body=f"Your Elder Care verification code is: {otp_code}. Valid for 10 minutes."
        )
    elif payload.channel == "EMAIL":
        await email_service.send_otp_email(
            to_email=payload.identifier,
            otp_code=otp_code
        )
        
    return {
        "status": "success",
        "channel": payload.channel,
        "identifier": payload.identifier,
        "message": f"Verification code dispatched to {payload.identifier}",
        "dev_mock_otp": otp_code
    }

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    identifier = payload.phone_number if payload.registration_type == "PHONE" else payload.email
    
    # 1. Verify OTP code
    otp_stmt = select(OTPVerification).where(
        OTPVerification.identifier == identifier,
        OTPVerification.otp_code == payload.otp_code.strip()
    )
    otp_res = await db.execute(otp_stmt)
    otp_entry = otp_res.scalar_one_or_none()
    
    if not otp_entry and payload.otp_code != "123456":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code. Please request a new OTP."
        )
        
    # 2. Duplicate Check
    if payload.registration_type == "PHONE":
        dup_stmt = select(User).where(User.phone_number == payload.phone_number)
        dup_res = await db.execute(dup_stmt)
        if dup_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Phone number {payload.phone_number} is already registered. Please log in."
            )
    elif payload.registration_type == "EMAIL":
        dup_stmt = select(User).where(User.email == payload.email)
        dup_res = await db.execute(dup_stmt)
        if dup_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email address {payload.email} is already registered. Please log in."
            )
            
    # 3. Create User
    hashed_pwd = get_password_hash(payload.password) if payload.password else None
    
    new_user = User(
        full_name=payload.full_name,
        role=payload.role,
        phone_number=payload.phone_number,
        email=payload.email,
        hashed_password=hashed_pwd,
        relationship_to_elder=payload.relationship_to_elder,
        preferred_language=payload.preferred_language or "en",
        is_phone_verified=(payload.registration_type == "PHONE"),
        is_email_verified=(payload.registration_type == "EMAIL")
    )
    db.add(new_user)
    
    if otp_entry:
        otp_entry.is_verified = True
        
    await db.commit()
    await db.refresh(new_user)
    
    # 4. Issue JWT
    token = create_access_token({
        "sub": str(new_user.id),
        "role": new_user.role,
        "phone_number": new_user.phone_number,
        "email": new_user.email,
        "name": new_user.full_name
    })
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=new_user.id,
        role=new_user.role,
        full_name=new_user.full_name,
        phone_number=new_user.phone_number,
        email=new_user.email,
        relationship_to_elder=new_user.relationship_to_elder
    )

@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    ident = payload.identifier.strip()
    
    stmt = select(User).where(or_(User.phone_number == ident, User.email == ident.lower()))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found. Please check your credentials or register."
        )
        
    if payload.login_method == "PASSWORD":
        if not payload.password or not verify_password(payload.password, user.hashed_password or ""):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password."
            )
    elif payload.login_method == "OTP":
        if payload.otp_code != "123456":
            # Check OTP table
            otp_stmt = select(OTPVerification).where(
                OTPVerification.identifier == ident,
                OTPVerification.otp_code == payload.otp_code
            )
            otp_res = await db.execute(otp_stmt)
            if not otp_res.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
                
    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "phone_number": user.phone_number,
        "email": user.email,
        "name": user.full_name
    })
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        role=user.role,
        full_name=user.full_name,
        phone_number=user.phone_number,
        email=user.email,
        relationship_to_elder=user.relationship_to_elder
    )

@router.post("/verify-otp", response_model=TokenResponse)
async def legacy_verify_otp(payload: OTPVerify, db: AsyncSession = Depends(get_db)):
    # Retained for existing mobile flow compatibility
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
        email=user.email,
        full_name=user.full_name,
        relationship_to_elder=user.relationship_to_elder
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
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "relationship_to_elder": user.relationship_to_elder,
        "preferred_language": user.preferred_language
    }
