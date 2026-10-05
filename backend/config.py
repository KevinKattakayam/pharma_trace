"""Application settings.

Security model
--------------
* ``ENVIRONMENT`` (dev | test | staging | prod) decides how strict validation is.
  ``debug`` no longer controls security; it defaults to ``False``.
* In dev/test an empty ``JWT_SECRET`` / ``HMAC_DAILY_SECRET`` is replaced by a random,
  process-local value and a warning is emitted: nothing guessable is ever used as a key.
* In staging/prod missing or weak secrets abort start-up.
"""
from __future__ import annotations

import secrets
import warnings
from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "staging", "prod"]

# Values that have appeared in this repository's history or docs and must never be accepted.
_KNOWN_PUBLIC_SECRETS = frozenset(
    {
        "pharmatrace-dev-secret-change-in-production",
        "mock_secret_key_for_development",
        "default_secret_rotate_me",
        "changeme",
        "secret",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        enable_decoding=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────
    app_name: str = "PharmaTrace API"
    app_version: str = "2.0.0"
    environment: Environment = "dev"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    log_level: str = "INFO"

    # ── Data stores ───────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""
    database_url: str = ""
    redis_url: str = ""
    supabase_max_connections: int = 20
    # When a cloud DB is configured, writes that fail are surfaced as errors instead of being
    # silently diverted to the local SQLite file (audit finding R7). Only enable for demos.
    allow_local_fallback_writes: bool = False
    # Where the local SQLite store lives. Must be writable (containers: a mounted volume).
    local_store_path: str = ""

    # ── Rate limiting ─────────────────────────────────────────────────────
    # e.g. "redis://redis:6379/1". Empty → in-process memory (single worker only).
    rate_limit_storage_uri: str = ""
    rate_limit_default: str = "100/minute"
    rate_limit_enabled: bool = True  # ops switch, e.g. for load tests behind an upstream limiter
    # Number of reverse proxies in front of the app whose X-Forwarded-For entries are trusted.
    # 0 = use the socket peer address only (safe default; headers are attacker-controlled).
    trusted_proxy_hops: int = 0

    # ── Observability ─────────────────────────────────────────────────────
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.05
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ── External AI / data providers ─────────────────────────────────────
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    openfda_api_key: str = ""
    gemini_api_key: str = ""
    http_timeout_seconds: float = 10.0

    # Optional authoritative manufacturer / authorised-distributor serial check.
    # A registry lookup alone must never be presented as physical-pack proof.
    manufacturer_verification_url: str = ""
    manufacturer_verification_token: str = ""
    clinical_interaction_provider_url: str = ""
    clinical_interaction_provider_token: str = ""
    external_data_max_age_hours: int = 72
    max_image_upload_bytes: int = 5_000_000
    max_batch_items: int = 100

    # ── Security ──────────────────────────────────────────────────────────
    allow_unauthenticated_demo_user: bool = False
    jwt_secret: str = ""
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_expiration_hours: int = 12
    jwt_issuer: str = "pharmatrace"
    # Keys pseudonymous reporter IDs and rate-limit fingerprints (rotated daily by date salt).
    hmac_daily_secret: str = ""
    # Shared secret for scheduled jobs (X-Cron-Secret header). Empty disables cron endpoints.
    cron_secret: str = ""

    # ── Feature flags ─────────────────────────────────────────────────────
    feature_pack_check: bool = True
    feature_batch_alerts: bool = True
    feature_lasa_guard: bool = True
    feature_passive_alias_learning: bool = False  # off: unauthenticated traffic could poison aliases
    batch_alerts_data_path: str = ""  # optional JSON file of normalised regulator alerts

    # ── Web Push ──────────────────────────────────────────────────────────
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = "mailto:admin@pharmatrace.app"

    # ------------------------------------------------------------------
    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
        return value

    @property
    def is_strict(self) -> bool:
        return self.environment in ("staging", "prod")

    @staticmethod
    def _secret_problems(value: str, *, min_len: int, diversity: bool) -> list[str]:
        problems = []
        if value in _KNOWN_PUBLIC_SECRETS:
            problems.append("is a publicly known default")
        if len(value) < min_len:
            problems.append(f"must be at least {min_len} characters (got {len(value)})")
        if diversity and value:
            classes = [
                any(c.isupper() for c in value),
                any(c.islower() for c in value),
                any(c.isdigit() for c in value),
                any(not c.isalnum() for c in value),
            ]
            if not all(classes):
                problems.append("must mix upper, lower, digit and symbol characters")
        return problems

    @model_validator(mode="after")
    def enforce_security_posture(self) -> Settings:
        if self.is_strict:
            errors: list[str] = []
            if self.debug:
                errors.append("DEBUG must be false in staging/prod")
            if "*" in self.cors_origins:
                errors.append("CORS_ORIGINS must list trusted origins (no wildcard)")
            for name, min_len, div in (("jwt_secret", 64, True), ("hmac_daily_secret", 32, False)):
                for p in self._secret_problems(getattr(self, name), min_len=min_len, diversity=div):
                    errors.append(f"{name.upper()} {p}")
            if self.cron_secret:
                for p in self._secret_problems(self.cron_secret, min_len=32, diversity=False):
                    errors.append(f"CRON_SECRET {p}")
            if self.allow_unauthenticated_demo_user:
                errors.append("ALLOW_UNAUTHENTICATED_DEMO_USER is forbidden in staging/prod")
            if errors:
                raise ValueError("Refusing to start: " + "; ".join(errors))
        else:
            # dev/test: never fall back to a guessable key. Generate per-process randomness.
            for name in ("jwt_secret", "hmac_daily_secret"):
                if not getattr(self, name) or getattr(self, name) in _KNOWN_PUBLIC_SECRETS:
                    object.__setattr__(self, name, secrets.token_urlsafe(48))
                    warnings.warn(
                        f"{name.upper()} not set; using an ephemeral random value "
                        "(tokens/pseudonyms will not survive a restart).",
                        RuntimeWarning,
                        stacklevel=2,
                    )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
