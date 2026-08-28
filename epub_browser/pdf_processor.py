from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional, Tuple

from pypdf import PdfReader
import pypdfium2 as pdfium
from pypdfium2 import raw as pdfium_raw


PDF_SIGNATURE_BYTES = 1024


class PDFProcessingError(Exception):
    """A stable, user-safe PDF inspection or rendering failure."""


@dataclass(frozen=True)
class PDFOutlineItem:
    title: str
    page_number: int
    level: int


@dataclass(frozen=True)
class PDFPageMetadata:
    page_number: int
    width: float
    height: float
    outline_labels: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PDFMetadata:
    title: Optional[str]
    authors: Tuple[str, ...]
    tags: Tuple[str, ...]
    language: Optional[str]
    pages: Tuple[PDFPageMetadata, ...]
    encrypted: bool
    has_extractable_text: bool
    cover: Optional[Path]


def _clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_values(value) -> Tuple[str, ...]:
    text = _clean_text(value)
    if text is None:
        return ()
    return tuple(part.strip() for part in re.split(r"[;,]", text) if part.strip())


def _page_metadata(page, page_index: int) -> PDFPageMetadata:
    width = float(page.cropbox.width)
    height = float(page.cropbox.height)
    if page.rotation % 360 in (90, 270):
        width, height = height, width
    return PDFPageMetadata(page_number=page_index + 1, width=width, height=height)


def _outline_items(reader: PdfReader) -> Tuple[PDFOutlineItem, ...]:
    items = []

    def visit(entries, level: int) -> None:
        for entry in entries:
            if isinstance(entry, list):
                visit(entry, level + 1)
                continue
            title = _clean_text(getattr(entry, "title", None))
            page_index = reader.get_destination_page_number(entry)
            if title is not None and page_index is not None and page_index >= 0:
                items.append(
                    PDFOutlineItem(
                        title=title,
                        page_number=page_index + 1,
                        level=level,
                    )
                )

    visit(reader.outline, 0)
    return tuple(items)


def _attach_outline_labels(
    pages: Tuple[PDFPageMetadata, ...],
    outline: Tuple[PDFOutlineItem, ...],
) -> Tuple[PDFPageMetadata, ...]:
    labels = [[] for _ in pages]
    for item in outline:
        if item.page_number <= len(pages):
            labels[item.page_number - 1].append(item.title)
    return tuple(
        PDFPageMetadata(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            outline_labels=tuple(labels[page_index]),
        )
        for page_index, page in enumerate(pages)
    )


def _has_extractable_text(reader: PdfReader) -> bool:
    for page in reader.pages:
        try:
            if (page.extract_text() or "").strip():
                return True
        except Exception:
            continue
    return False


def _validate_pdf_signature(source: Path) -> None:
    try:
        with source.open("rb") as stream:
            signature_window = stream.read(PDF_SIGNATURE_BYTES)
    except OSError:
        raise PDFProcessingError("Unable to read PDF") from None
    if b"%PDF-" not in signature_window:
        raise PDFProcessingError("PDF signature is missing")


def _inspect_pdf_contents(source: Path) -> PDFMetadata:
    reader = PdfReader(source, strict=False)
    if reader.is_encrypted:
        return PDFMetadata(
            title=None,
            authors=(),
            tags=(),
            language=None,
            pages=(),
            encrypted=True,
            has_extractable_text=False,
            cover=None,
        )
    document_info = reader.metadata or {}
    pages = tuple(
        _page_metadata(page, page_index)
        for page_index, page in enumerate(reader.pages)
    )
    pages = _attach_outline_labels(pages, _outline_items(reader))
    return PDFMetadata(
        title=_clean_text(document_info.get("/Title")),
        authors=_split_values(document_info.get("/Author")),
        tags=_split_values(document_info.get("/Keywords")),
        language=_clean_text(
            document_info.get("/Lang") or reader.root_object.get("/Lang")
        ),
        pages=pages,
        encrypted=reader.is_encrypted,
        has_extractable_text=_has_extractable_text(reader),
        cover=None,
    )


def inspect_pdf(source: Path) -> PDFMetadata:
    source = Path(source)
    _validate_pdf_signature(source)

    try:
        return _inspect_pdf_contents(source)
    except Exception:
        raise PDFProcessingError("Unable to inspect PDF") from None


def render_pdf_cover(
    source: Path,
    destination: Path,
    max_width: int = 600,
    max_height: int = 900,
) -> Optional[Path]:
    source = Path(source)
    destination = Path(destination)
    if max_width <= 0 or max_height <= 0:
        raise PDFProcessingError("PDF cover bounds must be positive")
    _validate_pdf_signature(source)
    try:
        document = pdfium.PdfDocument(str(source))
    except pdfium.PdfiumError as error:
        if error.err_code == pdfium_raw.FPDF_ERR_PASSWORD:
            return None
        raise PDFProcessingError("Unable to render PDF cover") from None
    if len(document) == 0:
        document.close()
        return None
    page = document[0]
    bitmap = None
    image = None
    try:
        width, height = page.get_size()
        scale = min(max_width / width, max_height / height)
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        image.save(destination, format="PNG")
        return destination
    except Exception:
        raise PDFProcessingError("Unable to render PDF cover") from None
    finally:
        if image is not None:
            image.close()
        if bitmap is not None:
            bitmap.close()
        page.close()
        document.close()
