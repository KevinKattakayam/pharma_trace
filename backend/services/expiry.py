import re
from datetime import date

from dateutil import parser as dateparser

EXPIRY_PATTERNS = [
    r'exp[iry\s:\.]*(\d{2}[/-]\d{2,4})',
    r'use\s+before[:\s]+(\w+\s+\d{4})',
    r'best\s+before[:\s]+(\w+\s+\d{4})',
    r'expiry[:\s]+(\d{2}[/-]\d{2,4})',
    r'expires?[:\s]+(\d{2}[/-]\d{2,4})',
    r'e[:\s]+(\d{2}[/-]\d{2,4})',
    r'समाप्ति[:\s]*(\d{2}[/-]\d{2,4})',
    r'കാലഹരണ[:\s]*(\d{2}[/-]\d{2,4})'
]

def extract_expiry_date(text: str) -> dict:
    if not text:
        return {"expiry_date": None, "days_remaining": None, "status": "unknown"}
        
    text_lower = text.lower()
    for pattern in EXPIRY_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            try:
                date_str = match.group(1)
                parsed = dateparser.parse(date_str)
                if parsed:
                    days_remaining = (parsed.date() - date.today()).days
                    if days_remaining < 0:
                        status = "expired"
                    elif days_remaining < 30:
                        status = "expiring_soon"
                    else:
                        status = "safe"
                    return {
                        "expiry_date": parsed.strftime("%B %Y"),
                        "days_remaining": days_remaining,
                        "status": status,
                        "raw_date": parsed.strftime("%Y-%m-%dT00:00:00Z")
                    }
            except Exception:
                continue
    return {"expiry_date": None, "days_remaining": None, "status": "unknown"}
