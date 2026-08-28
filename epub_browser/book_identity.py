from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .epub_identity import (
    ensure_embedded_book_id,
    read_embedded_book_id,
    validate_book_id,
)
from .identity import new_server_book_id, source_sha256
from .sidecar_identity import (
    SidecarIdentity,
    adopt_sidecar,
    read_exact_sidecar,
    read_sidecar_file,
    validate_source_fingerprint,
    write_sidecar,
)
from .source_format import EPUB_FORMAT, PDF_FORMAT, source_format


BOOK_ID_STORAGE_SIDECAR = "sidecar"
BOOK_ID_STORAGE_EMBEDDED = "embedded"
BOOK_ID_STORAGE_CHOICES = (
    BOOK_ID_STORAGE_SIDECAR,
    BOOK_ID_STORAGE_EMBEDDED,
)


def validate_book_id_storage(value: str) -> str:
    if value not in BOOK_ID_STORAGE_CHOICES:
        choices = ", ".join(BOOK_ID_STORAGE_CHOICES)
        raise ValueError(f"Book ID storage must be one of: {choices}")
    return value


class BookIdentityError(RuntimeError):
    pass


class BookIdentityConflict(BookIdentityError):
    pass


@dataclass(frozen=True)
class KnownSourceFingerprint:
    value: str
    source_size: int
    source_mtime_ns: int


@dataclass(frozen=True)
class ExternalBookIdentity:
    origin: str
    book_id: str
    current_path: bool


@dataclass(frozen=True)
class BookIdentityInspection:
    source: Path
    source_fingerprint: str
    source_size: int
    source_mtime_ns: int
    source_snapshot: tuple[int, int, int, int]
    embedded_book_id: Optional[str]
    exact_sidecar: Optional[SidecarIdentity]
    matching_orphans: tuple[SidecarIdentity, ...]

    @property
    def has_current_carrier(self) -> bool:
        return self.exact_sidecar is not None or self.embedded_book_id is not None


@dataclass(frozen=True)
class ResolvedBookIdentity:
    book_id: str
    source_fingerprint: str
    source_size: int
    source_mtime_ns: int


def inspect_book_identity(
    source: Path,
    *,
    known_fingerprint: Optional[KnownSourceFingerprint] = None,
    orphan_sidecars: Sequence[Path] = (),
) -> BookIdentityInspection:
    source_path = Path(source)
    format_name = source_format(source_path)
    before = _source_snapshot(source_path)
    if (
        known_fingerprint is not None
        and known_fingerprint.source_size == before[2]
        and known_fingerprint.source_mtime_ns == before[3]
    ):
        try:
            fingerprint = validate_source_fingerprint(known_fingerprint.value)
        except RuntimeError as error:
            raise BookIdentityError(str(error)) from error
    else:
        fingerprint = source_sha256(source_path)

    exact_sidecar = read_exact_sidecar(source_path)
    embedded_book_id = (
        read_embedded_book_id(source_path)
        if format_name == EPUB_FORMAT
        else None
    )
    matching_orphans = []
    for orphan_path in orphan_sidecars:
        orphan = read_sidecar_file(orphan_path)
        if orphan.source_fingerprint == fingerprint:
            matching_orphans.append(orphan)
    matching_orphans.sort(key=lambda sidecar: str(sidecar.path))

    if _source_snapshot(source_path) != before:
        raise BookIdentityError(
            "source changed while its identity was inspected"
        )
    return BookIdentityInspection(
        source=source_path,
        source_fingerprint=fingerprint,
        source_size=before[2],
        source_mtime_ns=before[3],
        source_snapshot=before,
        embedded_book_id=embedded_book_id,
        exact_sidecar=exact_sidecar,
        matching_orphans=tuple(matching_orphans),
    )


