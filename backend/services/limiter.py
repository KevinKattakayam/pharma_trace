"""Rate limiter (SlowAPI / `limits`).

Keys (audit S4/S5):
* Authenticated requests are keyed by the **verified** JWT subject.
* Anonymous requests are keyed by a daily-rotating HMAC pseudonym of the client IP,
  computed by ``PrivacyMiddleware`` *before* the IP is removed from the request scope.

Storage: set ``RATE_LIMIT_STORAGE_URI`` (e.g. ``redis://redis:6379/1``) so limits are
shared across workers and survive restarts. Memory storage is per-process.
"""
from __future__ import annotations

import structlog
from slowapi import Limiter
from starlette.requests import Request

from config import get_settings
from services.security import bearer_token, client_ip, decode_token, pseudonymise, subject_of

logger = structlog.get_logger()


def rate_limit_key(request: Request) -> str:
    token = bearer_token(request)
    if token:
        claims = decode_token(token)
        if claims and (sub := subject_of(claims)):
            return f"user:{sub}"
    precomputed = getattr(request.state, "client_key", None)
    if precomputed:
        return f"anon:{precomputed}"
    return "anon:" + pseudonymise(client_ip(request), purpose="ratelimit")


# Backwards-compatible alias for any external import of the old name.
auth_or_ip_key_func = rate_limit_key


def _storage_uri() -> str:
    s = get_settings()
    uri = s.rate_limit_storage_uri or (s.redis_url if s.redis_url.startswith("redis") else "")
    if not uri:
        if s.is_strict:
            logger.warning(
                "rate_limit_memory_storage",
                detail="In-memory rate limits are per-worker; set RATE_LIMIT_STORAGE_URI=redis://... in production.",
            )
        return "memory://"
    return uri


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[get_settings().rate_limit_default],
    storage_uri=_storage_uri(),
    headers_enabled=False,
    swallow_errors=True,  # a Redis outage degrades to "no limit" rather than 500 on every call
    enabled=get_settings().rate_limit_enabled,
)
