"""A deliberately narrow Wikimedia summary client for reader lookups."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class EncyclopediaError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EncyclopediaSummary:
    found: bool
    title: str | None = None
    description: str | None = None
    extract: str | None = None
    source_url: str | None = None
    attribution: str = "Wikipedia · CC BY-SA 4.0"


class WikimediaEncyclopedia:
    _semaphore = threading.BoundedSemaphore(3)

    @staticmethod
    def language_code(language: str) -> str:
        if not isinstance(language, str):
            raise EncyclopediaError("encyclopedia_unavailable")
        code = language.split("-", 1)[0].strip().casefold()
        if not code or not code.isalpha() or len(code) > 8:
            raise EncyclopediaError("encyclopedia_unavailable")
        return code

    def lookup(self, language: str, text: str) -> EncyclopediaSummary:
        if not isinstance(text, str) or not text.strip() or len(text) > 120 or any(ord(char) < 32 for char in text):
            raise EncyclopediaError("invalid_encyclopedia_query")
        locale = self.language_code(language)
        url = "https://" + locale + ".wikipedia.org/api/rest_v1/page/summary/" + quote(text.strip(), safe="")
        request = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "EPUBBrowser/1.0 (https://github.com/dfface/epub-browser)",
        })
        if not self._semaphore.acquire(timeout=3):
            raise EncyclopediaError("encyclopedia_busy")
        try:
            try:
                with urlopen(request, timeout=3) as result:  # nosec B310: fixed Wikimedia host
                    payload = json.loads(result.read(256 * 1024).decode("utf-8"))
            except HTTPError as error:
                if error.code == 404:
                    return EncyclopediaSummary(found=False)
                if error.code == 429:
                    raise EncyclopediaError("encyclopedia_rate_limited") from error
                raise EncyclopediaError("encyclopedia_unavailable") from error
            except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
                raise EncyclopediaError("encyclopedia_unavailable")
        finally:
            self._semaphore.release()
        if not isinstance(payload, dict) or payload.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
            return EncyclopediaSummary(found=False)
        content_urls = payload.get("content_urls") if isinstance(payload.get("content_urls"), dict) else {}
        desktop = content_urls.get("desktop") if isinstance(content_urls.get("desktop"), dict) else {}
        page_url = desktop.get("page")
        return EncyclopediaSummary(
            found=True,
            title=payload.get("title") if isinstance(payload.get("title"), str) else None,
            description=payload.get("description") if isinstance(payload.get("description"), str) else None,
            extract=payload.get("extract") if isinstance(payload.get("extract"), str) else None,
            source_url=page_url if isinstance(page_url, str) and page_url.startswith("https://") else None,
        )
