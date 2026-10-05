"""
Translation service using LibreTranslate (free, self-hosted or public instances).
Rewrites drug information in the user's local language.
"""
import os
import unicodedata
from typing import Optional

import httpx

# Self-hosted LibreTranslate instance (Docker)
LIBRETRANSLATE_URLS = [
    os.getenv("LIBRETRANSLATE_URL", "https://libretranslate.com")
]

# Supported languages with display names
LANGUAGES = {
    "en": "English",
    "hi": "हिन्दी (Hindi)",
    "es": "Español (Spanish)",
    "fr": "Français (French)",
    "pt": "Português (Portuguese)",
    "ar": "العربية (Arabic)",
    "bn": "বাংলা (Bengali)",
    "zh": "中文 (Chinese)",
    "sw": "Kiswahili (Swahili)",
    "ta": "தமிழ் (Tamil)",
    "te": "తెలుగు (Telugu)",
    "ur": "اردو (Urdu)",
    "de": "Deutsch (German)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "ru": "Русский (Russian)",
    "tr": "Türkçe (Turkish)",
    "vi": "Tiếng Việt (Vietnamese)",
    "id": "Bahasa Indonesia",
    "th": "ไทย (Thai)",
}

def contains_non_latin(text: str) -> bool:
    return any(
        unicodedata.name(c, "").startswith(("MALAYALAM", "DEVANAGARI", "TAMIL", 
        "TELUGU", "BENGALI", "GUJARATI", "GURMUKHI", "KANNADA", "ORIYA"))
        for c in text if c.strip()
    )

async def resolve_script_to_latin(query: str) -> str:
    if not contains_non_latin(query):
        return query
    transliterated = await translate_text(query, target_lang="en", source_lang="auto")
    return transliterated or query


async def translate_text(text: str, target_lang: str, source_lang: str = "en") -> Optional[str]:
    """
    Translate text using LibreTranslate free API.
    Falls back through multiple public instances.
    """
    if target_lang == source_lang or target_lang == "en":
        return text

    async with httpx.AsyncClient(timeout=15.0) as client:
        for base_url in LIBRETRANSLATE_URLS:
            try:
                resp = await client.post(
                    f"{base_url}/translate",
                    json={
                        "q": text,
                        "source": source_lang,
                        "target": target_lang,
                        "format": "text"
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    translated = data.get("translatedText")
                    if translated:
                        return translated
            except Exception:
                continue

    # If all instances fail, return original text
    return text


async def translate_side_effects(side_effects: list[dict], target_lang: str) -> list[dict]:
    """Translate a list of side effect descriptions to the target language."""
    if target_lang == "en":
        return side_effects

    translated = []
    for se in side_effects:
        desc = await translate_text(se.get("description", ""), target_lang)
        translated.append({
            **se,
            "description": desc,
            "original_description": se.get("description", ""),
            "language": target_lang
        })
    return translated


async def translate_drug_info(info: dict, target_lang: str) -> dict:
    """Translate key drug information fields to the target language."""
    if target_lang == "en":
        return info

    translatable_fields = ["product_type", "route"]
    result = {**info, "language": target_lang}

    for field in translatable_fields:
        if info.get(field):
            result[field] = await translate_text(info[field], target_lang)
            
    return result


import re

# Terms that must survive translation unchanged
PROTECTED_PATTERNS = [
    r"\b\d+\s*(mg|mcg|ml|g|IU|units?)\b",  # dosages
    r"\b[A-Z][a-z]+(cin|mycin|cillin|prazole|sartan|mab|nib)\b",  # drug suffixes
    r"\b(OD|BD|TDS|QID|HS|AC|PC|SOS)\b",  # prescription abbreviations
]


def mask_protected_terms(text: str) -> tuple[str, dict]:
    """Replace protected terms with placeholders before translation."""
    placeholders = {}
    masked = text
    counter = 0

    all_matches = []
    for pattern in PROTECTED_PATTERNS:
        for m in re.finditer(pattern, masked, re.IGNORECASE):
            all_matches.append((m.start(), m.end(), m.group()))

    # Sort by start position, deduplicate
    seen_spans = set()
    for start, end, term in sorted(all_matches):
        if (start, end) not in seen_spans:
            seen_spans.add((start, end))
            key = f"__TERM_{counter}__"
            placeholders[key] = term
            masked = masked[:start] + key + masked[end:]
            counter += 1

    return masked, placeholders


def restore_protected_terms(translated: str, placeholders: dict) -> str:
    for key, term in placeholders.items():
        translated = translated.replace(key, term)
    return translated


async def translate_medical_text(text: str, target_lang: str) -> str:
    """Translate with medical term protection."""
    if target_lang == "en":
        return text

    masked_text, placeholders = mask_protected_terms(text)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Iterate over public LibreTranslate instances
        for base_url in LIBRETRANSLATE_URLS:
            try:
                r = await client.post(
                    f"{base_url}/translate",
                    json={
                        "q": masked_text,
                        "source": "en",
                        "target": target_lang,
                        "format": "text"
                    },
                    headers={"Content-Type": "application/json"}
                )
                if r.status_code == 200:
                    translated = r.json().get("translatedText", masked_text)
                    return restore_protected_terms(translated, placeholders)
            except Exception:
                continue

    return restore_protected_terms(masked_text, placeholders)


def get_supported_languages() -> dict:
    """Return all supported languages with codes and display names."""
    return LANGUAGES
