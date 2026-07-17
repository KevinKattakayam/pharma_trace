"""
FastAPI dependencies for JWT authentication and dynamic CurrentUser context injection.
"""
import jwt
from fastapi import Header, HTTPException, Depends
from typing import Optional
from config import get_settings
from models.schemas import CurrentUser


def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[CurrentUser]:
    """
    Dependency to validate JWT and extract user context into a CurrentUser object.
    Optional for public endpoints (returns None if no token provided).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.split(" ")[1]
    settings = get_settings()
    
    try:
        secret = settings.jwt_secret
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": True, "verify_signature": True}
        )
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("uid")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing subject identifier (sub/user_id)")
            
        return CurrentUser(
            user_id=str(user_id),
            role=payload.get("role", "user"),
            clinic_id=payload.get("clinic_id")
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token signature or format")


def require_current_user(user: Optional[CurrentUser] = Depends(get_current_user)) -> CurrentUser:
    """
    Strict dependency for protected routes (/cabinet, /push, /caregiver).
    Requires valid JWT authentication. In local testing/demo mode, only falls back to demo user
    if allow_unauthenticated_demo_user is explicitly set to True in configuration.
    """
    if not user:
        settings = get_settings()
        if settings.allow_unauthenticated_demo_user and settings.environment != "prod":
            import structlog
            logger = structlog.get_logger()
            logger.warning("security_auth_bypass_triggered", detail="Unauthenticated request allowed as demo-user-123 because allow_unauthenticated_demo_user=True")
            return CurrentUser(user_id="demo-user-123", role="user")
        raise HTTPException(status_code=401, detail="401 Unauthorized: Valid authentication token required.")
    return user
