import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


def normalize_base_path(value: str) -> str:
    candidate = (value or "/").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"Base path must be a URL path without host, query, or fragment: {value}")
    if "\\" in candidate:
        raise ValueError("Base path cannot contain backslashes")
    segments = [segment for segment in candidate.split("/") if segment]
    if any(segment in {".", ".."} for segment in segments):
        raise ValueError("Base path cannot contain dot segments")
    if not segments:
        return "/"
    return "/" + "/".join(segments) + "/"


@dataclass(frozen=True)
class SiteURLs:
    base_path: str = "/"

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_path", normalize_base_path(self.base_path))

    def public(self, path: str) -> str:
        if path.startswith("//"):
            raise ValueError(f"Protocol-relative URL is not an internal path: {path}")
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc:
            raise ValueError(f"External URL is not an internal path: {path}")
        normalized_path = parsed.path or "/"
        if self.base_path != "/" and normalized_path.startswith(self.base_path):
            result = normalized_path
        elif normalized_path == "/":
            result = self.base_path
        else:
            result = posixpath.join(self.base_path, normalized_path.lstrip("/"))
            if normalized_path.endswith("/") and not result.endswith("/"):
                result += "/"
        if parsed.query:
            result += "?" + parsed.query
        if parsed.fragment:
            result += "#" + parsed.fragment
        return result

    def filesystem_relative(self, public_url: str) -> Path:
        parsed = urlsplit(public_url)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError(f"Public asset URL is not a filesystem path: {public_url}")
        if not parsed.path.startswith(self.base_path):
            raise ValueError(f"URL is outside base path {self.base_path}: {public_url}")
        relative = parsed.path[len(self.base_path):]
        if not relative:
            raise ValueError("Base path itself does not identify a file")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Unsafe public asset path: {public_url}")
        return candidate


_ROOT_URL_ATTRIBUTE = re.compile(
    r"(?P<prefix>\b(?:href|src|content)\s*=\s*['\"])(?P<url>/[^'\"]*)(?P<suffix>['\"])",
    re.IGNORECASE,
)


def rewrite_root_urls(html: str, urls: SiteURLs) -> str:
    if urls.base_path == "/":
        return html

    def replace(match: re.Match) -> str:
        value = match.group("url")
        if value.startswith("//") or value.startswith(urls.base_path):
            return match.group(0)
        return match.group("prefix") + urls.public(value) + match.group("suffix")

    return _ROOT_URL_ATTRIBUTE.sub(replace, html)
