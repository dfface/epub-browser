"""Authentication configuration and cryptographic primitives for Server mode."""

import hashlib
import hmac
import ipaddress
import secrets
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple

SESSION_COOKIE = "epub_browser_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
CSRF_HEADER_NAME = "X-CSRF-Token"
LOGIN_FAILURE_LIMIT = 5
LOGIN_THROTTLE_WINDOW_SECONDS = 5 * 60
LOGIN_THROTTLE_CAPACITY = 1024

# A valid Argon2id hash keeps the unknown-user path on the same password-
# verification primitive as a wrong password for an existing account.
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "R29uZXJBdGVkU2FsdDEyMw$"
    "XsPl1lDyqEA3tvNHaMCJJN4YBM4Zt/9p4cGHJps2BuM"
)


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    role: str


@dataclass(frozen=True)
class BootstrapCredentials:
    username: str
    password: str


@dataclass(frozen=True)
class ProxyIdentity:
    issuer: str
    subject: str
    display_name: Optional[str] = None


@dataclass(frozen=True)
class ServerAuthOptions:
    admin_username: Optional[str] = None
    admin_password_file: Optional[Path] = None
    trusted_proxy_cidrs: Tuple[str, ...] = ()
    proxy_subject_header: Optional[str] = None
    proxy_display_name_header: Optional[str] = None
    proxy_issuer: Optional[str] = None
    cookie_secure: Optional[bool] = None


@dataclass(frozen=True)
class AuthConfig:
    cookie_secure: bool
    session_ttl_seconds: int
    csrf_header_name: str
    trusted_proxy_networks: Tuple[ipaddress._BaseNetwork, ...]
    proxy_subject_header: Optional[str]
    proxy_display_name_header: Optional[str]
    proxy_issuer: Optional[str]

    @classmethod
    def from_values(
        cls,
        trusted_proxy_cidrs: Sequence[str],
        proxy_subject_header: Optional[str],
        proxy_issuer: Optional[str],
        proxy_display_name_header: Optional[str] = None,
        cookie_secure: bool = False,
    ) -> "AuthConfig":
        has_proxy_setting = bool(
            trusted_proxy_cidrs
            or proxy_subject_header
            or proxy_display_name_header
            or proxy_issuer
        )
        has_required_proxy_settings = bool(
            trusted_proxy_cidrs and proxy_subject_header and proxy_issuer
        )
        if has_proxy_setting and not has_required_proxy_settings:
            raise ValueError(
                "trusted proxy CIDRs, subject header, and issuer must be configured together"
            )

        try:
            networks = tuple(
                ipaddress.ip_network(cidr, strict=True)
                for cidr in trusted_proxy_cidrs
            )
        except ValueError as error:
            raise ValueError("trusted proxy CIDRs must be valid networks") from error

        return cls(
            cookie_secure=bool(cookie_secure),
            session_ttl_seconds=SESSION_TTL_SECONDS,
            csrf_header_name=CSRF_HEADER_NAME,
            trusted_proxy_networks=networks,
            proxy_subject_header=proxy_subject_header,
            proxy_display_name_header=proxy_display_name_header,
            proxy_issuer=proxy_issuer,
        )

    def is_trusted_proxy(self, client_host: str) -> bool:
        try:
            client_address = ipaddress.ip_address(client_host)
        except ValueError:
            return False
        return any(client_address in network for network in self.trusted_proxy_networks)


def hash_password(password: str) -> str:
    from argon2 import PasswordHasher
    from argon2.low_level import Type

    return PasswordHasher(type=Type.ID).hash(password)


def verify_password(encoded: str, password: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
    from argon2.low_level import Type

    try:
        return PasswordHasher(type=Type.ID).verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def session_cookie_options(config: AuthConfig) -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": config.cookie_secure,
        "path": "/",
    }


def token_digest(raw_token: str) -> str:
    """Return the one-way lookup value persisted for an opaque session token."""
    if not isinstance(raw_token, str):
        raise TypeError("Session token must be text")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _clock_seconds(value) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return float(value)


