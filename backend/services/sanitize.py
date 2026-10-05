"""Input Sanitization Service against Prompt Injection and Malicious Payloads."""
import re

from fastapi import HTTPException

# Whitelist: alphanumeric, standard hyphens, spaces, dots, parentheses, slashes (max 100 chars)
DRUG_NAME_WHITELIST = re.compile(r"^[a-zA-Z0-9\s\-.,()+/]{1,100}$")

PROMPT_INJECTION_KEYWORDS = [
    "ignore all previous", "system prompt", "output prompt", "forget instructions",
    "bypass", "jailbreak", "as an ai", "act as", "repeat system", "override"
]


def sanitize_drug_input(user_input: str, source: str = "text") -> str:
    """
    Sanitize user or voice-transcribed drug input before LLM prompt injection.
    Enforces regex whitelist and prompt injection pattern detection.
    """
    if not user_input or not isinstance(user_input, str):
        raise HTTPException(status_code=400, detail="Invalid drug input provided")
        
    cleaned = user_input.strip()
    if len(cleaned) > 100:
        raise HTTPException(status_code=400, detail="Input exceeds maximum limit of 100 characters")
        
    if not DRUG_NAME_WHITELIST.match(cleaned):
        raise HTTPException(
            status_code=400, 
            detail="SECURITY VIOLATION: Input contains non-whitelisted characters. Only alphanumeric characters and standard drug punctuation are allowed."
        )
        
    # Check against prompt injection patterns (critical for voice transcription path)
    lower = cleaned.lower()
    for kw in PROMPT_INJECTION_KEYWORDS:
        if kw in lower:
            raise HTTPException(
                status_code=400,
                detail=f"SECURITY VIOLATION [{source}]: Prompt injection pattern detected."
            )
            
    return cleaned
