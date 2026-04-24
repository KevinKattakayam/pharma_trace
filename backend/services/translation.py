"""
Translation service using LibreTranslate (free, self-hosted or public instances).
Rewrites drug information in the user's local language.
"""
import httpx
from typing import Optional

# Free public LibreTranslate instances (no API key required)
LIBRETRANSLATE_URLS = [
    "https://libretranslate.com",
    "https://translate.argosopentech.com",
    "https://translate.terraprint.co",
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


def get_supported_languages() -> dict:
    """Return all supported languages with codes and display names."""
    return LANGUAGES
