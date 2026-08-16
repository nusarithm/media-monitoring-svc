from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # PostgreSQL Configuration
    DATABASE_URL: str
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10
    DB_COMMAND_TIMEOUT: int = 30

    # JWT Configuration
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # SMTP Configuration
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str
    
    # OTP Configuration
    OTP_EXPIRE_MINUTES: int = 10
    OTP_LENGTH: int = 6

    # Password hashing configuration (PBKDF2-HMAC-SHA256)
    PASSWORD_HASH_ITERATIONS: int = 100_000
    PASSWORD_SALT_BYTES: int = 16
    
    # SMTP TLS verification (set to false for local testing if certificate issues occur)
    SMTP_VERIFY_SSL: bool = True
    
    # Application Configuration
    APP_NAME: str = "Media Monitoring Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # CORS - comma separated list of allowed browser origins
    CORS_ORIGINS: str = "https://monitor.nusarithm.id"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Alert sweep interval in minutes; 0 disables the background loop.
    ALERT_SWEEP_MINUTES: int = 60

    # LLM gateway (OpenAI-compatible) used for narrative summaries.
    # Empty LLM_API_KEY disables the feature rather than breaking startup.
    LLM_BASE_URL: str = "https://omni.menglabs.id/v1"
    LLM_MODEL: str = "antigravity/gemini-3.6-flash-medium"
    LLM_API_KEY: str = ""
    LLM_MAX_ARTICLES: int = 30
    LLM_TIMEOUT: float = 60.0

    # Elasticsearch Configuration
    ELASTICSEARCH_HOST: str
    ELASTICSEARCH_USERNAME: str
    ELASTICSEARCH_PASSWORD: str
    ELASTICSEARCH_INDEX: str = "online-news-*"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
