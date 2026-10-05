"""Security primitives shared by auth, rate limiting and privacy middleware.

All JWT parsing goes through :func:`decode_token`, which always verifies signature,
expiry and algorithm. Nothing in the codebase may decode a token without verification.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

import jwt
from starlette.requests import Request

from config import get_settings


def decode_token(token: str) -> dict[str, Any] | None:
    """Return verified claims, or ``None`` if the token is invalid/expired.

    Callers that must distinguish *expired* from *invalid* should use
    :func:`decode_token_strict` instead.
    """
    try:
        return decode_token_strict(token)
    except jwt.PyJWTError:
        return None


def decode_token_strict(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_signature": True, "verify_exp": True, "require": ["exp"]},
    )


def bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def subject_of(claims: dict[str, Any]) -> str | None:
    sub = claims.get("sub") or claims.get("user_id") or claims.get("uid")
    return str(sub) if sub else None


def client_ip(request: Request) -> str:
    """Resolve the client IP, trusting X-Forwarded-For only for configured proxy hops.

    With ``trusted_proxy_hops = N`` we take the N-th address from the right of the
    X-Forwarded-For chain (the one appended by our outermost trusted proxy). Anything
    to the left of that is client-controlled and ignored.
    """
    hops = get_settings().trusted_proxy_hops
    if hops > 0:
        xff = request.headers.get("x-forwarded-for", "")
        chain = [p.strip() for p in xff.split(",") if p.strip()]
        if len(chain) >= hops:
            return chain[-hops]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def pseudonymise(value: str, *, purpose: str) -> str:
    """Keyed, daily-rotating pseudonym. Not reversible without HMAC_DAILY_SECRET.

    ``purpose`` domain-separates uses (rate-limit vs. reporter ID) so one pseudonym
    cannot be correlated with another.
    """
    settings = get_settings()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = hmac.new(settings.hmac_daily_secret.encode(), f"{purpose}:{day}".encode(), hashlib.sha256).digest()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:24]


def constant_time_equals(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())
