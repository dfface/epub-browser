import base64
import hashlib
import json
import unicodedata
import uuid
from pathlib import Path
from typing import Iterable, Tuple

from .models import BookMetadata


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def new_server_book_id() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


def derive_ssg_book_id(
    metadata: BookMetadata,
    spine_toc: Iterable[Tuple[str, str, int]],
) -> str:
    normalized_structure = [
        {
            "title": _normalize_text(title),
            "src": _normalize_text(src).replace("\\", "/"),
            "level": int(level),
        }
        for title, src, level in spine_toc
    ]
    identifier = _normalize_text(metadata.epub_identifier or "")
    if identifier:
        identity = {"epub_identifier": identifier}
    else:
        identity = {
            "title": _normalize_text(metadata.title),
            "authors": [_normalize_text(author) for author in metadata.authors],
        }
    payload = {
        "identity": identity,
        "structure": normalized_structure,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:22]


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
