"""Personal access token primitives for the Server external API."""

import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import FrozenSet, Optional, Sequence, Tuple

from .auth import Principal


PAT_SCOPES = frozenset({
    "library:read",
    "bookshelf:read",
    "bookshelf:write",
    "progress:read",
    "progress:write",
    "annotations:read",
    "annotations:write",
    "reviews:read",
    "reviews:write",
    "admin:data:read",
})

PAT_WRITE_REQUIRES = {
    "bookshelf:write": "bookshelf:read",
    "progress:write": "progress:read",
    "annotations:write": "annotations:read",
    "reviews:write": "reviews:read",
}

_PAT_PATTERN = re.compile(r"^epub_pat_([A-Za-z0-9_-]{16,64})_([A-Za-z0-9_-]{32,128})$")


@dataclass(frozen=True)
class PersonalAccessToken:
    token_id: str
    public_id: str
    user_id: str
    name: str
    scopes: Tuple[str, ...]
    expires_at: Optional[float]
    last_used_at: Optional[float]
    revoked_at: Optional[float]
    created_at: float


@dataclass(frozen=True)
class IssuedPersonalAccessToken:
    token: PersonalAccessToken
    raw_token: str


@dataclass(frozen=True)
class AuthenticatedPAT:
    principal: Principal
    token: PersonalAccessToken
    effective_scopes: FrozenSet[str]


def normalize_scopes(scopes: Sequence[str]) -> Tuple[str, ...]:
    if isinstance(scopes, (str, bytes)):
        raise ValueError("PAT scopes must be a sequence")
    normalized = set(scopes)
    if not normalized:
        raise ValueError("At least one PAT scope is required")
    unsupported = normalized - PAT_SCOPES
    if unsupported:
        raise ValueError("Unsupported PAT scope")
    for write_scope, read_scope in PAT_WRITE_REQUIRES.items():
        if write_scope in normalized and read_scope not in normalized:
            raise ValueError("A write scope requires its matching read scope")
    return tuple(sorted(normalized))


def pat_digest(raw_token: str) -> str:
    if not isinstance(raw_token, str):
        raise TypeError("PAT must be text")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_pat() -> Tuple[str, str, str]:
    public_id = secrets.token_urlsafe(16)
    secret = secrets.token_urlsafe(32)
    raw_token = "epub_pat_{}_{}".format(public_id, secret)
    return raw_token, public_id, pat_digest(raw_token)


def pat_public_id(raw_token: str) -> Optional[str]:
    if not isinstance(raw_token, str):
        return None
    match = _PAT_PATTERN.fullmatch(raw_token)
    return match.group(1) if match is not None else None
