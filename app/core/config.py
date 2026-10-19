from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "AI Data Center Document Comparison"

    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/ai_datacenter"
    )

    # LLM configuration
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-2.5-flash-lite"
    LLM_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: int = 180
    LLM_TEMPERATURE: float = 0.0

    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    EXTRACTED_DIR: str = str(BASE_DIR / "data" / "extracted")
    PROCESSED_DIR: str = str(BASE_DIR / "data" / "processed")
    REPORT_DIR: str = str(BASE_DIR / "data" / "reports")

    MAX_UPLOAD_SIZE_MB: Optional[int] = None

    JWT_SECRET_KEY: str = (
        "super-secret-datacenter-jwt-key-2026-change-in-production"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    SUPERADMIN_EMAIL: str = "admin@datacenter.ai"
    SUPERADMIN_PASSWORD: str = "Admin@12345"
    SUPERADMIN_NAME: str = "Super Administrator"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()