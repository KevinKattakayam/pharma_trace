import jwt
from fastapi import Header, HTTPException
from typing import Optional
from config import get_settings

def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Dependency to validate JWT and extract clinic_id.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization.split(" ")[1]
    settings = get_settings()
    
    try:
        # In a real app, use the actual JWT secret.
        # We assume the secret is in settings or use a fallback for prototyping.
        secret = getattr(settings, 'jwt_secret', 'mock_secret_key_for_development')
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        
        # Verify clinic_id exists in the payload
        clinic_id = payload.get("clinic_id")
        if not clinic_id:
            raise HTTPException(status_code=403, detail="User not assigned to a clinic")
            
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
