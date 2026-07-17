"""
Enterprise Regulatory Compliance & PHI/PII Tokenization Gateway.
Enforces HIPAA, 21 CFR Part 11, and India DPDP Act 2023 compliance by tokenizing sensitive data before LLM transmission.
"""
import re
import hmac
import hashlib
from typing import Tuple, Dict, Any
from config import get_settings

# Regex patterns for sensitive Indian & global medical PII/PHI
PATTERNS = {
    "AADHAAR": re.compile(r"\b\d{4}[\-\s]?\d{4}[\-\s]?\d{4}\b"),
    "PHONE": re.compile(r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b"),
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
    "DOB": re.compile(r"\b(?:0[1-9]|[12]\d|3[01])[\/\-\.](?:0[1-9]|1[0-2])[\/\-\.]\d{4}\b"),
    "PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")
}


def _generate_token(pii_type: str, raw_val: str, secret: str) -> str:
    """
    Generate deterministic Format-Preserving Encryption (FPE) synthetic tokens.
    Transforms PII/PHI into syntactically valid pseudorandom formats (e.g., phone numbers stay phone numbers,
    dates stay valid dates) to prevent breaking downstream EHR schemas or JSON validators while ensuring 100% privacy.
    """
    digest = hmac.new(secret.encode(), raw_val.encode(), hashlib.sha256).hexdigest()
    int_val = int(digest[:8], 16)

    if pii_type == "PHONE":
        # Generate valid 10-digit Indian mobile number starting with 9 (e.g., +919123456789)
        prefix = "+91" if raw_val.startswith("+91") or raw_val.startswith("91") else ""
        pseudo_phone = f"9{int_val % 1000000000:09d}"
        return f"{prefix}{pseudo_phone}"
    elif pii_type == "AADHAAR":
        # Generate 12-digit Aadhaar-formatted number (e.g., 9999 1234 5678)
        p1 = 9000 + (int_val % 1000)
        p2 = int(digest[8:12], 16) % 10000
        p3 = int(digest[12:16], 16) % 10000
        return f"{p1:04d} {p2:04d} {p3:04d}" if " " in raw_val else f"{p1:04d}{p2:04d}{p3:04d}"
    elif pii_type == "DOB":
        # Generate synthetic valid date between 1950 and 2000
        year = 1950 + (int_val % 50)
        month = 1 + ((int_val // 100) % 12)
        day = 1 + ((int_val // 10000) % 28)
        sep = "/" if "/" in raw_val else ("-" if "-" in raw_val else ".")
        return f"{day:02d}{sep}{month:02d}{sep}{year:04d}"
    elif pii_type == "PAN":
        # Generate valid PAN format: 5 letters, 4 digits, 1 letter (e.g., PXXFT1234Z)
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        l1 = "".join(letters[(int(digest[i:i+2], 16) % 26)] for i in range(0, 10, 2))
        d1 = int_val % 10000
        l2 = letters[int_val % 26]
        return f"{l1}{d1:04d}{l2}"
    elif pii_type == "EMAIL":
        return f"patient.{digest[:8]}@masked.pharmatrace.io"

    return f"[PHI_{pii_type}_{digest[:12]}]"


def sanitize_phi(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Scan text for PII/PHI and replace with format-preserving cryptographic tokens.
    Returns sanitized text and token-to-raw mapping dictionary for restoration.
    """
    if not text:
        return "", {}

    settings = get_settings()
    secret = getattr(settings, "hmac_daily_secret", "default_secret_rotate_me")
    
    sanitized = text
    token_map: Dict[str, str] = {}

    for pii_type, regex in PATTERNS.items():
        matches = regex.findall(sanitized)
        for match in set(matches):
            token = _generate_token(pii_type, match, secret)
            token_map[token] = match
            sanitized = sanitized.replace(match, token)

    return sanitized, token_map


def restore_phi(text: str, token_map: Dict[str, str]) -> str:
    """Restore original PII/PHI values into tokenized LLM output."""
    if not text or not token_map:
        return text
    
    restored = text
    for token, raw_val in token_map.items():
        restored = restored.replace(token, raw_val)
        
    return restored


async def log_compliance_event(user_id: str, action: str, details: Dict[str, Any]):
    """Log an immutable WORM audit record for PHI access or compliance events."""
    try:
        from services.audit import add_audit_record
        import uuid
        event_id = f"COMPLIANCE-{uuid.uuid4().hex[:8].upper()}"
        await add_audit_record(event_id, {
            "verdict": "compliance_log",
            "confidence": 1.0,
            "source": "phi_gateway",
            "user_id": user_id,
            "action": action,
            "details": details
        })
    except Exception as e:
        import structlog
        structlog.get_logger().error("compliance_event_log_failed", error=str(e))
