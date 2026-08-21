import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "AI Vastra WhatsApp Sales Agent"
    ENV: str = "development"
    SECRET_KEY: str = "super_secure_random_production_secret_key_998877"

    # CORS configuration
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [oss.strip() for oss in v.split(",")]
        elif isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                return [v]
        elif isinstance(v, list):
            return [str(item) for item in v]
        return ["*"]

    # Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./aivastra.db"
    SYNC_DATABASE_URL: str = "sqlite:///./aivastra.db"

    # Redis Cache & Celery (Optional)
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Vector DB (ChromaDB)
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000

    # Clerk Auth Setup (Optional)
    CLERK_JWKS_URL: str = "https://api.clerk.com/v1/jwks"
    CLERK_SECRET_KEY: str = ""
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: str = ""

    # AI Configurations
    DEFAULT_LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # File Storage Configurations
    STORAGE_PROVIDER: str = "local"
    LOCAL_STORAGE_DIR: str = "./uploads"

    # WhatsApp Sales Team Contact
    SALES_TEAM_NAME: str = "Ai Vastra Sales Team"
    SALES_TEAM_EMAIL: str = "support@aivastra.com"

    # WhatsApp Meta Cloud API Configurations
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "aivastra_whatsapp_verify_token_2026"


settings = Settings()
