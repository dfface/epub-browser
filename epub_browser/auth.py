"""Authentication configuration and cryptographic primitives for Server mode."""

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

SESSION_COOKIE = "epub_browser_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
CSRF_HEADER_NAME = "X-CSRF-Token"


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
