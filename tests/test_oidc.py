import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from epub_browser.auth import BootstrapCredentials
from epub_browser.oidc import OIDCError, OIDCService
from epub_browser.state import StateStore


ISSUER = "https://identity.example.test"
NOW = 1_800_000_000.0


class OIDCServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = StateStore(Path(self.temporary.name, "state.db"))
        self.store.initialize(BootstrapCredentials("owner", "secret"))
        self.settings = {
            "enabled": True,
            "provider_name": "Company SSO",
            "issuer_url": ISSUER,
            "client_id": "epub-browser",
            "client_secret": "client-secret",
            "redirect_uri": "https://reader.example.test/auth/oidc/callback",
            "scopes": ("openid", "profile", "email"),
            "username_claim": "preferred_username",
            "config_revision": 3,
        }

    async def asyncTearDown(self):
        client = getattr(self, "client", None)
        if client is not None:
            await client.aclose()

    def _metadata(self, **updates):
        metadata = {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/api/authorize",
            "token_endpoint": f"{ISSUER}/api/token",
            "jwks_uri": f"{ISSUER}/jwks.json",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
        }
        metadata.update(updates)
        return metadata

    def _service(self, handler, *, max_response_bytes=64 * 1024):
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return OIDCService(
            self.store,
            http_client=self.client,
            clock=lambda: NOW,
            max_response_bytes=max_response_bytes,
        )

    async def test_begin_discovers_provider_and_builds_s256_authorization_request(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=self._metadata())

        service = self._service(handler)
        start = await service.begin(
            self.settings,
            purpose="login",
            next_path="/book/book-1/chapter_1.html",
            expected_user_id=None,
        )

        query = parse_qs(urlparse(start.authorization_url).query)
        self.assertEqual(query["client_id"], ["epub-browser"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["scope"], ["openid profile email"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(len(query["code_challenge"][0]), 43)
        self.assertEqual(query["state"], [start.state])
        self.assertEqual(query["nonce"], [start.nonce])
        self.assertNotIn(start.browser_token, start.authorization_url)
        self.assertEqual(
            requests[0].url,
            httpx.URL(f"{ISSUER}/.well-known/openid-configuration"),
        )

    async def test_discovery_requires_exact_issuer_https_endpoints_and_s256(self):
        cases = (
            (self._metadata(issuer=f"{ISSUER}/other"), "discovery_invalid"),
            (self._metadata(token_endpoint="http://identity.example.test/token"), "discovery_invalid"),
            (self._metadata(code_challenge_methods_supported=["plain"]), "configuration_unsupported"),
            (self._metadata(response_types_supported=["id_token"]), "configuration_unsupported"),
            (self._metadata(id_token_signing_alg_values_supported=7), "discovery_invalid"),
            ({"issuer": ISSUER}, "discovery_invalid"),
        )
        for metadata, expected_code in cases:
            with self.subTest(metadata=metadata):
                service = self._service(lambda request: httpx.Response(200, json=metadata))
                with self.assertRaises(OIDCError) as raised:
                    await service.begin(
                        self.settings,
                        purpose="login",
                        next_path="/",
                        expected_user_id=None,
                    )
                self.assertEqual(raised.exception.code, expected_code)
                await self.client.aclose()
                self.client = None

    async def test_redirect_uri_must_use_the_exact_callback_path(self):
        for redirect_uri in (
            "https://reader.example.test/not-the-callback",
            "https://reader.example.test/auth/oidc/callback?tenant=one",
        ):
            with self.subTest(redirect_uri=redirect_uri):
                service = self._service(
                    lambda request: httpx.Response(200, json=self._metadata())
                )
                with self.assertRaises(OIDCError) as raised:
                    await service.begin(
                        dict(self.settings, redirect_uri=redirect_uri),
                        purpose="login",
                        next_path="/",
                        expected_user_id=None,
                    )
                self.assertEqual(raised.exception.code, "configuration_invalid")
                await self.client.aclose()
                self.client = None

    async def test_loopback_http_is_allowed_but_remote_http_issuer_is_rejected(self):
        loopback = dict(self.settings, issuer_url="http://127.0.0.1:9091")
        metadata = self._metadata(
            issuer=loopback["issuer_url"],
            authorization_endpoint="http://127.0.0.1:9091/authorize",
            token_endpoint="http://127.0.0.1:9091/token",
            jwks_uri="http://127.0.0.1:9091/jwks",
        )
        service = self._service(lambda request: httpx.Response(200, json=metadata))
        start = await service.begin(loopback, purpose="login", next_path="/", expected_user_id=None)
        self.assertTrue(start.authorization_url.startswith("http://127.0.0.1:9091/authorize?"))

        remote = dict(self.settings, issuer_url="http://identity.example.test")
        with self.assertRaises(OIDCError) as raised:
            await service.begin(remote, purpose="login", next_path="/", expected_user_id=None)
        self.assertEqual(raised.exception.code, "configuration_invalid")

    async def test_discovery_is_bounded_and_transport_errors_are_stable(self):
        oversized = json.dumps(self._metadata()).encode() + (b" " * 200)
        service = self._service(
            lambda request: httpx.Response(200, content=oversized),
            max_response_bytes=100,
        )
        with self.assertRaises(OIDCError) as raised:
            await service.begin(self.settings, purpose="login", next_path="/", expected_user_id=None)
        self.assertEqual(raised.exception.code, "provider_response_too_large")

        await self.client.aclose()
        service = self._service(
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("secret upstream detail"))
        )
        with self.assertRaises(OIDCError) as raised:
            await service.begin(self.settings, purpose="login", next_path="/", expected_user_id=None)
        self.assertEqual(raised.exception.code, "provider_unavailable")
        self.assertNotIn("secret upstream detail", str(raised.exception))

    async def test_callback_validates_signed_id_token_and_returns_normalized_claims(self):
        from authlib.jose import JsonWebKey, jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        jwk = JsonWebKey.import_key(public_pem, {"kid": "key-1", "use": "sig"}).as_dict()
        start_holder = {}

        def handler(request):
            if request.url.path.endswith("openid-configuration"):
                return httpx.Response(200, json=self._metadata())
            if request.url.path == "/jwks.json":
                return httpx.Response(200, json={"keys": [jwk]})
            if request.url.path == "/api/token":
                form = parse_qs(request.content.decode())
                self.assertEqual(form["code_verifier"], [start_holder["start"].pkce_verifier])
                claims = {
                    "iss": ISSUER,
                    "sub": "subject-123",
                    "aud": "epub-browser",
                    "nonce": start_holder["start"].nonce,
                    "iat": int(NOW),
                    "exp": int(NOW + 300),
                    "preferred_username": "remote-reader",
                    "name": "Remote Reader",
                    "email": "reader@example.test",
                }
                token = jwt.encode({"alg": "RS256", "kid": "key-1"}, claims, private_pem)
                return httpx.Response(200, json={"id_token": token.decode(), "access_token": "discard-me"})
            raise AssertionError(f"Unexpected request: {request.url}")

        service = self._service(handler)
        start = await service.begin(self.settings, purpose="login", next_path="/library", expected_user_id=None)
        start_holder["start"] = start
        completion = await service.complete(
            self.settings,
            state=start.state,
            browser_token=start.browser_token,
            code="provider-code",
        )

        self.assertEqual(completion.transaction.next_path, "/library")
        self.assertEqual(completion.claims.issuer, ISSUER)
        self.assertEqual(completion.claims.subject, "subject-123")
        self.assertEqual(completion.claims.username, "remote-reader")
        self.assertEqual(completion.claims.display_name, "Remote Reader")
        self.assertEqual(completion.claims.email, "reader@example.test")
        self.assertFalse(hasattr(completion, "access_token"))

    async def test_callback_rejects_wrong_browser_before_token_exchange(self):
        token_calls = 0

        def handler(request):
            nonlocal token_calls
            if request.url.path.endswith("openid-configuration"):
                return httpx.Response(200, json=self._metadata())
            token_calls += 1
            return httpx.Response(500)

        service = self._service(handler)
        start = await service.begin(self.settings, purpose="login", next_path="/", expected_user_id=None)
        with self.assertRaises(OIDCError) as raised:
            await service.complete(
                self.settings,
                state=start.state,
                browser_token="wrong-browser-token",
                code="code",
            )
        self.assertEqual(raised.exception.code, "invalid_callback")
        self.assertEqual(token_calls, 0)

    async def test_provider_error_callback_is_bound_and_sanitized(self):
        service = self._service(lambda request: httpx.Response(200, json=self._metadata()))
        start = await service.begin(self.settings, purpose="login", next_path="/", expected_user_id=None)
        with self.assertRaises(OIDCError) as raised:
            await service.complete(
                self.settings,
                state=start.state,
                browser_token=start.browser_token,
                error="access_denied",
                error_description="client-secret=do-not-leak",
            )
        self.assertEqual(raised.exception.code, "provider_denied")
        self.assertNotIn("do-not-leak", str(raised.exception))

    async def test_unknown_kid_refreshes_jwks_once(self):
        from authlib.jose import JsonWebKey, jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        fresh_jwk = JsonWebKey.import_key(public_pem, {"kid": "rotated", "use": "sig"}).as_dict()
        starts = []
        jwks_calls = 0

        def handler(request):
            nonlocal jwks_calls
            if request.url.path.endswith("openid-configuration"):
                return httpx.Response(200, json=self._metadata())
            if request.url.path == "/jwks.json":
                jwks_calls += 1
                return httpx.Response(200, json={"keys": [] if jwks_calls == 1 else [fresh_jwk]})
            claims = {
                "iss": ISSUER,
                "sub": "rotated-subject",
                "aud": ["epub-browser"],
                "nonce": starts[0].nonce,
                "iat": int(NOW),
                "exp": int(NOW + 300),
                "preferred_username": "rotated-user",
            }
            token = jwt.encode({"alg": "RS256", "kid": "rotated"}, claims, private_pem)
            return httpx.Response(200, json={"id_token": token.decode()})

        service = self._service(handler)
        starts.append(await service.begin(self.settings, purpose="login", next_path="/", expected_user_id=None))
        completion = await service.complete(
            self.settings,
            state=starts[0].state,
            browser_token=starts[0].browser_token,
            code="code",
        )
        self.assertEqual(completion.claims.subject, "rotated-subject")
        self.assertEqual(jwks_calls, 2)

    async def test_id_token_rejects_nonce_issuer_audience_azp_and_time_claims(self):
        from authlib.jose import JsonWebKey, jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        jwk = JsonWebKey.import_key(public_pem, {"kid": "claims-key", "use": "sig"}).as_dict()
        active_claims = {}

        def handler(request):
            if request.url.path.endswith("openid-configuration"):
                return httpx.Response(200, json=self._metadata())
            if request.url.path == "/jwks.json":
                return httpx.Response(200, json={"keys": [jwk]})
            token = jwt.encode({"alg": "RS256", "kid": "claims-key"}, active_claims, private_pem)
            return httpx.Response(200, json={"id_token": token.decode()})

        service = self._service(handler)
        invalid_updates = (
            {"nonce": "wrong"},
            {"iss": "https://attacker.example"},
            {"aud": "different-client"},
            {"aud": ["epub-browser", "other"], "azp": "other"},
            {"exp": int(NOW - 301)},
            {"iat": int(NOW + 301)},
        )
        for updates in invalid_updates:
            with self.subTest(updates=updates):
                start = await service.begin(self.settings, purpose="login", next_path="/", expected_user_id=None)
                active_claims.clear()
                active_claims.update(
                    {
                        "iss": ISSUER,
                        "sub": "subject",
                        "aud": "epub-browser",
                        "nonce": start.nonce,
                        "iat": int(NOW),
                        "exp": int(NOW + 300),
                        "preferred_username": "reader",
                    }
                )
                active_claims.update(updates)
                with self.assertRaises(OIDCError) as raised:
                    await service.complete(
                        self.settings,
                        state=start.state,
                        browser_token=start.browser_token,
                        code="code",
                    )
                self.assertEqual(raised.exception.code, "invalid_id_token")


if __name__ == "__main__":
    unittest.main()
