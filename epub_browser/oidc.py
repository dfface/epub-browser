"""Bounded, Provider-neutral OpenID Connect protocol support.

This module owns protocol details so routes and persistence never need to handle raw
Provider tokens. It intentionally implements only Authorization Code Flow with PKCE
S256 and signed ID Tokens.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import secrets
import time
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlencode, urlparse

import httpx
from authlib.jose import JsonWebToken
from authlib.jose.errors import JoseError

from .state import OIDCTransactionRecord, StateStore


_ALLOWED_SIGNING_ALGORITHMS = (
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
)
_TOKEN_BYTES = 32


class OIDCError(RuntimeError):
    """A sanitized OIDC failure with a stable application-facing code."""

    _MESSAGES = {
        "configuration_invalid": "The OIDC configuration is invalid.",
        "configuration_unsupported": "The OIDC Provider configuration is unsupported.",
        "discovery_failed": "The OIDC Provider metadata could not be loaded.",
        "discovery_invalid": "The OIDC Provider metadata is invalid.",
        "provider_unavailable": "The OIDC Provider is unavailable.",
        "provider_response_too_large": "The OIDC Provider response is too large.",
        "invalid_callback": "The OIDC callback is invalid or expired.",
        "provider_denied": "The OIDC Provider did not authorize this request.",
        "token_exchange_failed": "The OIDC authorization code could not be exchanged.",
        "invalid_id_token": "The OIDC identity token is invalid.",
    }

    def __init__(self, code: str):
        self.code = code
        super().__init__(self._MESSAGES.get(code, "OIDC authentication failed."))


@dataclass(frozen=True)
class OIDCConfiguration:
    enabled: bool
    provider_name: str
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...]
    username_claim: str
    config_revision: int

    @classmethod
    def from_settings(cls, settings: Any) -> "OIDCConfiguration":
        def value(name: str, default: Any = None) -> Any:
            if isinstance(settings, Mapping):
                return settings.get(name, default)
            return getattr(settings, name, default)

        issuer = value("issuer_url", value("issuer", ""))
        scopes = value("scopes", ())
        secret = value("client_secret", "") or ""
        try:
            configuration = cls(
                enabled=bool(value("enabled", False)),
                provider_name=str(value("provider_name", "")).strip(),
                issuer=str(issuer).strip().rstrip("/"),
                client_id=str(value("client_id", "")).strip(),
                client_secret=str(secret),
                redirect_uri=str(value("redirect_uri", "")).strip(),
                scopes=tuple(str(scope).strip() for scope in scopes if str(scope).strip()),
                username_claim=str(value("username_claim", "")).strip(),
                config_revision=int(value("config_revision", 0)),
            )
        except (TypeError, ValueError) as exc:
            raise OIDCError("configuration_invalid") from exc
        configuration.validate()
        return configuration

    def validate(self) -> None:
        if not (
            self.enabled
            and self.provider_name
            and self.client_id
            and self.redirect_uri
            and self.username_claim
            and self.config_revision > 0
            and "openid" in self.scopes
        ):
            raise OIDCError("configuration_invalid")
        if len(self.client_secret) > 8192 or any(len(scope) > 128 for scope in self.scopes):
            raise OIDCError("configuration_invalid")
        _require_secure_url(self.issuer, issuer=True)
        _require_secure_url(self.redirect_uri)
        redirect = urlparse(self.redirect_uri)
        if redirect.path != "/auth/oidc/callback" or redirect.query:
            raise OIDCError("configuration_invalid")


@dataclass(frozen=True)
class OIDCProviderMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: Optional[str]
    signing_algorithms: tuple[str, ...]
    token_auth_methods: tuple[str, ...]


@dataclass(frozen=True)
class OIDCStart:
    authorization_url: str
    state: str
    browser_token: str
    nonce: str
    pkce_verifier: str
    expires_at: float


@dataclass(frozen=True)
class OIDCClaims:
    issuer: str
    subject: str
    username: str
    display_name: str
    email: Optional[str]


@dataclass(frozen=True)
class OIDCCompletion:
    transaction: OIDCTransactionRecord
    claims: OIDCClaims


def _is_loopback(hostname: Optional[str]) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _require_secure_url(value: str, *, issuer: bool = False) -> None:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise OIDCError("configuration_invalid") from exc
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise OIDCError("configuration_invalid")
    if issuer and (parsed.query or value.endswith("/")):
        raise OIDCError("configuration_invalid")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and _is_loopback(parsed.hostname)
    ):
        raise OIDCError("configuration_invalid")
    if port is not None and not 1 <= port <= 65535:
        raise OIDCError("configuration_invalid")


def _token(length: int = _TOKEN_BYTES) -> str:
    return secrets.token_urlsafe(length)


def _b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _jwt_header(token: str) -> Mapping[str, Any]:
    try:
        encoded = token.split(".", 1)[0]
        encoded += "=" * (-len(encoded) % 4)
        value = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (
        ValueError,
        TypeError,
        UnicodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        raise OIDCError("invalid_id_token") from exc
    if not isinstance(value, dict):
        raise OIDCError("invalid_id_token")
    return value


class OIDCService:
    """Generic OIDC client with injectable transport, persistence, and clock."""

    def __init__(
        self,
        state: StateStore,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        clock: Callable[[], float] = time.time,
        transaction_ttl: float = 600,
        request_timeout: float = 10,
        max_response_bytes: int = 64 * 1024,
        clock_skew: float = 60,
    ):
        self._state = state
        self._client = http_client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(request_timeout),
        )
        self._owns_client = http_client is None
        self._clock = clock
        self._transaction_ttl = float(transaction_ttl)
        self._request_timeout = float(request_timeout)
        self._max_response_bytes = int(max_response_bytes)
        self._clock_skew = float(clock_skew)
        self._metadata_cache: dict[tuple[str, int], OIDCProviderMetadata] = {}
        self._jwks_cache: dict[tuple[str, int], Mapping[str, Any]] = {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def begin(
        self,
        settings: Any,
        *,
        purpose: str,
        next_path: str,
        expected_user_id: Optional[str],
    ) -> OIDCStart:
        configuration = OIDCConfiguration.from_settings(settings)
        metadata = await self.validate_configuration(configuration)
        state_token = _token()
        browser_token = _token()
        nonce = _token()
        pkce_verifier = _token(48)
        expires_at = self._clock() + self._transaction_ttl
        self._state.create_oidc_transaction(
            state_token=state_token,
            browser_token=browser_token,
            nonce=nonce,
            pkce_verifier=pkce_verifier,
            purpose=purpose,
            next_path=next_path,
            config_revision=configuration.config_revision,
            expires_at=expires_at,
            now=self._clock(),
            expected_user_id=expected_user_id,
        )
        query = urlencode(
            {
                "client_id": configuration.client_id,
                "redirect_uri": configuration.redirect_uri,
                "response_type": "code",
                "scope": " ".join(configuration.scopes),
                "state": state_token,
                "nonce": nonce,
                "code_challenge": _b64url_sha256(pkce_verifier),
                "code_challenge_method": "S256",
            }
        )
        separator = "&" if "?" in metadata.authorization_endpoint else "?"
        return OIDCStart(
            authorization_url=f"{metadata.authorization_endpoint}{separator}{query}",
            state=state_token,
            browser_token=browser_token,
            nonce=nonce,
            pkce_verifier=pkce_verifier,
            expires_at=expires_at,
        )

    async def complete(
        self,
        settings: Any,
        *,
        state: str,
        browser_token: str,
        code: Optional[str] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ) -> OIDCCompletion:
        del error_description
        configuration = OIDCConfiguration.from_settings(settings)
        transaction = self._state.claim_oidc_transaction(
            state,
            browser_token,
            configuration.config_revision,
            now=self._clock(),
        )
        if transaction is None:
            raise OIDCError("invalid_callback")
        if error:
            raise OIDCError("provider_denied")
        if not isinstance(code, str) or not code or len(code) > 8192:
            raise OIDCError("invalid_callback")
        metadata = await self.discover(configuration)
        token_response = await self._exchange_code(
            configuration, metadata, transaction, code
        )
        id_token = token_response.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OIDCError("token_exchange_failed")
        id_token_claims = await self._validated_id_token_claims(
            configuration, metadata, transaction, id_token
        )
        supplemental_claims = None
        username_claim = id_token_claims.get(configuration.username_claim)
        if not isinstance(username_claim, str) or not username_claim.strip():
            access_token = token_response.get("access_token")
            token_type = token_response.get("token_type")
            if (
                metadata.userinfo_endpoint is None
                or not isinstance(access_token, str)
                or not access_token
                or (token_type is not None and str(token_type).lower() != "bearer")
                or len(access_token) > 16384
                or any(ord(character) < 0x21 or ord(character) > 0x7E for character in access_token)
            ):
                raise OIDCError("invalid_id_token")
            supplemental_claims = await self._fetch_json(
                metadata.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                failure_code="invalid_id_token",
            )
        claims = self._normalized_claims(
            configuration,
            id_token_claims,
            supplemental_claims=supplemental_claims,
        )
        return OIDCCompletion(transaction=transaction, claims=claims)

    async def discover(self, configuration: OIDCConfiguration) -> OIDCProviderMetadata:
        cache_key = (configuration.issuer, configuration.config_revision)
        cached = self._metadata_cache.get(cache_key)
        if cached is not None:
            return cached
        url = f"{configuration.issuer}/.well-known/openid-configuration"
        payload = await self._fetch_json(url, failure_code="discovery_failed")
        try:
            issuer = payload["issuer"]
            authorization_endpoint = payload["authorization_endpoint"]
            token_endpoint = payload["token_endpoint"]
            jwks_uri = payload["jwks_uri"]
        except KeyError as exc:
            raise OIDCError("discovery_invalid") from exc
        if issuer != configuration.issuer:
            raise OIDCError("discovery_invalid")
        for endpoint in (authorization_endpoint, token_endpoint, jwks_uri):
            if not isinstance(endpoint, str):
                raise OIDCError("discovery_invalid")
            try:
                _require_secure_url(endpoint)
            except OIDCError as exc:
                raise OIDCError("discovery_invalid") from exc
        userinfo_endpoint = payload.get("userinfo_endpoint")
        if userinfo_endpoint is not None:
            if not isinstance(userinfo_endpoint, str):
                raise OIDCError("discovery_invalid")
            try:
                _require_secure_url(userinfo_endpoint)
            except OIDCError as exc:
                raise OIDCError("discovery_invalid") from exc
        challenge_methods = payload.get("code_challenge_methods_supported", ())
        if not isinstance(challenge_methods, list) or any(
            not isinstance(method, str) for method in challenge_methods
        ):
            raise OIDCError("discovery_invalid")
        if "S256" not in challenge_methods:
            raise OIDCError("configuration_unsupported")
        response_types = payload.get("response_types_supported")
        if response_types is not None:
            if not isinstance(response_types, list) or any(
                not isinstance(response_type, str) for response_type in response_types
            ):
                raise OIDCError("discovery_invalid")
            if "code" not in response_types:
                raise OIDCError("configuration_unsupported")
        advertised_algorithms = payload.get(
            "id_token_signing_alg_values_supported", _ALLOWED_SIGNING_ALGORITHMS
        )
        if not isinstance(advertised_algorithms, (list, tuple)) or any(
            not isinstance(algorithm, str) for algorithm in advertised_algorithms
        ):
            raise OIDCError("discovery_invalid")
        signing_algorithms = tuple(
            algorithm
            for algorithm in advertised_algorithms
            if algorithm in _ALLOWED_SIGNING_ALGORITHMS
        )
        if not signing_algorithms:
            raise OIDCError("configuration_unsupported")
        advertised_auth_methods = payload.get(
            "token_endpoint_auth_methods_supported", ["client_secret_basic"]
        )
        if not isinstance(advertised_auth_methods, list) or any(
            not isinstance(method, str) for method in advertised_auth_methods
        ):
            raise OIDCError("discovery_invalid")
        token_auth_methods = tuple(
            method
            for method in advertised_auth_methods
            if method in {"client_secret_basic", "client_secret_post", "none"}
        )
        if not token_auth_methods:
            raise OIDCError("configuration_unsupported")
        metadata = OIDCProviderMetadata(
            issuer=issuer,
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            jwks_uri=jwks_uri,
            userinfo_endpoint=userinfo_endpoint,
            signing_algorithms=signing_algorithms,
            token_auth_methods=token_auth_methods,
        )
        self._metadata_cache[cache_key] = metadata
        return metadata

    async def validate_configuration(self, settings: Any) -> OIDCProviderMetadata:
        """Validate local settings and live Provider metadata without persisting."""
        configuration = (
            settings
            if isinstance(settings, OIDCConfiguration)
            else OIDCConfiguration.from_settings(settings)
        )
        metadata = await self.discover(configuration)
        if configuration.client_secret:
            supported = {"client_secret_basic", "client_secret_post"}
            if not supported.intersection(metadata.token_auth_methods):
                raise OIDCError("configuration_unsupported")
        elif "none" not in metadata.token_auth_methods:
            raise OIDCError("configuration_unsupported")
        return metadata

    async def _exchange_code(
        self,
        configuration: OIDCConfiguration,
        metadata: OIDCProviderMetadata,
        transaction: OIDCTransactionRecord,
        code: str,
    ) -> Mapping[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": configuration.redirect_uri,
            "client_id": configuration.client_id,
            "code_verifier": transaction.pkce_verifier,
        }
        auth = None
        if configuration.client_secret:
            if "client_secret_basic" in metadata.token_auth_methods:
                auth = httpx.BasicAuth(configuration.client_id, configuration.client_secret)
            elif "client_secret_post" in metadata.token_auth_methods:
                data["client_secret"] = configuration.client_secret
            else:
                raise OIDCError("configuration_unsupported")
        elif "none" not in metadata.token_auth_methods:
            raise OIDCError("configuration_unsupported")
        return await self._fetch_json(
            metadata.token_endpoint,
            method="POST",
            data=data,
            auth=auth,
            failure_code="token_exchange_failed",
        )

    async def _jwks(
        self,
        configuration: OIDCConfiguration,
        metadata: OIDCProviderMetadata,
        *,
        refresh: bool = False,
    ) -> Mapping[str, Any]:
        cache_key = (configuration.issuer, configuration.config_revision)
        if not refresh and cache_key in self._jwks_cache:
            return self._jwks_cache[cache_key]
        payload = await self._fetch_json(
            metadata.jwks_uri, failure_code="provider_unavailable"
        )
        keys = payload.get("keys")
        if not isinstance(keys, list) or any(not isinstance(key, dict) for key in keys):
            raise OIDCError("invalid_id_token")
        self._jwks_cache[cache_key] = payload
        return payload

    async def _validated_id_token_claims(
        self,
        configuration: OIDCConfiguration,
        metadata: OIDCProviderMetadata,
        transaction: OIDCTransactionRecord,
        token: str,
    ) -> Mapping[str, Any]:
        header = _jwt_header(token)
        algorithm = header.get("alg")
        kid = header.get("kid")
        if algorithm not in metadata.signing_algorithms or not isinstance(kid, str) or not kid:
            raise OIDCError("invalid_id_token")
        jwks = await self._jwks(configuration, metadata)
        if not any(key.get("kid") == kid for key in jwks["keys"]):
            jwks = await self._jwks(configuration, metadata, refresh=True)
        if not any(key.get("kid") == kid for key in jwks["keys"]):
            raise OIDCError("invalid_id_token")
        try:
            claims_obj = JsonWebToken([algorithm]).decode(token, jwks)
            claims = dict(claims_obj)
        except (JoseError, ValueError, TypeError) as exc:
            raise OIDCError("invalid_id_token") from exc
        self._validate_claims(configuration, transaction, claims)
        return claims

    def _normalized_claims(
        self,
        configuration: OIDCConfiguration,
        id_token_claims: Mapping[str, Any],
        *,
        supplemental_claims: Optional[Mapping[str, Any]] = None,
    ) -> OIDCClaims:
        claims = dict(id_token_claims)
        if supplemental_claims is not None:
            if supplemental_claims.get("sub") != id_token_claims.get("sub"):
                raise OIDCError("invalid_id_token")
            for name in (configuration.username_claim, "name", "email"):
                if name in supplemental_claims:
                    claims[name] = supplemental_claims[name]
        username = claims.get(configuration.username_claim)
        if not isinstance(username, str) or not username.strip() or len(username) > 255:
            raise OIDCError("invalid_id_token")
        display_name = claims.get("name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = username
        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            email = None
        return OIDCClaims(
            issuer=configuration.issuer,
            subject=id_token_claims["sub"],
            username=username.strip(),
            display_name=display_name.strip()[:255],
            email=email.strip()[:320] if email else None,
        )

    def _validate_claims(
        self,
        configuration: OIDCConfiguration,
        transaction: OIDCTransactionRecord,
        claims: Mapping[str, Any],
    ) -> None:
        now = self._clock()
        subject = claims.get("sub")
        nonce = claims.get("nonce")
        audience = claims.get("aud")
        authorized_party = claims.get("azp")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if claims.get("iss") != configuration.issuer:
            raise OIDCError("invalid_id_token")
        if not isinstance(subject, str) or not subject or len(subject) > 1024:
            raise OIDCError("invalid_id_token")
        if not isinstance(nonce, str) or not secrets.compare_digest(nonce, transaction.nonce):
            raise OIDCError("invalid_id_token")
        if isinstance(audience, str):
            audiences: Sequence[str] = (audience,)
        elif isinstance(audience, list) and all(isinstance(item, str) for item in audience):
            audiences = audience
        else:
            raise OIDCError("invalid_id_token")
        if configuration.client_id not in audiences:
            raise OIDCError("invalid_id_token")
        if (len(audiences) > 1 or authorized_party is not None) and authorized_party != configuration.client_id:
            raise OIDCError("invalid_id_token")
        if not isinstance(issued_at, (int, float)) or isinstance(issued_at, bool):
            raise OIDCError("invalid_id_token")
        if not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool):
            raise OIDCError("invalid_id_token")
        if not math.isfinite(float(issued_at)) or not math.isfinite(float(expires_at)):
            raise OIDCError("invalid_id_token")
        if float(issued_at) > now + self._clock_skew or float(expires_at) <= now - self._clock_skew:
            raise OIDCError("invalid_id_token")

    async def _fetch_json(
        self,
        url: str,
        *,
        method: str = "GET",
        data: Optional[Mapping[str, str]] = None,
        auth: Optional[httpx.Auth] = None,
        headers: Optional[Mapping[str, str]] = None,
        failure_code: str,
    ) -> Mapping[str, Any]:
        try:
            async with self._client.stream(
                method,
                url,
                data=data,
                auth=auth,
                timeout=self._request_timeout,
                follow_redirects=False,
                headers={"Accept": "application/json", **dict(headers or {})},
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise OIDCError(failure_code)
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > self._max_response_bytes:
                            raise OIDCError("provider_response_too_large")
                    except ValueError:
                        raise OIDCError(failure_code)
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self._max_response_bytes:
                        raise OIDCError("provider_response_too_large")
                    chunks.append(chunk)
        except OIDCError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
            raise OIDCError("provider_unavailable") from exc
        try:
            payload = json.loads(b"".join(chunks))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OIDCError(failure_code) from exc
        if not isinstance(payload, dict):
            raise OIDCError(failure_code)
        return payload


__all__ = [
    "OIDCClaims",
    "OIDCCompletion",
    "OIDCConfiguration",
    "OIDCError",
    "OIDCProviderMetadata",
    "OIDCService",
    "OIDCStart",
]
