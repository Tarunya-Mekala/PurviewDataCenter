from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "AI Data Center Document Comparison"

    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/ai_datacenter"
    )

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "qwen2.5:27b"
    LLM_API_KEY: Optional[str] = None
    LLM_TIMEOUT_SECONDS: int = 180
    LLM_TEMPERATURE: float = 0.0

    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    EXTRACTED_DIR: str = str(BASE_DIR / "data" / "extracted")
    PROCESSED_DIR: str = str(BASE_DIR / "data" / "processed")
    REPORT_DIR: str = str(BASE_DIR / "data" / "reports")
    BACKUP_DIR: str = str(BASE_DIR / "data" / "backups")

    # Database connection pool settings
    DB_POOL_SIZE: int = 25
    DB_MAX_OVERFLOW: int = 50
    DB_POOL_TIMEOUT: int = 60
    DB_POOL_RECYCLE: int = 1800

    # Retention period (in days) for stored export files (7 years = 2555 days for audit & dispute compliance)
    EXPORT_RETENTION_DAYS: int = 2555

    MAX_UPLOAD_SIZE_MB: Optional[int] = None

    # Authentication & JWT
    JWT_SECRET_KEY: str = "super-secret-datacenter-jwt-key-2026-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Initial Super Admin credentials
    SUPERADMIN_EMAIL: str = "admin@datacenter.ai"
    SUPERADMIN_PASSWORD: str = "DcAdmin!Secure2026#Xk9"
    SUPERADMIN_NAME: str = "Super Administrator"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()