def resolve_book_identity(
    inspection: BookIdentityInspection,
    storage: str,
    *,
    external_candidates: Sequence[ExternalBookIdentity] = (),
) -> ResolvedBookIdentity:
    storage = validate_book_id_storage(storage)
    current_candidates = []
    if inspection.exact_sidecar is not None:
        current_candidates.append(
            (
                f"sidecar {inspection.exact_sidecar.path}",
                inspection.exact_sidecar.book_id,
            )
        )
    if inspection.embedded_book_id is not None:
        current_candidates.append(
            ("embedded EPUB metadata", inspection.embedded_book_id)
        )

    move_candidates = []
    for candidate in external_candidates:
        try:
            candidate_id = validate_book_id(candidate.book_id)
        except (TypeError, ValueError) as error:
            raise BookIdentityError(
                f"Invalid book ID from {candidate.origin}: {error}"
            ) from error
        target = current_candidates if candidate.current_path else move_candidates
        target.append((candidate.origin, candidate_id))

    selected_orphan = None
    if current_candidates:
        candidates = current_candidates
    else:
        if len(inspection.matching_orphans) > 1:
            paths = ", ".join(
                str(sidecar.path) for sidecar in inspection.matching_orphans
            )
            raise BookIdentityError(
                f"Multiple sidecars match {inspection.source}: {paths}"
            )
        candidates = move_candidates
        if inspection.matching_orphans:
            selected_orphan = inspection.matching_orphans[0]
            candidates.append(
                (f"orphan sidecar {selected_orphan.path}", selected_orphan.book_id)
            )

    _require_candidate_agreement(candidates)
    book_id = candidates[0][1] if candidates else new_server_book_id()
    _assert_snapshot(inspection)

    if (
        storage == BOOK_ID_STORAGE_SIDECAR
        or source_format(inspection.source) == PDF_FORMAT
    ):
        if selected_orphan is not None:
            adopt_sidecar(selected_orphan, inspection.source)
        write_sidecar(
            inspection.source,
            book_id,
            inspection.source_fingerprint,
        )
        _assert_snapshot(inspection)
        return ResolvedBookIdentity(
            book_id=book_id,
            source_fingerprint=inspection.source_fingerprint,
            source_size=inspection.source_size,
            source_mtime_ns=inspection.source_mtime_ns,
        )

    if inspection.embedded_book_id is not None:
        _assert_snapshot(inspection)
        return ResolvedBookIdentity(
            book_id=book_id,
            source_fingerprint=inspection.source_fingerprint,
            source_size=inspection.source_size,
            source_mtime_ns=inspection.source_mtime_ns,
        )

    persisted_id = ensure_embedded_book_id(
        inspection.source,
        preferred_book_id=book_id,
    )
    if persisted_id != book_id:
        raise BookIdentityConflict(
            f"Embedded EPUB book ID {persisted_id!r} conflicts with {book_id!r}"
        )
    post_write = _source_snapshot(inspection.source)
    post_fingerprint = source_sha256(inspection.source)
    if _source_snapshot(inspection.source) != post_write:
        raise BookIdentityError(
            "source changed while its embedded identity was verified"
        )
    return ResolvedBookIdentity(
        book_id=book_id,
        source_fingerprint=post_fingerprint,
        source_size=post_write[2],
        source_mtime_ns=post_write[3],
    )


def _source_snapshot(path: Path) -> tuple[int, int, int, int]:
    source_stat = path.stat()
    return (
        source_stat.st_dev,
        source_stat.st_ino,
        source_stat.st_size,
        source_stat.st_mtime_ns,
    )


def _assert_snapshot(inspection: BookIdentityInspection) -> None:
    if _source_snapshot(inspection.source) != inspection.source_snapshot:
        raise BookIdentityError(
            "source changed before its identity could be persisted"
        )


def _require_candidate_agreement(candidates: Sequence[tuple[str, str]]) -> None:
    if len({book_id for _origin, book_id in candidates}) <= 1:
        return
    details = "; ".join(
        f"{origin}={book_id!r}" for origin, book_id in candidates
    )
    raise BookIdentityConflict(f"Conflicting book IDs: {details}")
