from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/invoice_system"

    # Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_API_KEY_2: str = ""  # Optional second key for rotation/fallback
    GEMINI_PRIMARY_MODEL: str = "gemini-3.1-flash-lite-preview"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-flash"

    # Cloudflare R2
    R2_ENDPOINT_URL: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "invoice-images"

    # JWT Auth
    JWT_SECRET_KEY: str = "change-this-to-a-random-secure-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS — set to your Vercel frontend URL in production
    FRONTEND_URL: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
