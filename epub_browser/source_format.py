from pathlib import Path


EPUB_FORMAT = "epub"
PDF_FORMAT = "pdf"


def source_format(path: Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".epub":
        return EPUB_FORMAT
    if suffix == ".pdf":
        return PDF_FORMAT
    raise ValueError(f"Unsupported book format: {suffix or '<none>'}")


def is_supported_source(path: Path) -> bool:
    return Path(path).suffix.lower() in {".epub", ".pdf"}
