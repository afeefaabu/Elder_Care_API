import logging
from typing import Dict, Any, List
from app.core.config import settings

logger = logging.getLogger("telephony")

class TelephonyService:
    """Handles real or mock SMS and Emergency Voice Dispatches."""
    
    @staticmethod
    async def send_sms(to_phone: str, body: str) -> bool:
        if settings.MOCK_EXTERNAL_SERVICES or settings.TWILIO_ACCOUNT_SID == "mock_sid":
            logger.info(f"[MOCK SMS] To: {to_phone} | Content: {body}")
            print(f"\n==================== [OUTBOUND SMS] ====================")
            print(f"TO: {to_phone}")
            print(f"MESSAGE: {body}")
            print(f"========================================================\n")
            return True
        else:
            # Twilio integration if credentials provided
            try:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                message = client.messages.create(
                    body=body,
                    from_=settings.TWILIO_FROM_PHONE,
                    to=to_phone
                )
                logger.info(f"Twilio SMS sent: {message.sid}")
                return True
            except Exception as e:
                logger.error(f"Failed to send Twilio SMS: {e}")
                return False

    @staticmethod
    async def send_push_notification(token: str, title: str, body: str, channel_id: str = "default", data: Dict[str, Any] = None) -> bool:
        logger.info(f"[MOCK PUSH] Channel: {channel_id} | Title: {title} | Body: {body}")
        print(f"\n📢 [PUSH NOTIFICATION] [{channel_id.upper()}] {title}: {body} (Data: {data})\n")
        return True

telephony_service = TelephonyService()