class AuthService:
    def __init__(
        self,
        store,
        config: AuthConfig,
        *,
        clock: Optional[Callable[[], float]] = None,
        throttle_limit: int = LOGIN_FAILURE_LIMIT,
        throttle_window_seconds: float = LOGIN_THROTTLE_WINDOW_SECONDS,
        throttle_capacity: int = LOGIN_THROTTLE_CAPACITY,
    ):
        if throttle_limit < 1:
            raise ValueError("Throttle limit must be positive")
        if throttle_window_seconds <= 0:
            raise ValueError("Throttle window must be positive")
        if throttle_capacity < 1:
            raise ValueError("Throttle capacity must be positive")
        self.store = store
        self.config = config
        self.clock = clock or time.time
        self.ttl = config.session_ttl_seconds
        self.throttle_limit = throttle_limit
        self.throttle_window_seconds = throttle_window_seconds
        self.throttle_capacity = throttle_capacity
        self._login_failures = OrderedDict()

    @property
    def tracked_login_keys(self) -> int:
        self._purge_login_failures(self._now())
        return len(self._login_failures)

    def _now(self) -> float:
        return _clock_seconds(self.clock())

    @staticmethod
    def _normalize_login_username(username: str) -> str:
        if not isinstance(username, str):
            return ""
        return username.strip().casefold()

    @staticmethod
    def _login_key(client_key: str, normalized_username: str) -> tuple:
        return (str(client_key), normalized_username)

    def _purge_login_failures(self, now: float) -> None:
        cutoff = now - self.throttle_window_seconds
        empty_keys = []
        for key, failures in self._login_failures.items():
            while failures and failures[0] <= cutoff:
                failures.popleft()
            if not failures:
                empty_keys.append(key)
        for key in empty_keys:
            del self._login_failures[key]

    def _record_login_failure(self, key: tuple, now: float) -> None:
        self._purge_login_failures(now)
        failures = self._login_failures.get(key)
        if failures is None:
            if len(self._login_failures) >= self.throttle_capacity:
                self._login_failures.popitem(last=False)
            failures = deque(maxlen=self.throttle_limit)
            self._login_failures[key] = failures
        else:
            self._login_failures.move_to_end(key)
        failures.append(now)

    def login_is_throttled(
        self,
        client_key: str,
        username: Optional[str] = None,
    ) -> bool:
        now = self._now()
        self._purge_login_failures(now)
        if username is not None:
            key = self._login_key(
                client_key,
                self._normalize_login_username(username),
            )
            return len(self._login_failures.get(key, ())) >= self.throttle_limit
        client = str(client_key)
        return any(
            key_client == client and len(failures) >= self.throttle_limit
            for (key_client, _), failures in self._login_failures.items()
        )

    def authenticate_password(
        self,
        username: str,
        password: str,
        client_key: str,
    ) -> Optional[Principal]:
        now = self._now()
        normalized = self._normalize_login_username(username)
        key = self._login_key(client_key, normalized)
        self._purge_login_failures(now)
        if len(self._login_failures.get(key, ())) >= self.throttle_limit:
            return None

        user = None
        if normalized:
            user = self.store.get_user_by_username(normalized)
        encoded = (
            user.password_hash
            if user is not None and user.enabled and user.password_hash
            else _DUMMY_PASSWORD_HASH
        )
        password_matches = verify_password(encoded, password)
        if (
            user is not None
            and user.enabled
            and user.password_hash
            and password_matches
        ):
            self._login_failures.pop(key, None)
            return user.principal

        self._record_login_failure(key, now)
        return None

    def create_session(self, principal: Principal) -> Tuple[str, str]:
        raw_token = secrets.token_urlsafe(32)
        now = self._now()
        self.store.create_session(
            token_digest(raw_token),
            principal.user_id,
            now + self.ttl,
            now=now,
        )
        return raw_token, self.issue_csrf_token(principal, raw_token)

    def principal_from_session(self, raw_token: Optional[str]) -> Optional[Principal]:
        if not raw_token:
            return None
        return self.store.principal_from_session(
            raw_token,
            now=self._now(),
            ttl_seconds=self.ttl,
        )

    def revoke_session(self, raw_token: Optional[str]) -> bool:
        if not raw_token:
            return False
        return self.store.revoke_session_by_token(raw_token, revoked_at=self._now())

    def issue_csrf_token(self, principal: Principal, raw_session: str) -> str:
        message = "csrf:{}".format(principal.user_id).encode("utf-8")
        return hmac.new(
            raw_session.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    def verify_csrf_token(
        self,
        principal: Principal,
        raw_session: Optional[str],
        supplied_token: Optional[str],
    ) -> bool:
        if not raw_session or not supplied_token:
            return False
        expected = self.issue_csrf_token(principal, raw_session)
        try:
            return hmac.compare_digest(expected, supplied_token)
        except TypeError:
            return False

    def verify_csrf(self, request, principal: Principal) -> bool:
        raw_session = request.cookies.get(SESSION_COOKIE)
        supplied_token = request.headers.get(self.config.csrf_header_name)
        return self.verify_csrf_token(principal, raw_session, supplied_token)

    @staticmethod
    def _header(headers: Mapping, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        value = headers.get(name)
        if value is not None:
            return value
        wanted = name.casefold()
        for header_name, header_value in headers.items():
            if str(header_name).casefold() == wanted:
                return header_value
        return None

    def authenticate_proxy(
        self,
        client_host: str,
        headers: Mapping,
    ) -> Optional[ProxyIdentity]:
        if not self.config.is_trusted_proxy(client_host):
            return None
        subject = self._header(headers, self.config.proxy_subject_header)
        if not isinstance(subject, str) or not subject.strip():
            return None
        display_name = self._header(
            headers,
            self.config.proxy_display_name_header,
        )
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = None
        return ProxyIdentity(
            self.config.proxy_issuer,
            subject.strip(),
            display_name.strip() if display_name is not None else None,
        )
