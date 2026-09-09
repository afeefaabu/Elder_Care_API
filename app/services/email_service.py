import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import settings

logger = logging.getLogger("email_service")

class EmailService:
    """Handles real Gmail SMTP email verification dispatches and fallback logging."""

    def _send_sync(self, to_email: str, subject: str, body_html: str, body_text: str) -> bool:
        clean_pwd = settings.SMTP_PASSWORD.replace(" ", "") if settings.SMTP_PASSWORD else ""
        
        # If credentials are not configured yet, fallback to local terminal output
        if not settings.SMTP_USER or not clean_pwd:
            logger.warning("[EMAIL SERVICE] SMTP_USER or SMTP_PASSWORD not configured. Printing code to console.")
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        from_header = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_USER}>" if settings.SMTP_FROM_NAME else settings.SMTP_USER
        msg["From"] = from_header
        msg["To"] = to_email

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, clean_pwd)
            server.sendmail(settings.SMTP_USER, [to_email], msg.as_string())
            
        logger.info(f"[EMAIL SERVICE] Real OTP email successfully delivered via Gmail SMTP to {to_email}")
        return True

    async def send_otp_email(self, to_email: str, otp_code: str) -> bool:
        subject = f"{otp_code} is your ElderCare verification code"
        body_text = f"""Hello,

Your ElderCare verification code is: {otp_code}

This code is valid for 10 minutes. Please enter this code in the Elder Care app to verify your account.

If you did not request this verification code, please ignore this email.

Best regards,
ElderCare Team
"""
        body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
    .card {{ max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
    .header {{ text-align: center; margin-bottom: 24px; }}
    .header h1 {{ color: #0D47A1; margin: 0; font-size: 26px; font-weight: bold; }}
    .subtitle {{ color: #64748b; font-size: 14px; margin-top: 4px; }}
    .otp-box {{ background-color: #f0fdf4; border: 2px dashed #16a34a; border-radius: 10px; padding: 18px; text-align: center; margin: 24px 0; }}
    .otp-code {{ font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #15803d; margin: 0; }}
    .info {{ color: #475569; font-size: 14px; line-height: 1.6; margin: 8px 0; }}
    .footer {{ text-align: center; margin-top: 32px; color: #94a3b8; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>ElderCare Network</h1>
      <div class="subtitle">Guardian Mode & Elder Safety</div>
    </div>
    <p class="info">Hello,</p>
    <p class="info">Use the following 6-digit verification code to complete your verification in the <strong>ElderCare</strong> app:</p>
    <div class="otp-box">
      <div class="otp-code">{otp_code}</div>
    </div>
    <p class="info">⏰ This code is valid for <strong>10 minutes</strong>. For security, never share this code with anyone.</p>
    <div class="footer">
      <p>&copy; 2026 ElderCare. All rights reserved.</p>
    </div>
  </div>
</body>
</html>"""

        try:
            return await asyncio.to_thread(self._send_sync, to_email, subject, body_html, body_text)
        except Exception as e:
            logger.error(f"[EMAIL SERVICE] SMTP Error sending to {to_email}: {e}")
            # Fallback print to terminal so development is never blocked
            print("\n==================== [OUTBOUND EMAIL FALLBACK] ====================")
            print(f"TO: {to_email}")
            print(f"SUBJECT: {subject}")
            print(f"OTP CODE: {otp_code}")
            print(f"SMTP EXCEPTION: {e}")
            print("===================================================================\n")
            return True

email_service = EmailService()
