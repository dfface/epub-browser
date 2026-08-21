import io
import json
import socket
import unittest
from urllib.error import HTTPError, URLError

from epub_browser.ai_client import (
    AIProviderError,
    OpenAICompatibleClient,
    ProviderConfig,
    validate_provider_base_url,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self):
        return self.payload


class AIClientTests(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(
            base_url="https://provider.example/v1",
            api_key="test-secret",
            model="reader-model",
            timeout_seconds=30,
        )

    def test_posts_openai_compatible_payload_without_exposing_key(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return _Response(
                json.dumps(
                    {"choices": [{"message": {"content": "  Answer  "}}]}
                ).encode()
            )

        client = OpenAICompatibleClient(self.config, opener=opener)
        self.assertEqual(client.complete([{"role": "user", "content": "Read"}]), "Answer")
        request, timeout = calls[0]
        self.assertEqual(request.full_url, "https://provider.example/v1/chat/completions")
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(json.loads(request.data), {
            "model": "reader-model",
            "messages": [{"role": "user", "content": "Read"}],
            "temperature": 0.2,
        })

    def test_maps_provider_failures_to_safe_error_codes(self):
        def rejected(request, timeout):
            raise HTTPError(request.full_url, 401, "ignored", {}, io.BytesIO(b"secret"))

        with self.assertRaisesRegex(AIProviderError, "provider_request_rejected"):
            OpenAICompatibleClient(self.config, opener=rejected).complete(
                [{"role": "user", "content": "Read"}]
            )

        def failed_connection(request, timeout):
            raise URLError(socket.timeout("ignored"))

        with self.assertRaises(AIProviderError) as raised:
            OpenAICompatibleClient(self.config, opener=failed_connection).complete(
                [{"role": "user", "content": "Read"}]
            )
        self.assertEqual(raised.exception.code, "provider_connection_failed")
        self.assertTrue(raised.exception.retryable_without_response)

    def test_rejects_unsafe_provider_urls(self):
        self.assertEqual(
            validate_provider_base_url(" https://provider.example/v1/ "),
            "https://provider.example/v1",
        )
        for unsafe in ("", "file:///tmp/key", "https://user:pass@example.com", "https://example.com/?key=x"):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(ValueError):
                    validate_provider_base_url(unsafe)

    def test_allows_a_one_hour_provider_timeout(self):
        long_running = ProviderConfig(
            base_url="https://provider.example/v1",
            api_key="test-secret",
            model="reader-model",
            timeout_seconds=3600,
        )
        OpenAICompatibleClient(long_running)
        too_long = ProviderConfig(
            base_url="https://provider.example/v1",
            api_key="test-secret",
            model="reader-model",
            timeout_seconds=3601,
        )
        with self.assertRaisesRegex(ValueError, "timeout"):
            OpenAICompatibleClient(too_long)
