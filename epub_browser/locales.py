SUPPORTED_LOCALES = ("en", "zh-CN", "zh-TW", "ko", "ja")
SUPPORTED_LOCALE_SET = frozenset(SUPPORTED_LOCALES)

PROMPT_LANGUAGE_NAMES = {
    "en": "English",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "ko": "Korean",
    "ja": "Japanese",
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
    return default
