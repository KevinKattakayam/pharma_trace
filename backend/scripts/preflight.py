"""Fail-fast production configuration check.

Run before deployment:
  python -m scripts.preflight

It intentionally never prints secret values.
"""
import sys

from config import get_settings


def main() -> int:
    try:
        settings = get_settings()
    except Exception as exc:
        print(f"FAIL: configuration is invalid: {exc}")
        return 1

    problems = []
    warnings = []
    if settings.environment == "prod":
        if settings.debug:
            problems.append("DEBUG must be false in production")
        if not settings.supabase_url or not settings.supabase_key:
            problems.append("SUPABASE_URL and SUPABASE_KEY are required for production persistence")
        if not settings.cors_origins:
            problems.append("CORS_ORIGINS must name the frontend domain")
    if not settings.manufacturer_verification_url:
        warnings.append("Manufacturer serial verification is not configured; pack results remain review-required")
    if not settings.clinical_interaction_provider_url:
        warnings.append("Clinical interaction provider is not configured; interaction results remain review-required")

    for warning in warnings:
        print(f"WARN: {warning}")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1

    print(f"PASS: {settings.environment} configuration is valid for deployment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
