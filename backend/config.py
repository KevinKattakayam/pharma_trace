from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache



from typing import Any, Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        enable_decoding=False,
    )
    # App & Environment Separation (dev, staging, prod)
    app_name: str = "PharmaTrace API"
    app_version: str = "1.0.0"
    debug: bool = True
    environment: Literal["dev", "staging", "prod"] = "dev"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Supabase (PostgreSQL + PostGIS)
    supabase_url: str = ""
    supabase_key: str = ""
    database_url: str = ""
    redis_url: str = ""
    supabase_max_connections: int = 20

    # Observability (Sentry + Langfuse for LangGraph tracing)
    sentry_dsn: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

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

    # Optional authoritative manufacturer / authorised-distributor serial check.
    # A registry lookup alone must never be presented as physical-pack proof.
    manufacturer_verification_url: str = ""
    manufacturer_verification_token: str = ""
    clinical_interaction_provider_url: str = ""
    clinical_interaction_provider_token: str = ""
    external_data_max_age_hours: int = 72
    max_image_upload_bytes: int = 5_000_000
    max_batch_items: int = 100

    # Security
    allow_unauthenticated_demo_user: bool = False
    jwt_secret: str = "pharmatrace-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    hmac_daily_secret: str = "default_secret_rotate_me"

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value: Any) -> Any:
        """Accept conventional deployment labels while retaining a strict bool internally."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        debug = info.data.get("debug", True)
        if not debug:
            if v in ("pharmatrace-dev-secret-change-in-production", "mock_secret_key_for_development"):
                raise ValueError("CRITICAL SECURITY RISK: Refusing to start with default development JWT_SECRET when DEBUG=false.")
            if len(v) < 64:
                raise ValueError(f"CRITICAL SECURITY RISK: JWT_SECRET must be >= 64 chars when DEBUG=false (current len: {len(v)}).")
            
            # Assert character class diversity
            has_upper = any(c.isupper() for c in v)
            has_lower = any(c.islower() for c in v)
            has_digit = any(c.isdigit() for c in v)
            has_special = any(not c.isalnum() for c in v)
            if not (has_upper and has_lower and has_digit and has_special):
                raise ValueError("CRITICAL SECURITY RISK: JWT_SECRET lacks character class diversity. Must contain >= 1 uppercase, lowercase, digit, and special char.")
        return v

    @field_validator("environment", mode="after")
    @classmethod
    def validate_environment(cls, v: str, info) -> str:
        debug = info.data.get("debug", True)
        if v == "prod" and debug:
            raise ValueError("SECURITY VIOLATION: Refusing to start 'prod' environment with debug=True.")
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Accept a comma-separated deployment variable without weakening CORS."""
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins", mode="after")
    @classmethod
    def validate_cors_origins(cls, origins: list[str], info) -> list[str]:
        if info.data.get("environment") == "prod" and "*" in origins:
            raise ValueError("CORS_ORIGINS must name trusted origins in production; wildcard is not allowed.")
        return origins

    
    # Web Push
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = "mailto:admin@pharmatrace.app"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
