from pathlib import Path


EPUB_FORMAT = "epub"
PDF_FORMAT = "pdf"
PDF_CONVERSION_UNAVAILABLE = "PDF conversion is not available yet"
PDF_EMBEDDED_STORAGE_NOTICE = (
    "Embedded book ID storage is EPUB-only; "
    "PDF identities use adjacent sidecars."
)


def source_format(path: Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".epub":
        return EPUB_FORMAT
    if suffix == ".pdf":
        return PDF_FORMAT
    raise ValueError(f"Unsupported book format: {suffix or '<none>'}")


def is_supported_source(path: Path) -> bool:
    return Path(path).suffix.lower() in {".epub", ".pdf"}
