from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "AI Data Center Document Comparison"

    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5433/ai_datacenter"
    )

    # =========================
    # LLM / Qwen Configuration
    # =========================
    LLM_PROVIDER: str = "qwen"
    LLM_MODEL: str = "Qwen/Qwen3-VL-4B-Instruct"
    LLM_BASE_URL: str = "http://localhost:8001/v1"
    LLM_API_KEY: str = "EMPTY"
    LLM_TIMEOUT_SECONDS: int = 180
    LLM_TEMPERATURE: float = 0.0

    # =========================
    # File Storage
    # =========================
    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    EXTRACTED_DIR: str = str(BASE_DIR / "data" / "extracted")
    PROCESSED_DIR: str = str(BASE_DIR / "data" / "processed")
    REPORT_DIR: str = str(BASE_DIR / "data" / "reports")

    MAX_UPLOAD_SIZE_MB: Optional[int] = None

    # =========================
    # JWT Configuration
    # =========================
    JWT_SECRET_KEY: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # =========================
    # Super Admin
    # =========================
    SUPERADMIN_EMAIL: str = "admin@datacenter.ai"
    SUPERADMIN_PASSWORD: str = "Admin@12345"
    SUPERADMIN_NAME: str = "Super Administrator"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()