"""Small, dependency-free OpenAI-compatible chat client.

Provider details stay on the server.  Callers receive stable, non-sensitive
error codes only; URLs, response payloads, and credentials are intentionally
never embedded in exceptions.
"""

import json
import socket
from dataclasses import dataclass
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


class AIProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable_without_response: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable_without_response = retryable_without_response


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    max_concurrency: int = 2

    @classmethod
    def from_settings(cls, settings: dict) -> "ProviderConfig":
        return cls(
            base_url=validate_provider_base_url(settings.get("base_url", "")),
            api_key=str(settings.get("api_key", "")),
            model=str(settings.get("model", "")).strip(),
            timeout_seconds=int(settings.get("timeout_seconds", 60)),
            max_concurrency=int(settings.get("max_concurrency", 2)),
        )


def validate_provider_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("AI Provider base URL must be text")
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("AI Provider base URL must be an HTTP(S) origin or path")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class OpenAICompatibleClient:
    def __init__(self, config: ProviderConfig, opener: Callable = urlopen):
        if not config.api_key or not config.model:
            raise ValueError("AI Provider key and model are required")
        if not 5 <= config.timeout_seconds <= 3600:
            raise ValueError("AI Provider timeout is out of range")
        if not 1 <= config.max_concurrency <= 4:
            raise ValueError("AI Provider concurrency is out of range")
        self._config = config
        self._opener = opener

    @property
    def endpoint(self) -> str:
        return self._config.base_url + "/chat/completions"

    def complete(self, messages: Sequence[dict], *, temperature: float = 0.2) -> str:
        if not isinstance(messages, Sequence) or not messages:
            raise ValueError("AI messages are required")
        payload = json.dumps(
            {
                "model": self._config.model,
                "messages": list(messages),
                "temperature": temperature,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": "Bearer " + self._config.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._config.timeout_seconds) as response:
                body = response.read()
        except HTTPError as error:
            if error.code == 429:
                raise AIProviderError("provider_rate_limited") from None
            if 400 <= error.code < 500:
                raise AIProviderError("provider_request_rejected") from None
            # Gateways and hosted OpenAI-compatible providers commonly return
            # a transient 5xx while a large model is warming up.  The caller
            # accounts for the retry as another real provider attempt.
            raise AIProviderError(
                "provider_server_error", retryable_without_response=True
            ) from None
        except (URLError, socket.timeout, TimeoutError, ConnectionError):
            raise AIProviderError(
                "provider_connection_failed", retryable_without_response=True
            ) from None
        except OSError:
            raise AIProviderError(
                "provider_connection_failed", retryable_without_response=True
            ) from None
        try:
            decoded = json.loads(body.decode("utf-8"))
            content = decoded["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            raise AIProviderError("provider_invalid_response") from None
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("provider_invalid_response")
        return content.strip()
