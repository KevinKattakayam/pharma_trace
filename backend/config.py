from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "PharmaTrace API"
    app_version: str = "1.0.0"
    debug: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Supabase (PostgreSQL + PostGIS)
    supabase_url: str = ""
    supabase_key: str = ""

    # OpenRouter (GPT-4o Vision — pill image analysis)
    openrouter_api_key: str = ""

    # Groq (Fast LLM inference — side effects, interactions, pill ID)
    groq_api_key: str = ""

    # OpenAI (legacy — not needed if OpenRouter is configured)
    openai_api_key: str = ""

    # OpenFDA
    openfda_api_key: str = ""

    # Gemini (Indian script drug name resolution — free tier)
    gemini_api_key: str = ""

    # Security
    jwt_secret: str = "pharmatrace-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    hmac_daily_secret: str = "default_secret_rotate_me"
    
    # Web Push
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = "mailto:admin@pharmatrace.app"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
