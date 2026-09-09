import logging
from app.core.config import settings

logger = logging.getLogger("email_service")

class EmailService:
    """Handles real or mock email verification dispatches."""
    
    @staticmethod
    async def send_otp_email(to_email: str, otp_code: str) -> bool:
        logger.info(f"[EMAIL OTP] To: {to_email} | Code: {otp_code}")
        print("\n==================== [OUTBOUND EMAIL] ====================")
        print(f"TO: {to_email}")
        print(f"SUBJECT: Your Elder Care Verification Code: {otp_code}")
        print("BODY:")
        print("Hello,")
        print(f"Your 6-digit verification code is: {otp_code}")
        print("This code will expire in 10 minutes.")
        print("If you did not request this, please ignore this email.")
        print("==========================================================\n")
        return True

email_service = EmailService()
