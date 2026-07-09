"""
Sarvam mapping logic — isolated to Sarvam.

Sarvam needs a full language code (e.g. "bn-IN", "en-IN"). This maps the
provider-agnostic config.language onto Sarvam's `target_language_code`.
"""
from __future__ import annotations

_FALLBACK_LANGUAGE = "en-IN"
_SHORT_TO_FULL = {"bn": "bn-IN", "en": "en-IN", "hi": "hi-IN"}


def target_language(language: str | None) -> str:
    """Return a Sarvam-style full language code like 'bn-IN'."""
    lang = (language or "").strip() or _FALLBACK_LANGUAGE
    if "-" in lang:
        return lang
    return _SHORT_TO_FULL.get(lang.lower(), _FALLBACK_LANGUAGE)
