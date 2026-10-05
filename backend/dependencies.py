"""FastAPI auth dependencies: verified JWT → ``CurrentUser``; role and tenant guards."""
from __future__ import annotations

from collections.abc import Callable

import jwt
import structlog
from fastapi import Depends, Header, HTTPException

from config import get_settings
from models.schemas import CurrentUser
from services.security import decode_token_strict, subject_of

logger = structlog.get_logger()

# Roles recognised by the platform. "admin" is a superset; others are least-privilege.
ROLES = frozenset({"user", "caregiver", "pharmacist", "clinic_admin", "regulator", "auditor", "admin"})


def get_current_user(authorization: str | None = Header(None)) -> CurrentUser | None:
    """Optional auth: ``None`` when no bearer token is sent; 401 when one is sent but invalid."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    try:
        payload = decode_token_strict(token.strip())
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user_id = subject_of(payload)
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject identifier")
    role = payload.get("role", "user")
    if role not in ROLES:
        raise HTTPException(status_code=401, detail="Token carries an unknown role")
    return CurrentUser(user_id=user_id, role=role, clinic_id=payload.get("clinic_id"))


def require_current_user(user: CurrentUser | None = Depends(get_current_user)) -> CurrentUser:
    if user:
        return user
    settings = get_settings()
    if settings.allow_unauthenticated_demo_user and not settings.is_strict:
        logger.warning("security_auth_bypass_triggered", detail="demo user substituted (dev only)")
        return CurrentUser(user_id="demo-user-123", role="user")
    raise HTTPException(status_code=401, detail="Authentication required")


def require_role(*roles: str) -> Callable[[CurrentUser], CurrentUser]:
    """Dependency factory: caller must hold one of ``roles`` (``admin`` always passes)."""
    unknown = set(roles) - ROLES
    if unknown:
        raise ValueError(f"unknown roles: {unknown}")

    def _guard(user: CurrentUser = Depends(require_current_user)) -> CurrentUser:
        if user.role == "admin" or user.role in roles:
            return user
        raise HTTPException(status_code=403, detail="Insufficient role for this operation")

    return _guard


def ensure_clinic_access(user: CurrentUser, clinic_id: str) -> None:
    """Tenant guard: clinic-scoped data is visible only to that clinic (or admin/regulator)."""
    if user.role in ("admin", "regulator", "auditor"):
        return
    if not user.clinic_id or user.clinic_id != clinic_id:
        raise HTTPException(status_code=403, detail="Not authorised for this clinic")
