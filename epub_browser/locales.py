SUPPORTED_LOCALES = (
    "en", "zh-CN", "zh-TW", "ko", "ja",
    "es", "de", "fr", "ru", "it", "pt-BR", "ar", "id", "hi", "vi", "th", "ms",
)
SUPPORTED_LOCALE_SET = frozenset(SUPPORTED_LOCALES)

LOCALE_NATIVE_NAMES = {
    "en": "English",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "ko": "한국어",
    "ja": "日本語",
    "es": "Español",
    "de": "Deutsch",
    "fr": "Français",
    "ru": "Русский",
    "it": "Italiano",
    "pt-BR": "Português (Brasil)",
    "ar": "العربية",
    "id": "Bahasa Indonesia",
    "hi": "हिन्दी",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "ms": "Bahasa Melayu",
}

PROMPT_LANGUAGE_NAMES = {
    "en": "English",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "ko": "Korean",
    "ja": "Japanese",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "it": "Italian",
    "pt-BR": "Brazilian Portuguese",
    "ar": "Arabic",
    "id": "Indonesian",
    "hi": "Hindi",
    "vi": "Vietnamese",
    "th": "Thai",
    "ms": "Malay",
}


def normalize_locale(value, default=""):
    candidate = str(value or "").replace("_", "-").lower()
    if candidate == "zh" or candidate.startswith(("zh-cn", "zh-sg")):
        return "zh-CN"
    if candidate.startswith(("zh-tw", "zh-hk", "zh-mo")):
        return "zh-TW"
    if candidate == "ko" or candidate.startswith("ko-"):
        return "ko"
    if candidate == "ja" or candidate.startswith("ja-"):
        return "ja"
    if candidate == "en" or candidate.startswith("en-"):
        return "en"
    if candidate == "pt" or candidate.startswith(("pt-br", "pt-pt")):
        return "pt-BR"
    for code in ("es", "de", "fr", "ru", "it", "ar", "id", "hi", "vi", "th", "ms"):
        if candidate == code or candidate.startswith(code + "-"):
            return code
    return default
