"""SlowAPI Rate Limiter Service for PharmaTrace API."""
from slowapi import Limiter
from starlette.requests import Request
import jwt

def auth_or_ip_key_func(request: Request) -> str:
    """Derive rate limit key from JWT user_id or IP address."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        try:
            token = auth.split(" ")[1]
            payload = jwt.decode(token, options={"verify_signature": False})
            uid = payload.get("sub") or payload.get("user_id")
            if uid:
                return f"user:{uid}"
        except Exception:
            pass
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

# Global limiter instance
limiter = Limiter(key_func=auth_or_ip_key_func, default_limits=["100/minute"])
