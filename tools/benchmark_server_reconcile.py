"""Measure Server reconcile validation work on a mixed EPUB/PDF library.

Run from a checkout root so the in-tree ``epub_browser`` package is imported::

    python tools/benchmark_server_reconcile.py
    python tools/benchmark_server_reconcile.py --books 8 --pdf-pages 2000 --json

The script converts a fresh batch, adds one book, then rescans without changes.
For every pass it reports wall time, time to the first readable book, the number
of cache validation calls, and the number of PDF bytes hashed by validation.
"""

import argparse
import json
import tempfile
import time
import zipfile
from pathlib import Path

from pypdf import PdfWriter

import epub_browser.server_library as server_library
from epub_browser.auth import BootstrapCredentials
from epub_browser.migration import MigrationManager
from epub_browser.server_library import ServerLibraryManager
from epub_browser.state import StateStore


def write_epub(path: Path, title: str, text: str) -> None:
    identifier = f"urn:benchmark:{path.stem}"
    container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    package = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{identifier}</dc:identifier>
    <dc:title>{title}</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
    chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title></head>
<body><h1>{title}</h1><p>{text}</p></body></html>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr("OEBPS/chapter.xhtml", chapter)


def write_pdf(path: Path, title: str, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=320, height=480)
    writer.add_metadata({"/Title": title, "/Author": "PDF Author"})
    with path.open("wb") as output:
        writer.write(output)


class ValidationProbe:
    """Count cache validations and the PDF bytes hashed by them."""

    def __init__(self, manager: ServerLibraryManager):
        self.manager = manager
        self.validation_calls = 0
        self.bytes_hashed = 0
        self._counting = False
        self._cache_valid = manager._cache_valid
        self._source_sha256 = server_library.source_sha256

    def __enter__(self):
        probe = self

        def cache_valid(record):
            probe.validation_calls += 1
            probe._counting = True
            try:
                return probe._cache_valid(record)
            finally:
                probe._counting = False

        def source_sha256(path):
            if probe._counting:
                try:
                    probe.bytes_hashed += Path(path).stat().st_size
                except OSError:
                    pass
            return probe._source_sha256(path)

        self.manager._cache_valid = cache_valid
        server_library.source_sha256 = source_sha256
        return self

    def __exit__(self, *_exc):
        del self.manager._cache_valid
        server_library.source_sha256 = self._source_sha256
        return False


def run_pass(manager: ServerLibraryManager, label: str) -> dict:
    started = time.perf_counter()
    first_readable = []

    def publish(failures):
        active_records, visible_changed = original_publish(failures)
        if not first_readable and active_records:
            first_readable.append(time.perf_counter() - started)
        return active_records, visible_changed

    original_publish = manager._publish_current_state
    manager._publish_current_state = publish
    try:
        with ValidationProbe(manager) as probe:
            summary = manager.reconcile()
    finally:
        del manager._publish_current_state

    return {
        "pass": label,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "first_readable_seconds": (
            round(first_readable[0], 3) if first_readable else None
        ),
        "validation_calls": probe.validation_calls,
        "bytes_hashed": probe.bytes_hashed,
        "converted": summary.converted,
        "reused": summary.reused,
        "failed": summary.failed,
        "active_books": len(summary.active_books),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", type=int, default=6, help="EPUB and PDF count each")
    parser.add_argument("--pdf-pages", type=int, default=500)
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="eb-reconcile-bench-") as temporary:
        root = Path(temporary)
        server_dir = root / "server"
        source_dir = root / "sources"
        source_dir.mkdir()
        for index in range(options.books):
            write_epub(source_dir / f"book-{index}.epub", f"Book {index}", "Body")
            write_pdf(
                source_dir / f"document-{index}.pdf",
                f"PDF {index}",
                options.pdf_pages,
            )
        migration = MigrationManager(
            server_dir,
            None,
            bootstrap=BootstrapCredentials("admin", "secret"),
        )
        state_store = StateStore(migration.prepare_data().database_path)
        manager = ServerLibraryManager(
            server_dir=server_dir,
            sources=(source_dir,),
            state_store=state_store,
            migration_manager=migration,
            max_workers=4,
        )
        results = [run_pass(manager, "fresh batch")]
        write_epub(source_dir / "added.epub", "Added", "Body")
        results.append(run_pass(manager, "one-book addition"))
        results.append(run_pass(manager, "unchanged rescan"))
        manager.shutdown()

    if options.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            print(
                f"{result['pass']:<18} wall={result['wall_seconds']:>7.3f}s "
                f"first_readable={result['first_readable_seconds']!s:>6}s "
                f"validation_calls={result['validation_calls']:>4} "
                f"bytes_hashed={result['bytes_hashed']:>10} "
                f"converted={result['converted']} reused={result['reused']} "
                f"failed={result['failed']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
