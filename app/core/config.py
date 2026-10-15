from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Elder Care Production API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./elder_care.db"
    
    # Auth & JWT
    SECRET_KEY: str = "temporary-secret-key-for-elder-care-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 Days

    # First administrator provisioning. These values are read only by the
    # backend at startup; the Flutter client can never create an administrator.
    DEFAULT_ADMIN_NAME: str = ""
    DEFAULT_ADMIN_EMAIL: str = ""
    DEFAULT_ADMIN_PASSWORD: str = ""
    
    # Mocking & Telephony
    MOCK_EXTERNAL_SERVICES: bool = True
    TWILIO_ACCOUNT_SID: str = "mock_sid"
    TWILIO_AUTH_TOKEN: str = "mock_token"
    TWILIO_FROM_PHONE: str = "+15005550006"
    
    # 25-Minute Watchdog
    WATCHDOG_CHECK_INTERVAL_SECONDS: int = 15
    MISSED_MEDICATION_THRESHOLD_MINUTES: int = 25

    # Gemini is called only from the backend. Leave the key blank until it is
    # added privately to .env; never expose it to the Flutter application.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # Email & SMTP Dispatch (Gmail)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_NAME: str = "ElderCare"
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
