import json
import tempfile
import unittest
import subprocess
import sys
import re
import zipfile
from pathlib import Path

from epub_browser.asset_publisher import AssetPublisher
from epub_browser.library import EPUBLibrary
from epub_browser.models import ConvertedBook
from epub_browser.processor import EPUBProcessor
from epub_browser.site import publish_library_shell
from epub_browser.urls import SiteURLs


class GeneratedReaderSurfaceTests(unittest.TestCase):
    def test_server_includes_real_account_controls_but_ssg_includes_none(self):
        server_html = self._server_html()
        ssg_html = self._library_html()

        for control_id in (
            "accountMenu",
            "accountPanel",
            "accountPasswordForm",
            "sessionList",
            "adminMenu",
            "adminPanel",
            "adminClose",
            "adminUserForm",
            "adminBookSearch",
            "adminBookVisibilityFilter",
            "adminBookTagFilter",
            "adminBookSort",
            "adminBookPageSize",
            "adminBookRefresh",
            "adminBookList",
            "adminBookLegacyList",
            "adminBookPagination",
            "adminBookLive",
        ):
            self.assertRegex(server_html, rf'\bid=(?:["\'])?{control_id}(?:["\' >])')
            self.assertNotIn(control_id, ssg_html)

        self.assertRegex(
            server_html,
            r'/assets/immutable/auth\.[0-9a-f]{12}\.js',
        )
        self.assertNotIn('auth.js', ssg_html)
        self.assertNotRegex(ssg_html, r'/assets/immutable/auth\.[0-9a-f]{12}\.js')
        self.assertLess(server_html.index('/immutable/auth.'), server_html.rindex('/immutable/library.'))
        self.assertNotIn('id=loginForm', server_html)
        self.assertRegex(
            server_html,
            r'/assets/immutable/account\.[0-9a-f]{12}\.css',
        )
        self.assertRegex(server_html, r'class=(?:["\'])?account-layout(?:["\' >])')
        self.assertRegex(server_html, r'class=(?:["\'])?account-grid(?:["\' >])')

    def test_server_admin_books_surface_is_semantic_and_localized(self):
        server_html = self._server_html()
        ssg_html = self._library_html()

        self.assertRegex(
            server_html,
            r'<section\b[^>]*aria-labelledby=(?:["\'])?adminSectionBooksTab',
        )
        for key in ('searchLabel', 'visibilityFilter', 'tagFilter', 'sortLabel', 'pageSize', 'refresh'):
            self.assertIn('data-i18n=admin.books.' + key, server_html)
        self.assertIn('data-i18n-placeholder=admin.books.searchPlaceholder', server_html)
        self.assertRegex(server_html, r'<input\b(?=[^>]*id=(?:["\'])?adminBookSearch)(?=[^>]*type=(?:["\'])?search)')
        self.assertRegex(server_html, r'<div\b(?=[^>]*id=(?:["\'])?adminBookTableSurface)(?=[^>]*hidden)')
        self.assertRegex(server_html, r'<div\b(?=[^>]*id=(?:["\'])?adminBookTableSurface)(?=[^>]*class=(?:["\'])?admin-books-workspace)')
        self.assertRegex(server_html, r'<div\b(?=[^>]*class=(?:["\'])?account-form admin-books-controls)(?=[^>]*role=(?:["\'])?search)(?=[^>]*aria-labelledby=(?:["\'])?adminBooksTitle)')
        self.assertRegex(server_html, r'<table\b[^>]*class=(?:["\'])?account-admin-table')
        self.assertRegex(server_html, r'<tbody\b[^>]*id=(?:["\'])?adminBookList')
        self.assertRegex(server_html, r'<ul\b[^>]*id=(?:["\'])?adminBookLegacyList')
        self.assertRegex(server_html, r'<nav\b[^>]*id=(?:["\'])?adminBookPagination')
        self.assertRegex(server_html, r'<p\b(?=[^>]*id=(?:["\'])?adminBookLive)(?=[^>]*aria-live=(?:["\'])?polite)')
        for key in ('book', 'access', 'profile', 'results', 'updated', 'action'):
            self.assertIn('data-i18n=admin.books.header.' + key, server_html)
        for value in ('10', '20', '50', '100'):
            self.assertRegex(server_html, r'<option\b[^>]*value=(?:["\'])?' + value + r'(?:["\' >])')
        self.assertRegex(server_html, r'<option\b(?=[^>]*value=(?:["\'])?20)(?=[^>]*selected)')
        for control_id in (
            'adminBookSearch', 'adminBookVisibilityFilter', 'adminBookTagFilter', 'adminBookSort',
            'adminBookPageSize', 'adminBookRefresh', 'adminBookList',
            'adminBookLegacyList', 'adminBookPagination', 'adminBookLive',
        ):
            self.assertNotIn(control_id, ssg_html)

    def test_server_admin_ai_jobs_surface_is_semantic_and_localized(self):
        server_html = self._server_html()
        ssg_html = self._library_html()

        self.assertRegex(server_html, r'<section\b[^>]*aria-labelledby=(?:["\'])?adminAiJobsTitle')
        self.assertIn('data-i18n=admin.ai.jobs.statusFilter', server_html)
        self.assertIn('data-i18n=admin.ai.jobs.pageSize', server_html)
        self.assertIn('data-i18n=admin.ai.jobs.refresh', server_html)
        self.assertRegex(server_html, r'<table\b[^>]*class=(?:["\'])?account-admin-table')
        self.assertIn('<thead>', server_html)
        self.assertRegex(server_html, r'<tbody\b[^>]*id=(?:["\'])?adminAiJobsBody')
        self.assertRegex(server_html, r'<nav\b[^>]*id=(?:["\'])?adminAiJobsPagination')
        self.assertRegex(
            server_html,
            r'<p\b(?=[^>]*id=(?:["\'])?adminAiJobsLive)(?=[^>]*aria-live=(?:["\'])?polite)',
        )
        for status in ('all', 'queued', 'running', 'complete', 'failed', 'interrupted'):
            self.assertIn('data-i18n=admin.ai.jobs.status.' + status, server_html)
        for page_size in ('10', '20', '50', '100'):
            self.assertRegex(
                server_html,
                r'<option\b[^>]*value=(?:["\'])?' + page_size + r'(?:["\' >])',
            )
        for control_id in (
            'adminAiJobsStatus', 'adminAiJobsPageSize', 'adminAiJobsRefresh',
            'adminAiJobsBody', 'adminAiJobsPagination', 'adminAiJobsLive',
        ):
            self.assertNotIn(control_id, ssg_html)

    def test_admin_ai_job_table_uses_a_bounded_scroller_for_its_sticky_header(self):
        stylesheet = Path('epub_browser/assets/account.css').read_text(
            encoding='utf-8'
        )
        scroll_start = stylesheet.index('.account-table-scroll {')
        scroll_rule = stylesheet[scroll_start:stylesheet.index('}', scroll_start)]
        header_start = stylesheet.index('.account-admin-table thead th {')
        header_rule = stylesheet[header_start:stylesheet.index('}', header_start)]

        self.assertIn('overflow: auto;', scroll_rule)
        self.assertIn('max-height:', scroll_rule)
        self.assertIn('position: sticky;', header_rule)
        self.assertIn('top: 0;', header_rule)
        self.assertRegex(
            stylesheet,
            r'@media \(max-width: 720px\)[\s\S]*?'
            r'\.account-admin-table\s*\{[^}]*min-width:\s*56rem;',
        )

    def test_account_surfaces_use_the_library_form_and_card_system(self):
        stylesheet = Path('epub_browser/assets/account.css').read_text(
            encoding='utf-8'
        )

        for selector in (
            '.auth-card',
            '.auth-primary-button',
            '.account-layout',
            '.account-grid',
            '.account-card',
            '.account-form',
            '.account-list-item',
            '.account-user-item',
            '.account-user-badge',
            '.account-user-details',
            '.account-danger-action',
        ):
            self.assertIn(selector, stylesheet)
        self.assertIn('@media (max-width: 560px)', stylesheet)
        self.assertIn('var(--button-bg, #4361ee)', stylesheet)

    def test_account_modal_keeps_dynamic_lists_scrollable_on_mobile(self):
        html = self._server_html()
        stylesheet = Path('epub_browser/assets/bookshelf.css').read_text(
            encoding='utf-8'
        )
        self.assertIn('.account-modal-body {', stylesheet)
        body_rule = stylesheet[
            stylesheet.index('.account-modal-body {'):
            stylesheet.index('}', stylesheet.index('.account-modal-body {'))
        ]

        self.assertRegex(html, r'class=(?:["\'])?account-modal-body(?:["\' >])')
        self.assertIn('display: flex;', body_rule)
        self.assertIn('flex-direction: column;', body_rule)
        self.assertIn('min-height: 0;', body_rule)
        self.assertIn('overflow-y: auto;', body_rule)

    def test_processor_convert_preserves_caller_supplied_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.epub"
            self._write_minimal_epub(source)

            processor = EPUBProcessor(
                str(source),
                str(root / "staging"),
                book_id="stable_id",
            )
            converted = processor.convert()

            self.assertIsInstance(converted, ConvertedBook)
            self.assertEqual(converted.book_id, "stable_id")
            self.assertEqual(converted.output_dir, root / "staging" / "epub_stable_id" / "web")
            self.assertEqual(processor.book_hash, "stable_id")
            self.assertEqual(converted.metadata.epub_identifier, "urn:test:stable")
            self.assertEqual(converted.chapter_count, 1)

    def test_server_processor_preserves_root_relative_navigation_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "root-relative-link.epub"
            navigation_path = (
                "/leetcode/ChapterFour/0001~0099/0001.Two-Sum/"
            )
            self._write_minimal_epub(
                source,
                chapter_body=f'<a href="{navigation_path}">Two Sum</a>',
            )
            processor = EPUBProcessor(
                str(source),
                str(root / "staging"),
                book_id="stable_id",
                deployment_mode="server",
            )

            converted = processor.convert()
            chapter = json.loads(
                Path(
                    converted.output_dir,
                    "content",
                    "chapter_0.json",
                ).read_text(encoding="utf-8")
            )

            self.assertIn(f'href="{navigation_path}"', chapter["content"])

    def test_processor_skips_non_linear_spine_items_from_public_chapters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "non-linear-spine.epub"
            container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
            package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Indexed</dc:title></metadata>
  <manifest>
    <item id="first" href="first.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="leaders" href="leaders-one.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="cover" linear="no"/><itemref idref="first"/><itemref idref="leaders"/></spine>
</package>
"""
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("META-INF/container.xml", container)
                archive.writestr("OEBPS/content.opf", package)
                archive.writestr("OEBPS/first.xhtml", "<html><body><p>First</p></body></html>")
                archive.writestr(
                    "OEBPS/cover.xhtml",
                    "<html><body><p>Cover</p></body></html>",
                )
                archive.writestr("OEBPS/leaders-one.xhtml", "<html><body><p>Leader article</p></body></html>")

            processor = EPUBProcessor(str(source), str(root / "staging"))
            processor.extract_epub()
            self.assertTrue(processor.parse_opf("OEBPS/content.opf"))

            self.assertEqual(
                [chapter["path"] for chapter in processor.chapters],
                ["OEBPS/first.xhtml", "OEBPS/leaders-one.xhtml"],
            )
            self.assertEqual(
                [chapter["title"] for chapter in processor.chapters],
                ["Chapter 0", "Chapter 1"],
            )

    def test_ncx_section_that_repeats_first_article_target_does_not_consume_chapter_index(self):
        """OPF spine, not NCX grouping nodes, owns chapter_N indexes."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "grouped-toc.epub"
            container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
            package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Grouped</dc:title></metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="article" href="article.xhtml" media-type="application/xhtml+xml"/>
    <item id="next" href="next.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx"><itemref idref="article"/><itemref idref="next"/></spine>
</package>
"""
            ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="section"><navLabel><text>Leaders</text></navLabel><content src="article.xhtml"/>
      <navPoint id="article"><navLabel><text>First article</text></navLabel><content src="article.xhtml"/></navPoint>
    </navPoint>
    <navPoint id="next"><navLabel><text>Next article</text></navLabel><content src="next.xhtml"/></navPoint>
  </navMap>
</ncx>
"""
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("META-INF/container.xml", container)
                archive.writestr("OEBPS/content.opf", package)
                archive.writestr("OEBPS/toc.ncx", ncx)
                archive.writestr("OEBPS/article.xhtml", "<html><body>Article</body></html>")
                archive.writestr("OEBPS/next.xhtml", "<html><body>Next</body></html>")

            processor = EPUBProcessor(str(source), str(root / "staging"))
            processor.extract_epub()
            self.assertTrue(processor.parse_opf("OEBPS/content.opf"))

            self.assertEqual(
                [(chapter["title"], chapter["path"]) for chapter in processor.chapters],
                [
                    ("First article", "OEBPS/article.xhtml"),
                    ("Next article", "OEBPS/next.xhtml"),
                ],
            )
            self.assertEqual(
                processor._build_toc_data(),
                [
                    {"title": "Leaders", "level": 0, "kind": "section"},
                    {
                        "title": "First article", "level": 1,
                        "kind": "chapter", "chapter_index": 0,
                        "chapter_file": "chapter_0.html",
                    },
                    {
                        "title": "Next article", "level": 0,
                        "kind": "chapter", "chapter_index": 1,
                        "chapter_file": "chapter_1.html",
                    },
                ],
            )

    def test_real_section_index_page_keeps_its_own_opf_chapter_index(self):
        """A spine page must not vanish because NCX repeats its first child."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "section-index.epub"
            container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
            package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Section index</dc:title></metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="section" href="leaders.xhtml" media-type="application/xhtml+xml"/>
    <item id="article" href="article.xhtml" media-type="application/xhtml+xml"/>
    <item id="next" href="next.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx"><itemref idref="section"/><itemref idref="article"/><itemref idref="next"/></spine>
</package>
"""
            ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="section"><navLabel><text>Leaders</text></navLabel><content src="article.xhtml"/>
      <navPoint id="article"><navLabel><text>First article</text></navLabel><content src="article.xhtml"/></navPoint>
    </navPoint>
    <navPoint id="next"><navLabel><text>Next article</text></navLabel><content src="next.xhtml"/></navPoint>
  </navMap>
</ncx>
"""
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("META-INF/container.xml", container)
                archive.writestr("OEBPS/content.opf", package)
                archive.writestr("OEBPS/toc.ncx", ncx)
                archive.writestr(
                    "OEBPS/leaders.xhtml",
                    '<html><body><h2 class="section_index_title">Leaders</h2></body></html>',
                )
                archive.writestr("OEBPS/article.xhtml", "<html><body>Article</body></html>")
                archive.writestr("OEBPS/next.xhtml", "<html><body>Next</body></html>")

            processor = EPUBProcessor(str(source), str(root / "staging"))
            processor.extract_epub()
            self.assertTrue(processor.parse_opf("OEBPS/content.opf"))

            self.assertEqual(
                [chapter["title"] for chapter in processor.chapters],
                ["Leaders", "First article", "Next article"],
            )
            self.assertEqual(
                processor._build_toc_data(),
                [
                    {
                        "title": "Leaders", "level": 0,
                        "kind": "chapter", "chapter_index": 0,
                        "chapter_file": "chapter_0.html",
                    },
                    {
                        "title": "First article", "level": 1,
                        "kind": "chapter", "chapter_index": 1,
                        "chapter_file": "chapter_1.html",
                    },
                    {
                        "title": "Next article", "level": 0,
                        "kind": "chapter", "chapter_index": 2,
                        "chapter_file": "chapter_2.html",
                    },
                ],
            )

    def test_ncx_order_is_preserved_when_it_differs_from_spine_order(self):
        """The reader directory follows NCX; chapter_N still follows OPF."""
        processor = object.__new__(EPUBProcessor)
        processor.chapters = [
            {"title": "First in spine", "path": "OEBPS/first.xhtml"},
            {"title": "Second in spine", "path": "OEBPS/second.xhtml"},
        ]
        processor.toc = [
            {"title": "Second in NCX", "src": "OEBPS/second.xhtml", "level": 0},
            {"title": "First in NCX", "src": "OEBPS/first.xhtml", "level": 0},
        ]

        self.assertEqual(
            processor._build_toc_data(),
            [
                {
                    "title": "Second in NCX", "level": 0,
                    "kind": "chapter", "chapter_index": 1,
                    "chapter_file": "chapter_1.html",
                },
                {
                    "title": "First in NCX", "level": 0,
                    "kind": "chapter", "chapter_index": 0,
                    "chapter_file": "chapter_0.html",
                },
            ],
        )

    def test_ncx_omitted_spine_page_is_not_added_to_toc(self):
        """The reader directory is strictly the NCX, not a synthetic spine list."""
        processor = object.__new__(EPUBProcessor)
        processor.chapters = [
            {"title": "Cover page", "path": "OEBPS/cover.xhtml"},
            {"title": "Chapter", "path": "OEBPS/chapter.xhtml"},
        ]
        processor.toc = [
            {"title": "Chapter", "src": "OEBPS/chapter.xhtml", "level": 0},
        ]

        self.assertEqual(
            processor._build_toc_data(),
            [{
                "title": "Chapter", "level": 0,
                "kind": "chapter", "chapter_index": 1,
                "chapter_file": "chapter_1.html",
            }],
        )

    def test_processor_rejects_zip_entries_that_escape_extraction_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unsafe.epub"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("../outside.txt", "escaped")

            processor = EPUBProcessor(str(source), str(root / "staging"))

            with self.assertRaisesRegex(ValueError, "Unsafe EPUB archive path"):
                processor.extract_epub()
            self.assertFalse(Path(processor.temp_dir, "outside.txt").exists())
            self.assertFalse((root / "outside.txt").exists())

    def test_processor_rejects_manifest_paths_that_escape_extraction_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unsafe-manifest.epub"
            container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
            package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Unsafe</dc:title></metadata>
  <manifest><item id="chapter" href="../../../secret.html" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("META-INF/container.xml", container)
                archive.writestr("OEBPS/content.opf", package)

            processor = EPUBProcessor(str(source), str(root / "staging"))
            secret = Path(processor.temp_dir).parent / "secret.html"
            secret.write_text("LOCAL-SECRET-MUST-NOT-BE-PUBLISHED", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unsafe EPUB internal path"):
                processor.convert()

            generated = Path(processor.web_dir)
            if generated.exists():
                for page in generated.rglob("*.html"):
                    self.assertNotIn(
                        "LOCAL-SECRET-MUST-NOT-BE-PUBLISHED",
                        page.read_text(encoding="utf-8"),
                    )

    def test_epub_internal_path_resolver_rejects_absolute_and_encoded_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)

            self.assertEqual(
                processor._resolve_internal_path("chapter%201.xhtml", "OEBPS"),
                "OEBPS/chapter 1.xhtml",
            )
            self.assertEqual(
                processor._resolve_internal_path("../Images/cover.jpg", "OEBPS/Text"),
                "OEBPS/Images/cover.jpg",
            )
            for reference in (
                "../../secret.html",
                "%2e%2e/secret.html",
                "%252e%252e/secret.html",
                "/etc/passwd",
                "C:\\secret.html",
                "file:///etc/passwd",
            ):
                with self.subTest(reference=reference), self.assertRaisesRegex(
                    ValueError,
                    "Unsafe EPUB internal path",
                ):
                    processor._resolve_internal_path(reference, "OEBPS")

    def test_processor_rejects_traversal_in_chapter_resource_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unsafe-link.epub"
            self._write_minimal_epub(
                source,
                chapter_body='<img src="../../../secret.png" alt="">',
            )
            processor = EPUBProcessor(str(source), str(root / "staging"))

            with self.assertRaisesRegex(ValueError, "Unsafe EPUB internal path"):
                processor.convert()

    def test_server_processor_makes_malicious_epub_markup_and_metadata_inert(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                deployment_mode="server",
            )
            processor.book_title = '</title><script id="title-payload">alert(1)</script>'
            processor.authors = ['<img src=x onerror="alert(2)">']
            processor.tags = ['</span><script id="tag-payload">alert(3)</script>']
            processor.description = '<img src=x onerror="alert(4)"><b>description</b>'
            processor.chapters = [{
                "title": '<svg onload="alert(5)">One</svg>',
                "path": "chapter.xhtml",
            }]
            processor.toc = [
                {
                    "title": '<img src=x onerror="alert(6)">Contents',
                    "src": "chapter.xhtml",
                    "level": 0,
                    "anchor": 'bad\" onmouseover=\"alert(7)',
                    "old_file_name": "chapter.xhtml",
                }
            ]
            Path(processor.web_dir).mkdir(parents=True)
            body, styles = processor.process_html_content(
                '''<html><head>
                <link rel="stylesheet" href="https://attacker.example/track.css">
                <style>@import "https://attacker.example/x"; p { color: red; }</style>
                </head><body>
                <script id="body-payload">alert(8)</script>
                <img src="javascript:alert(9)" onerror="alert(10)">
                <a href="JaVaScRiPt:alert(11)" onclick="alert(12)">unsafe</a>
                <form action="/logout"><button>submit</button></form>
                <iframe srcdoc="<script>alert(13)</script>"></iframe>
                <svg onload="alert(14)"><script>alert(15)</script></svg>
                <p class="kept">Safe text</p>
                </body></html>''',
                "chapter.xhtml",
            )
            chapter_html = processor.create_chapter_template(
                body,
                styles,
                0,
                processor.chapters[0]["title"],
            )
            processor.create_index_page()
            book_html = Path(processor.web_dir, "index.html").read_text(
                encoding="utf-8"
            )

        combined = book_html + chapter_html
        for payload in (
            '<script id="title-payload"',
            '<script id="tag-payload"',
            "body-payload",
            " onerror=",
            " onclick=",
            " onmouseover=",
            "javascript:",
            "attacker.example",
            "<form",
            "<iframe",
            "<svg",
        ):
            self.assertNotIn(payload.lower(), combined.lower())
        self.assertIn('alert(1)', book_html)
        self.assertIn('description', book_html)
        self.assertIn('<p class="kept">Safe text</p>', chapter_html)

    def test_server_processor_preserves_safe_epub_inline_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                deployment_mode="server",
            )
            body, _ = processor.process_html_content(
                '''<body><p style="color: #234; text-align: center;
                background-image: url(https://attacker.example/pixel.png);
                behavior: url(#payload)" onclick="alert(1)">Styled text</p></body>''',
                "Text/chapter.xhtml",
            )

        self.assertIn('style="color: #234; text-align: center"', body)
        self.assertNotIn("attacker.example", body)
        self.assertNotIn("background-image", body)
        self.assertNotIn("behavior", body)
        self.assertNotIn("onclick", body)

    def test_server_processor_preserves_safe_css_rules_with_local_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                deployment_mode="server",
            )
            extracted = Path(processor.extract_dir)
            extracted.mkdir(parents=True)
            (extracted / "book.css").write_text(
                '''@import "https://attacker.example/payload.css";
                @font-face { font-family: "Book Serif";
                  src: url("Fonts/book.woff2") format("woff2"); }
                p.body { color: #234; text-align: justify;
                  background-image: url("Images/paper.png"); }
                a.track { color: navy;
                  background-image: url("https://attacker.example/pixel.png"); }
                a.sprite { color: teal;
                  background-image: image-set("https://attacker.example/2x.png" 2x); }''',
                encoding="utf-8",
            )

            processor.copy_resources()
            rendered = Path(
                processor.web_dir,
                "resources",
                "book.css",
            ).read_text(encoding="utf-8")

        self.assertIn('@font-face', rendered)
        self.assertIn('font-family: "Book Serif"', rendered)
        self.assertIn('url("Fonts/book.woff2")', rendered)
        self.assertIn('p.body', rendered)
        self.assertIn('text-align: justify', rendered)
        self.assertIn('url("Images/paper.png")', rendered)
        self.assertIn('a.track', rendered)
        self.assertIn('color: navy', rendered)
        self.assertIn('a.sprite', rendered)
        self.assertIn('color: teal', rendered)
        self.assertNotIn('@import', rendered)
        self.assertNotIn('attacker.example', rendered)

    def test_server_book_description_preserves_safe_metadata_markup(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                deployment_mode="server",
            )
            processor.book_title = "Styled Book"
            processor.description = (
                '<p class="summary">First <em>formatted</em> paragraph.</p>'
                '<ul><li>One</li><li>Two</li></ul>'
                '<a href="javascript:alert(1)" onclick="alert(2)">unsafe</a>'
                '<script>alert(3)</script>'
            )
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            rendered = Path(processor.web_dir, "index.html").read_text(
                encoding="utf-8"
            )

        self.assertRegex(
            rendered,
            r'<p class=(?:"summary"|summary)>First <em>formatted</em> paragraph\.',
        )
        self.assertRegex(rendered, r'<ul><li>One(?:</li>)?<li>Two')
        self.assertIn('<a>unsafe</a>', rendered)
        self.assertNotIn('javascript:', rendered)
        self.assertNotIn('onclick', rendered)
        self.assertNotIn('<script>alert(3)</script>', rendered)

    def test_server_processor_sanitizes_copied_svg_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                deployment_mode="server",
            )
            extracted = Path(processor.extract_dir)
            extracted.mkdir(parents=True)
            (extracted / "diagram.svg").write_text(
                '''<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">
                <script>alert(2)</script>
                <foreignObject><iframe src="https://attacker.example"></iframe></foreignObject>
                <a href="javascript:alert(3)"><rect width="10" height="10" fill="red"/></a>
                <path d="M0 0L10 10" stroke="black"/>
                </svg>''',
                encoding="utf-8",
            )
            (extracted / "payload.htm").write_text(
                '<script id="resource-payload">fetch("/api/session")</script>',
                encoding="utf-8",
            )
            (extracted / "payload.svgz").write_bytes(b"compressed-active-svg")
            (extracted / "payload.js").write_text(
                'fetch("/api/session")',
                encoding="utf-8",
            )
            (extracted / "safe.css").write_text(
                "p { color: red; }",
                encoding="utf-8",
            )
            (extracted / "unsafe.css").write_text(
                '@import "https://attacker.example/payload.css";',
                encoding="utf-8",
            )
            (extracted / "cover.png").write_bytes(b"passive-image")

            body, _ = processor.process_html_content(
                '<body><a href="payload.htm">payload</a>'
                '<img src="payload.svgz"></body>',
                "chapter.xhtml",
            )

            processor.copy_resources()
            rendered = Path(
                processor.web_dir,
                "resources",
                "diagram.svg",
            ).read_text(encoding="utf-8")
            resources = Path(processor.web_dir, "resources")
            blocked_resources = {
                name: (resources / name).exists()
                for name in ("payload.htm", "payload.svgz", "payload.js")
            }
            safe_css = (resources / "safe.css").read_text(encoding="utf-8")
            unsafe_css = (resources / "unsafe.css").read_text(encoding="utf-8")
            cover_bytes = (resources / "cover.png").read_bytes()

        for payload in (
            "script",
            "foreignObject",
            "iframe",
            "onload",
            "javascript:",
            "attacker.example",
        ):
            self.assertNotIn(payload.lower(), rendered.lower())
        self.assertIn("path", rendered)
        self.assertIn("M0 0L10 10", rendered)
        self.assertNotIn("payload.htm", body)
        self.assertNotIn("payload.svgz", body)
        self.assertEqual(blocked_resources, {
            "payload.htm": False,
            "payload.svgz": False,
            "payload.js": False,
        })
        self.assertEqual(safe_css, "p { color: red; }")
        self.assertEqual(unsafe_css, "")
        self.assertEqual(cover_bytes, b"passive-image")

    def test_ssg_processor_preserves_existing_epub_markup_metadata_and_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory, deployment_mode="ssg")
            processor.book_title = '<script id="ssg-title">title()</script>'
            processor.authors = ['<b id="ssg-author">Author</b>']
            processor.description = '<em id="ssg-description">Description</em>'
            processor.tags = ['<i id="ssg-tag">Tag</i>']
            processor.chapters = [{"title": '<u id="ssg-chapter">One</u>'}]
            Path(processor.web_dir).mkdir(parents=True)

            body, styles = processor.process_html_content(
                '''<html><head>
                <link rel="stylesheet" href="https://example.test/book.css">
                <style>p { color: red; background: url(image.png); }</style>
                </head><body><p style="color:red" onclick="run()">Text</p>
                <script id="ssg-body">body()</script></body></html>''',
                "chapter.xhtml",
            )
            chapter_html = processor.create_chapter_template(
                body,
                styles,
                0,
                processor.chapters[0]["title"],
            )
            processor.create_index_page()
            index_html = Path(processor.web_dir, "index.html").read_text(
                encoding="utf-8"
            )

            extracted = Path(processor.extract_dir)
            extracted.mkdir(parents=True)
            (extracted / "active.svg").write_text(
                '<svg onload="run()"><script>svg()</script></svg>',
                encoding="utf-8",
            )
            (extracted / "linked.htm").write_text(
                '<script>linked()</script>',
                encoding="utf-8",
            )
            processor.copy_resources()

            self.assertIn('onclick="run()"', chapter_html)
            self.assertIn('style="color:red"', chapter_html)
            self.assertIn('id="ssg-body"', chapter_html)
            self.assertIn("background: url(image.png)", chapter_html)
            self.assertIn("https://example.test/book.css", chapter_html)
            for marker in (
                "ssg-title",
                "ssg-author",
                "ssg-description",
                "ssg-tag",
            ):
                self.assertIn(marker, index_html)
            self.assertIn("ssg-chapter", chapter_html)
            self.assertIn(
                'onload="run()"',
                Path(processor.web_dir, "resources", "active.svg").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertTrue(
                Path(processor.web_dir, "resources", "linked.htm").exists()
            )

    def test_generated_book_pages_apply_base_path_without_runtime_url_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                urls=SiteURLs("/reader/"),
            )
            processor.book_title = "A Book"
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            book_html = Path(processor.web_dir, "index.html").read_text(encoding="utf-8")
            chapter_html = processor.create_chapter_template("<p>Text</p>", "", 0, "One")

        for html in (book_html, chapter_html):
            self.assertRegex(html, r"/reader/assets/immutable/")
            self.assertNotIn("function addBasePath", html)
        self.assertIn("window.initScriptBook()", book_html)
        self.assertIn("window.initScriptChapter()", chapter_html)

    def test_server_reader_pages_gate_protected_startup_behind_cache_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                deployment_mode="server",
            )
            processor.book_title = "A Book"
            processor.chapters = [{"title": "One"}]
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            book_html = Path(processor.web_dir, "index.html").read_text(
                encoding="utf-8"
            )
            chapter_html = processor.create_chapter_template(
                "<p>Text</p>",
                "",
                0,
                "One",
            )

        for html, client_name, init_name in (
            (book_html, "startBookClients", "initScriptBook"),
            (chapter_html, "startChapterClients", "initScriptChapter"),
        ):
            self.assertRegex(
                html,
                r'/assets/immutable/cache-boundary\.[0-9a-f]{12}\.js',
            )
            self.assertIn(
                f"window.EpubBrowserCacheBoundary.start({client_name})",
                html,
            )
            self.assertIn(f"function {client_name}()", html)
            self.assertIn(f"window.{init_name}()", html)
            self.assertLess(
                html.index("cache-boundary."),
                html.index("reading-progress."),
            )

        for html in (self._book_html(), self._chapter_html()):
            self.assertNotIn("EpubBrowserCacheBoundary.start", html)

    def test_server_reader_pages_load_auth_before_personal_data_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub",
                directory,
                deployment_mode="server",
            )
            processor.book_title = "A Book"
            processor.chapters = [{"title": "One"}]
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            book_html = Path(processor.web_dir, "index.html").read_text(
                encoding="utf-8"
            )
            chapter_html = processor.create_chapter_template(
                "<p>Text</p>",
                "",
                0,
                "One",
            )

        for html in (book_html, chapter_html):
            self.assertRegex(html, r'/assets/immutable/auth\.[0-9a-f]{12}\.js')
            self.assertLess(html.index('/immutable/auth.'), html.index('/immutable/reading-progress.'))
            self.assertNotIn('syncShelfBtn', html)

        for html in (self._book_html(), self._chapter_html()):
            self.assertNotRegex(html, r'/assets/immutable/auth\.[0-9a-f]{12}\.js')
            self.assertNotIn('EpubBrowserAuth.init', html)
            self.assertNotIn('syncShelfBtn', html)

    def test_dynamic_browser_urls_use_the_generated_base_path_runtime(self):
        scripts = {
            name: Path("epub_browser", "assets", name).read_text(encoding="utf-8")
            for name in (
                "cache-boundary.js",
                "library.js",
                "i18n.js",
                "bookshelf.js",
                "chapter.js",
                "annotation-hub.js",
            )
        }

        self.assertIn(
            "EpubBrowserURL.publicPath('/sw.js')",
            scripts["cache-boundary.js"],
        )
        self.assertIn("publicPath('/assets/manifest.'", scripts["i18n.js"])
        self.assertGreaterEqual(
            scripts["bookshelf.js"].count("EpubBrowserURL.publicPath('/book/"),
            1,
        )
        self.assertGreaterEqual(
            scripts["chapter.js"].count("EpubBrowserURL.publicPath('/book/"),
            3,
        )
        self.assertIn("publicPath('/book-metadata.json')", scripts["annotation-hub.js"])
        self.assertIn("publicPath('/book/'", scripts["annotation-hub.js"])
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            self.assertLess(
                html.index("window.EpubBrowserBasePath"),
                html.index("window.EpubBrowserI18n.init()"),
            )

    def test_generated_footers_show_the_package_version_and_load_the_update_checker(self):
        package_version = subprocess.check_output(
            [sys.executable, "setup.py", "--version"],
            text=True,
        ).strip()

        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            footer = html[html.index('<footer'):html.index('</footer>')]
            self.assertRegex(
                footer,
                rf'data-current-version=(?:["\'])?{package_version}(?:["\' >])',
            )
            self.assertIn(f'v{package_version}', footer)
            self.assertRegex(
                html,
                r'/assets/immutable/version-check\.[0-9a-f]{12}\.js',
            )

    def test_all_generated_pages_bootstrap_shared_i18n_before_ui_scripts(self):
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            self.assertRegex(html, r'/assets/immutable/i18n\.[0-9a-f]{12}\.js')
            self.assertIn('window.EpubBrowserI18n.init()', html)
            self.assertLess(html.index('window.EpubBrowserI18n.init()'), html.index('/assets/immutable/theme.'))
            self.assertNotIn('/assets/manifest.json', html)
            self.assertRegex(
                html,
                r'<noscript><link\b(?=[^>]*\brel=(?:"manifest"|manifest))(?=[^>]*\bhref=(?:"/assets/manifest\.en\.json"|/assets/manifest\.en\.json))[^>]*>',
            )

    def test_chapter_separates_ui_and_epub_content_languages(self):
        html = self._chapter_html()

        self.assertIn('<html lang="en"', html)
        self.assertRegex(html, r'<article[^>]+id="eb-content"[^>]+lang="en"')

    def test_book_and_chapter_keep_epub_language_off_the_ui_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)
            processor.book_title = "A Book"
            processor.description = "Une description"
            processor.lang = "fr"
            processor.chapters = [{"title": "One"}]
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            book_html = Path(processor.web_dir, "index.html").read_text(encoding="utf-8")
            chapter_html = processor.create_chapter_template("<p>Texte</p>", "", 0, "One")

        self.assertRegex(book_html, r'<html\s+lang=(?:"en"|en)(?:\s|>)')
        self.assertRegex(book_html, r'<div\b(?=[^>]*\bclass=(?:"book-info-desc"|book-info-desc))(?=[^>]*\blang=(?:"fr"|fr))[^>]*>')
        self.assertIn('<html lang="en"', chapter_html)
        self.assertRegex(chapter_html, r'<article[^>]+id="eb-content"[^>]+lang="fr"')

    def test_book_page_localizes_shell_but_marks_metadata_as_content(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor('book.epub', directory)
            processor.book_title = 'A Book'
            processor.lang = 'fr'
            processor.description = '<p>Texte original</p>'
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            html = Path(processor.web_dir, 'index.html').read_text(encoding='utf-8')

        self.assertRegex(html, r'data-i18n=(?:["\'])?book\.startReading')
        self.assertRegex(html, r'data-i18n=(?:["\'])?book\.tableOfContents')
        self.assertRegex(html, r'class=(?:["\'])?book-info-desc(?=[^>]*\blang=(?:["\'])?fr)')
        self.assertIn('A Book', html)
        self.assertIn('Texte original', html)

    def test_book_script_has_no_literal_user_notifications_or_confirmations(self):
        script = Path('epub_browser/assets/book.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")

    def test_chapter_script_routes_notifications_and_confirmations_through_i18n(self):
        script = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")
        self.assertIn("i18n.t('reader.loadingNextChapter'", script)
        self.assertIn("i18n.t('reader.chapterLoadFailed'", script)
        self.assertIn("i18n.t('settings.saved'", script)
        self.assertIn("i18n.t('reader.chapterNumber'", script)
        self.assertIn("i18n.t('settings.continuousScrollTip'", script)

    def test_normal_scroll_chapter_navigation_swaps_only_the_reading_body(self):
        script = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')

        self.assertIn('function navigateScrollingChapter(', script)
        start = script.index('function navigateScrollingChapter(')
        end = script.index('\n    function handleKeyDown(', start)
        navigation = script[start:end]

        self.assertIn("xhr.open('GET', url, true);", navigation)
        self.assertIn("tempDiv.querySelector('#eb-content')", navigation)
        self.assertIn("chapterContent.getAttribute('data-chapter-index')", navigation)
        self.assertIn("chapterContent.getAttribute('data-book-hash')", navigation)
        self.assertIn('while (content.firstChild) content.removeChild(content.firstChild);', navigation)
        self.assertIn('content.appendChild(childNodes[i].cloneNode(true));', navigation)
        self.assertNotIn('content.innerHTML', navigation)
        self.assertIn("window.history.pushState({chapterIndex: target.index}, '', url);", navigation)
        self.assertIn("window.addEventListener('popstate'", navigation)
        self.assertIn("navigateScrollingChapter(window.location.href, { history: false });", navigation)
        self.assertIn('if (isPaginationMode || isContinuousScroll) return false;', navigation)
        self.assertIn('target.index === parseInt(chapter_index, 10)', navigation)
        self.assertNotIn('target.path === window.location.pathname', navigation)
        self.assertIn('syncChapterScopedControls(target.index);', navigation)
        self.assertIn('wireNormalScrollChapterNavigation();', script)
        self.assertIn('function syncChapterScopedControls(chapterIndex) {', script)
        self.assertRegex(
            script,
            r"document\.querySelectorAll\(\s*"
            r"'\[data-ai-learning-canvas\], \[data-ai-followup-drawer\]'\s*\)",
        )
        self.assertIn("setAttribute('data-chapter-index', chapterIndex);", script)

        keyboard = script[script.index('function handleKeyDown('):script.index('\n    prevPageBtn.addEventListener', script.index('function handleKeyDown('))]
        self.assertIn('navigateScrollingChapter(prev, { history: true });', keyboard)
        self.assertIn('navigateScrollingChapter(next, { history: true });', keyboard)

        toc_start = script.index("a.addEventListener('click', function(e) {")
        toc_end = script.index('\n                    });', toc_start)
        book_toc = script[toc_start:toc_end]
        self.assertIn('navigateScrollingChapter(this.href, { history: true });', book_toc)
        self.assertIn('!isPaginationMode && !isContinuousScroll', book_toc)

    def test_partial_chapter_swap_refreshes_ai_canvas_without_stale_results(self):
        chapter_script = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')
        canvas_script = Path('epub_browser/assets/ai-canvas.js').read_text(encoding='utf-8')

        self.assertIn('function refreshPartialChapterCanvas(chapterIndex) {', chapter_script)
        self.assertIn('window.EpubBrowserAICanvas.refresh(chapterIndex);', chapter_script)
        self.assertIn('refreshPartialChapterCanvas(target.index);', chapter_script)

        self.assertIn('root.EpubBrowserAICanvas = {', canvas_script)
        self.assertIn('function refresh(chapterIndex) {', canvas_script)
        self.assertIn('refresh: refresh', canvas_script)
        self.assertIn('state.contextVersion += 1;', canvas_script)
        self.assertIn('closeEventSources();', canvas_script)
        self.assertIn('if (!isCurrentContext(context, contextVersion)) return null;', canvas_script)
        self.assertIn('if (!isCurrentContext(context, contextVersion)) return;', canvas_script)
        context_guard = canvas_script[
            canvas_script.index('function isCurrentContext('):canvas_script.index(
                '\n  function clearChapter(', canvas_script.index('function isCurrentContext(')
            )
        ]
        self.assertIn('var article = currentArticleFor(context);', context_guard)
        self.assertNotIn("document.querySelector('#eb-content')", context_guard)
        self.assertRegex(
            canvas_script,
            r'function generate\(button, context, contextVersion\) \{\s*'
            r'if \(!isCurrentContext\(context, contextVersion\)\) return;',
        )
        self.assertEqual(
            canvas_script.count(
                'if (confirmed && isCurrentContext(context, contextVersion)) '
                'generate(button, context, contextVersion);'
            ),
            2,
        )

    def test_annotation_menu_includes_a_text_only_copy_action(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertIn('annotation-btn-copy', script)
        self.assertIn('copyText(source.text)', script)

    def test_annotation_storage_exposes_reading_independent_read_apis(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertIn('var AnnotationStorage = {', script)
        self.assertIn('init: function() {', script)
        self.assertIn('getAll: function() {', script)
        self.assertIn('getByBook: function(bookHash) {', script)
        self.assertIn('getStorageType: function() {', script)
        self.assertIn('isBackendAvailable: function() {', script)
        self.assertIn('global.AnnotationStorage = AnnotationStorage;', script)

    def test_chapter_can_focus_an_annotation_requested_by_query_parameter(self):
        script = Path("epub_browser/assets/chapter.js").read_text(encoding="utf-8")
        annotation_script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation.css").read_text(encoding="utf-8")

        self.assertIn("requestedAnnotationId()", script)
        self.assertIn("focusAnnotation(annotationId)", script)
        self.assertIn("focusAnnotation: function(id)", annotation_script)
        self.assertIn("annotation-focus-active", css)

    def test_reader_annotation_edits_are_silent_when_successful(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertNotIn("Utils.showNotification('Annotation added', 'success')", script)
        self.assertNotIn("Utils.showNotification('Annotation updated', 'success')", script)
        self.assertNotIn("Utils.showNotification('Annotation deleted', 'info')", script)
        self.assertIn("Utils.showNotification(tr('addFailed', { error: err.message }), 'error')", script)
        self.assertIn("Utils.showNotification(tr('updateFailed', { error: err.message }), 'error')", script)
        self.assertIn("Utils.showNotification(tr('deleteFailed', { error: err.message }), 'error')", script)

    def test_annotation_editor_routes_user_copy_through_i18n(self):
        script = Path('epub_browser/assets/annotation.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"Utils\.showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")
        self.assertIn("i18n.t('annotations.noteOptional'", script)
        self.assertIn("i18n.t('annotations.storageLocationChanged'", script)
        self.assertIn("tr('defaultColorTip')", script)
        self.assertIn("tr('colorReorderTip')", script)
        color_css = Path('epub_browser/assets/annotation.css').read_text(encoding='utf-8')
        self.assertIn('content: attr(data-tooltip);', color_css)

    def test_reader_does_not_append_an_emoji_to_noted_highlights(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation.css").read_text(encoding="utf-8")

        self.assertNotIn('has-note', script)
        self.assertNotIn("content: '📝'", css)

    def test_remove_from_shelf_uses_theme_safe_destructive_colors(self):
        css = Path("epub_browser/assets/book.css").read_text(encoding="utf-8")

        rules = css[css.index('#toggleShelfBtn.in-shelf {'):css.index('}', css.index('#toggleShelfBtn.in-shelf {'))]
        hover_rules = css[css.index('#toggleShelfBtn.in-shelf:hover {'):css.index('}', css.index('#toggleShelfBtn.in-shelf:hover {'))]
        self.assertIn('background: #c0392b;', rules)
        self.assertIn('color: #fff;', rules)
        self.assertIn('background: #a93226;', hover_rules)

    def test_cloud_annotations_retry_restoration_without_applying_a_stale_chapter_response(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertIn('renderVersion: 0,', script)
        self.assertIn('var renderVersion = ++this.renderVersion;', script)
        self.assertIn('if (renderVersion !== self.renderVersion) return;', script)
        self.assertIn('return false;', script)
        self.assertIn('self.renderAll(true);', script)
        self.assertIn("Utils.showNotification(tr('restoreFailed'), 'error')", script)

    def test_continuous_reader_loads_chapter_relative_annotation_positioning(self):
        html = self._chapter_html()
        chapter_script = Path("epub_browser/assets/chapter.js").read_text(encoding="utf-8")
        annotation_script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        positioning = re.search(r'/assets/immutable/annotation-position\.[0-9a-f]{12}\.js', html)
        annotations = re.search(r'/assets/immutable/annotation\.[0-9a-f]{12}\.js', html)
        self.assertIsNotNone(positioning)
        self.assertIsNotNone(annotations)
        self.assertLess(positioning.start(), annotations.start())
        self.assertIn('getChapterIndexFromSource: function(source)', annotation_script)
        self.assertIn('StorageManager.getByBook(currentBookHash)', annotation_script)
        self.assertIn('refreshContinuousAnnotations();', chapter_script)

    def test_library_does_not_offer_a_manual_cache_update_button(self):
        script = Path("epub_browser/assets/library.js").read_text(encoding="utf-8")

        self.assertNotIn('update-cache-btn', script)
        self.assertNotIn('Updating cache...', script)

    def test_book_page_offers_a_progress_aware_continue_reading_action(self):
        html = self._book_html()
        script = Path("epub_browser/assets/book.js").read_text(encoding="utf-8")
        styles = Path("epub_browser/assets/book.css").read_text(encoding="utf-8")

        self.assertRegex(html, r'id=(?:["\'])?continueReadingBtn')
        self.assertRegex(html, r'id=(?:["\'])?continueReadingBtnText')
        self.assertRegex(html, r'id=(?:["\'])?continueReadingMenuToggle')
        self.assertRegex(html, r'id=(?:["\'])?clearReadingProgressMenu')
        self.assertRegex(html, r'id=(?:["\'])?clearReadingProgressBtn')
        self.assertRegex(html, r'data-i18n-aria-label=(?:["\'])?book\.clearReadingProgress')
        self.assertRegex(html, r'data-i18n=(?:["\'])?book\.clear')
        self.assertIn("updateContinueReadingButton(book_hash);", script)
        self.assertIn("setClearReadingProgressAvailability(!!resumeChapter && !isKindleMode());", script)
        self.assertIn("clearButton.hidden = !available;", script)
        self.assertIn("clearMenuToggle.setAttribute('aria-expanded'", script)
        self.assertIn("window.EpubDialog.confirm({", script)
        self.assertIn("message: bookT('book.clearReadingProgressConfirm')", script)
        self.assertIn("'DELETE',", script)
        self.assertIn("true,\n                    true", script)
        self.assertIn("if (!result || result.error)", script)
        self.assertIn("book.clearReadingProgressFailed", script)
        clear_handler = script.index("window.EpubDialog.confirm({")
        server_request = script.index("window.EpubReadingProgress.request(", clear_handler)
        self.assertIn("if (!window.EpubReadingProgress.isServerMode())", script)
        self.assertLess(
            server_request,
            script.index("clearLocalProgress();", server_request),
        )
        self.assertNotIn("matchMedia", script)
        self.assertIn(".continue-reading-control.has-reading-progress:hover #continueReadingBtn", styles)
        self.assertIn("transform: none;", styles)
        self.assertIn(".continue-reading-control.has-reading-progress:focus-within", styles)
        self.assertIn(".continue-reading-menu-toggle[aria-expanded=\"true\"] i", styles)
        self.assertRegex(
            styles,
            r"\.continue-reading-menu\s*\{[^}]*width:\s*100%;[^}]*min-width:\s*0;",
        )
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn("overflow: visible;", styles)
        self.assertIn("document.getElementById(readKey)", script)
        self.assertIn("chapterLinks[i].id.split('#')[0] === readKey", script)
        self.assertIn("bookT('book.continueReading')", script)
        self.assertIn("bookT('book.startReading')", script)

    def test_book_toc_marks_server_synced_reading_progress_with_the_reader_identity(self):
        script = Path("epub_browser/assets/book.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/book.css").read_text(encoding="utf-8")

        self.assertIn("markReadingChapter(readKey, getProgressIdentity())", script)
        self.assertIn("if (window.EpubBrowserMode !== 'server') return '';", script)
        self.assertIn("return window.EpubReadingProgress.getUsername();", script)
        self.assertNotIn("return 'shared';", script)
        self.assertIn("markReadingChapter(currentChapter);", script)
        self.assertIn("if (username) {", script)
        self.assertIn("chapter-sync-tag", script)
        self.assertIn("chapter-title-with-sync", script)
        self.assertIn("bookT('book.cloudSyncUser'", script)
        self.assertIn("bookT('book.cloudSyncUserAria'", script)
        self.assertIn(".chapter-sync-tag", css)
        self.assertIn(".chapter-title-with-sync", css)
        self.assertIn(".chapter-page", css)
        self.assertIn("flex: 0 0 auto;", css)
        self.assertIn("margin-left: auto;", css)
        self.assertIn("padding-left: 16px;", css)
        self.assertIn("padding-left: 10px;", css)

    def test_reader_includes_chapter_sync_and_progress_bar_controls(self):
        book_html = self._book_html()
        chapter_html = self._chapter_html()
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        self.assertRegex(book_html, r'/assets/immutable/reading-progress\.[0-9a-f]{12}\.js')
        self.assertRegex(chapter_html, r'/assets/immutable/reading-progress\.[0-9a-f]{12}\.js')
        self.assertIn('id="showReadingProgressBarToggle"', chapter_html)
        self.assertIn('.reading-progress-container.is-progress-bar-hidden', css)

    def test_book_and_chapter_return_to_the_library_without_redirect_or_unused_fragment(self):
        for html in (self._book_html(), self._chapter_html()):
            self.assertNotIn('/index.html#', html)
            self.assertNotIn('/#AwU__ARVZEOf9_LKuztYxQ', html)
            self.assertRegex(html, r'href=(?:["\'])?/(?:["\' >])')

    def test_pages_link_one_shared_application_navigation_stylesheet(self):
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            self.assertRegex(html, r'/assets/immutable/breadcrumb\.[0-9a-f]{12}\.css')
            self.assertIn('app-nav', html)
        css = Path("epub_browser/assets/breadcrumb.css").read_text(encoding="utf-8")
        self.assertIn("width: min(calc(100% - 40px), 1180px)", css)
        self.assertIn("min-height: 68px", css)
        self.assertIn(".app-nav-brand", css)
        self.assertIn(".app-nav-links", css)
        self.assertIn(".app-nav-actions", css)
        self.assertIn(".app-nav-theme", css)
        self.assertIn("backdrop-filter: blur(18px)", css)
        header_rule = css[
            css.index(".app-header {"):
            css.index("}", css.index(".app-header {"))
        ]
        self.assertIn("position: relative", header_rule)
        self.assertNotIn("position: sticky", header_rule)

    def test_mobile_application_navigation_uses_the_shared_reader_breakpoint(self):
        css = Path("epub_browser/assets/breadcrumb.css").read_text(encoding="utf-8")
        book_html = self._book_html()
        chapter_html = self._chapter_html()

        self.assertIn(".app-nav-brand span", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn(".app-nav-links", css)
        self.assertIn("flex-wrap: wrap;", css)
        self.assertIn("min-width: 0;", css)
        self.assertIn("overflow-x: auto;", css)
        for html in (book_html, chapter_html):
            self.assertIn('app-nav-links', html)
            self.assertNotIn('app-context-path', html)
            self.assertIn('app-nav-theme', html)

    def test_small_reader_uses_bottom_controls_without_the_desktop_side_toolbar(self):
        shared_css = Path("epub_browser/assets/breadcrumb.css").read_text(
            encoding="utf-8"
        )
        chapter_css = Path("epub_browser/assets/chapter.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("@media (max-width: 768px)", shared_css)
        shared_mobile = shared_css.split("@media (max-width: 768px)", 1)[1]
        shared_mobile = shared_mobile.split("@media (max-width: 430px)", 1)[0]
        chapter_mobile = chapter_css.split("@media (max-width: 768px)", 1)[-1]
        chapter_mobile = chapter_mobile.split("@media (max-width: 480px)", 1)[0]

        self.assertRegex(
            shared_mobile,
            r"\.reader-toolbar\.top-controls,\s*\.reading-controls\s*\{\s*display:\s*none;",
        )
        self.assertRegex(
            shared_mobile,
            r"\.app-nav-link\s*\{[^}]*min-height:\s*44px;",
        )
        self.assertRegex(
            chapter_mobile,
            r"\.mobile-controls\s*\{\s*display:\s*flex;",
        )
        self.assertRegex(
            chapter_mobile,
            r"\.mobile-controls\s+\.control-btn[^}]*min-height:\s*44px;",
        )
        self.assertIn(".mobile-controls .control-btn span {\n    display: none;", chapter_css)
        self.assertIn("content: attr(aria-label);", chapter_mobile)
        self.assertNotIn("@media (hover: hover)", chapter_mobile)
        self.assertRegex(
            chapter_mobile,
            r"\.mobile-controls\s*\{[^}]*overflow-x:\s*auto;",
        )
        self.assertIn("env(safe-area-inset-bottom)", chapter_mobile)
        self.assertRegex(
            chapter_mobile,
            r"\.mobile-controls\s+#mobileTopBtn\s*\{\s*display:\s*none;",
        )
        self.assertRegex(
            chapter_mobile,
            r"\.mobile-controls\s+#mobileTopBtn\.is-visible\s*\{\s*display:\s*flex;",
        )

        chapter_script = Path("epub_browser/assets/chapter.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("mobileTopBtn.classList.add('is-visible')", chapter_script)
        self.assertIn("mobileTopBtn.classList.remove('is-visible')", chapter_script)

        chapter_html = self._chapter_html()
        self.assertNotIn('id="mobileAIReadingBtn"', chapter_html)
        self.assertNotIn('data-ai-learning-canvas', chapter_html)
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory, deployment_mode="server")
            processor.book_title = "A Book"
            processor.chapters = [{"title": "One"}]
            server_chapter_html = processor.create_chapter_template("<p>Text</p>", "", 0, "One")
        self.assertIn('id="mobileAIReadingBtn"', server_chapter_html)
        mobile_ai_start = server_chapter_html.index('id="mobileAIReadingBtn"')
        mobile_ai_end = server_chapter_html.index('</button>', mobile_ai_start)
        mobile_ai_button = server_chapter_html[mobile_ai_start:mobile_ai_end]
        self.assertIn('data-ai-reading-hub', mobile_ai_button)
        self.assertIn('aria-haspopup="dialog"', mobile_ai_button)
        self.assertNotIn('data-ai-learning-canvas', mobile_ai_button)
        self.assertNotIn('id="mobileThemeBtn"', chapter_html)

    def test_theme_picker_stays_anchored_to_the_top_right_action_on_mobile(self):
        script = Path("epub_browser/assets/theme.js").read_text(encoding="utf-8")

        self.assertIn("var rect = toggleBtn.getBoundingClientRect();", script)
        self.assertIn("menu.style.left = 'auto';", script)
        self.assertNotIn("mobileThemeBtn", script)
        self.assertNotIn("menu.style.bottom = '80px';", script)

    def test_reader_chrome_uses_one_default_font_stack(self):
        for path in ("library.css", "book.css", "chapter.css"):
            css = Path("epub_browser/assets", path).read_text(encoding="utf-8")
            self.assertIn("font-family: var(--font-family, system-ui, -apple-system, sans-serif)", css)
        for path in ("library.js", "book.js"):
            script = Path("epub_browser/assets", path).read_text(encoding="utf-8")
            self.assertIn('fontFamily === "ebook-default"', script)
            self.assertIn("document.body.style.fontFamily = '';", script)

    def test_default_reader_assets_use_immutable_content_addressed_urls(self):
        library_html = self._library_html()
        book_html = self._book_html()
        self.assertRegex(library_html, r'/assets/immutable/library\.[0-9a-f]{12}\.css')
        self.assertRegex(library_html, r'/assets/immutable/library\.[0-9a-f]{12}\.js')
        self.assertRegex(book_html, r'/assets/immutable/book\.[0-9a-f]{12}\.css')
        self.assertRegex(book_html, r'/assets/immutable/book\.[0-9a-f]{12}\.js')
        self.assertNotIn('?v=', library_html + book_html)

    def test_pagination_mode_does_not_access_the_removed_custom_css_panel(self):
        script = Path("epub_browser/assets/chapter.js").read_text(encoding="utf-8")

        self.assertNotIn('document.querySelector(".custom-css-panel").style', script)

    def test_chapter_script_uses_an_immutable_content_addressed_url(self):
        self.assertRegex(self._chapter_html(), r'/assets/immutable/chapter\.[0-9a-f]{12}\.js')

    def test_initial_font_size_update_uses_content_loading_only(self):
        script = Path("epub_browser/assets/chapter.js").read_text(encoding="utf-8")

        self.assertIn('showLoading();\n        requestAnimationFrame(function()', script)
        self.assertIn('updateFontSize(s);', script)
        self.assertNotIn('applyFontSizeWithLoading', script)

    def test_content_loading_uses_the_active_theme_surface(self):
        css = Path("epub_browser/assets/loading.css").read_text(encoding="utf-8")

        self.assertIn('color-mix(in srgb, var(--card-bg) 72%, transparent)', css)
        self.assertNotIn('rgba(15, 23, 42, 0.32)', css)

    def test_content_loading_is_scoped_to_the_reading_content_container(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        container_rules = css[css.index('.eb-content-container {'):css.index('}', css.index('.eb-content-container {'))]
        self.assertIn('position: relative;', container_rules)
        self.assertRegex(self._chapter_html(), r'/assets/immutable/chapter\.[0-9a-f]{12}\.css')

    def test_pagination_uses_a_chapter_top_bar_not_a_breadcrumb_container(self):
        html = self._chapter_html()

        self.assertIn('class="chapter-top-bar app-header"', html)
        self.assertNotIn('class="breadcrumb-container"', html)

    def test_chapter_application_header_keeps_the_shared_navigation_geometry(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        self.assertIn(".container {", css)
        self.assertNotIn(".container, .chapter-top-bar", css)
        self.assertNotRegex(
            css,
            r"\.chapter-top-bar\s*\{[^}]*(?:width|max-width|margin|padding-top)\s*:",
        )

    def test_book_toc_offers_a_direct_book_home_link(self):
        html = self._chapter_html()
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        self.assertRegex(html, r'<a\b[^>]*\bclass="toc-book-home"[^>]*\bhref="index\.html"')
        self.assertIn('data-i18n-aria-label="reader.openBookHome"', html)
        self.assertIn('id="bookHomeClose"', html)
        self.assertIn('.toc-header-actions', css)
        self.assertIn('min-width: 44px;', css)

    def test_chapter_footer_uses_a_divider_instead_of_a_header_surface(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")
        footer_rules = css[css.index(".eb-footer {"):css.index("}", css.index(".eb-footer {"))]

        self.assertIn("border-top: 1px solid var(--footer-border);", footer_rules)
        self.assertNotIn("background: var(--header-bg);", footer_rules)

    def test_chapter_content_has_desktop_breathing_room_below_the_app_header(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")
        content_rules = css[css.index(".eb-content-container {"):css.index("}", css.index(".eb-content-container {"))]

        self.assertIn("margin-top: 18px;", content_rules)
        self.assertIn(".navigation, .custom-css-panel, .eb-content-container", css)

    def test_book_and_chapter_do_not_repeat_location_breadcrumbs(self):
        for html in (self._book_html(), self._chapter_html()):
            self.assertNotIn('app-context-path', html)
            self.assertNotRegex(html, r'data-i18n-aria-label=(?:["\'])?(?:book|reader)\.breadcrumb')

    def test_generated_pages_do_not_include_fullscreen_loading_overlay(self):
        for html in (self._library_html(), self._chapter_html()):
            self.assertNotIn('id="loadingOverlay"', html)
        self.assertIn('id="contentLoading"', self._chapter_html())

    def test_chapter_initial_layout_reflow_stays_behind_the_content_mask(self):
        html = self._chapter_html()
        loading_css = Path("epub_browser/assets/loading.css").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            html,
            r'class="content-loading is-visible"[^>]+id="contentLoading"',
        )
        self.assertIn('backdrop-filter: blur(12px)', loading_css)

    def _library_html(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            library.create_library_home()
            return Path(directory, "index.html").read_text(encoding="utf-8")

    def _server_html(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = AssetPublisher(
                Path('epub_browser/assets'),
                directory,
            ).publish()
            publish_library_shell(
                Path(directory),
                (),
                assets,
                SiteURLs(),
                deployment_mode="server",
            )
            return Path(directory, "index.html").read_text(encoding="utf-8")

    def _chapter_html(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)
            processor.book_title = "A Book"
            processor.chapters = [{"title": "One"}]
            return processor.create_chapter_template("<p>Text</p>", "", 0, "One")

    def _book_html(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)
            processor.book_title = "A Book"
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            return Path(processor.web_dir, "index.html").read_text(encoding="utf-8")

    @staticmethod
    def _write_minimal_epub(path, chapter_body="<h1>One</h1><p>Text</p>"):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:test:stable</dc:identifier>
    <dc:title>Stable Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>
"""
        chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body>{chapter_body}</body></html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", package)
            archive.writestr("OEBPS/chapter.xhtml", chapter)

    def test_library_separates_primary_navigation_from_page_summary(self):
        html = self._library_html()

        self.assertRegex(html, r'<nav\b(?=[^>]*\bclass=["\'][^"\']*\bapp-nav-primary\b)(?=[^>]*\bdata-i18n-aria-label=(?:["\'])?library\.navigation(?:["\'])?)[^>]*>')
        self.assertRegex(html, r'<a\b(?=[^>]*\bclass=(?:["\'])?app-nav-brand)(?=[^>]*\baria-label=(?:["\'])?EPUB Browser(?:["\'])?)[^>]*>')
        self.assertRegex(html, r'<h1\b[^>]*\bdata-i18n=(?:["\'])?library\.title(?:["\'])?[^>]*>')
        breadcrumb = html[html.index('<nav'):html.index('</nav>')]
        self.assertRegex(breadcrumb, r'/assets/immutable/logo-mark-color\.[0-9a-f]{12}\.png')
        self.assertIn('app-nav-brand-mark', breadcrumb)
        self.assertIn('app-nav-links', breadcrumb)
        self.assertIn('app-nav-theme', breadcrumb)
        self.assertIn('id=bookshelfBtn', breadcrumb)
        self.assertIn('id=annotationsBtn', breadcrumb)
        self.assertNotIn('id=libraryBookCount', breadcrumb)
        self.assertNotIn('id=libraryTagCount', breadcrumb)
        self.assertIn('class=library-overview', html)
        self.assertIn('class=library-summary', html)
        self.assertNotRegex(breadcrumb, r'\bid=(?:["\'])?loginCard(?:["\'])?')
        self.assertNotIn('library-info', html)

    def test_locale_selector_exists_only_in_library_navigation(self):
        library = self._library_html()
        self.assertEqual(len(re.findall(r'\bid=(?:["\'])?localeSelect(?:["\' >])', library)), 1)
        breadcrumb = library[library.index('<nav'):library.index('</nav>')]
        self.assertRegex(breadcrumb, r'\bid=(?:["\'])?localeToggle(?:["\' >])')
        self.assertRegex(breadcrumb, r'\baria-haspopup=(?:["\'])?menu(?:["\' >])')
        self.assertRegex(breadcrumb, r'\baria-expanded=(?:["\'])?false(?:["\' >])')
        self.assertRegex(breadcrumb, r'\bvalue=(?:["\'])?zh-CN(?:["\' >])')
        self.assertRegex(breadcrumb, r'\bvalue=(?:["\'])?en(?:["\' >])')
        self.assertNotRegex(self._book_html(), r'\bid=(?:["\'])?localeSelect(?:["\' >])')
        self.assertNotRegex(self._chapter_html(), r'\bid=(?:["\'])?localeSelect(?:["\' >])')
        self.assertRegex(library, r'localeSelect\.value=i18n\.getLocale\(\)')
        self.assertRegex(library, r'localeSelect\.addEventListener\(["\'`]change')
        self.assertRegex(library, r'i18n\.setLocale\(localeSelect\.value\)')
        self.assertRegex(library, r'localeMenu\.className=["\'`]theme-menu locale-menu["\'`]')
        self.assertRegex(library, r'item\.setAttribute\(["\'`]role["\'`],["\'`]menuitemradio["\'`]\)')
        self.assertRegex(library, r'item\.setAttribute\(["\'`]aria-checked["\'`]')

    def test_locale_action_is_a_compact_icon_control(self):
        library = self._library_html()
        nav = re.search(
            r'<nav\b[^>]*\bclass=(?:["\'])?app-nav[^>]*>.*?</nav>',
            library,
            re.S,
        ).group(0)
        toggle = re.search(
            r'<button\b(?=[^>]*\bid=(?:["\'])?localeToggle(?:["\' >]))[^>]*>(.*?)</button>',
            nav,
            re.S,
        ).group(1)

        self.assertRegex(toggle, r'\bclass=(?:["\'])?fas fa-globe(?:["\'])?')
        self.assertRegex(
            toggle,
            r'<span\b(?=[^>]*\bid=(?:["\'])?localeCurrentLabel(?:["\' >]))'
            r'(?=[^>]*\bclass=(?:["\'])?sr-only(?:["\' >]))[^>]*>',
        )
        self.assertNotIn('app-nav-menu-chevron', toggle)

        css = Path('epub_browser/assets/breadcrumb.css').read_text(encoding='utf-8')
        locale_rules = css[
            css.index('.app-nav .app-nav-locale-toggle {'):
            css.index('}', css.index('.app-nav .app-nav-locale-toggle {'))
        ]
        self.assertIn('width: 44px;', locale_rules)
        self.assertIn('height: 44px;', locale_rules)
        self.assertIn('padding: 0;', locale_rules)
        self.assertNotIn('.app-nav-locale-toggle > .fa-globe', css)

    def test_desktop_floating_controls_only_keep_scroll_to_top(self):
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            floating = re.search(r'class=(?:["\'])?reading-controls(?:["\' >])', html)
            self.assertIsNotNone(floating)
            self.assertGreater(html.index('scrollToTopBtn'), floating.start())
            self.assertLess(html.index('bookshelfBtn'), floating.start())

        chapter = self._chapter_html()
        chapter_floating = re.search(r'class=(?:["\'])?reading-controls(?:["\' >])', chapter)
        self.assertLess(chapter.index('settingsControlBtn'), chapter_floating.start())

        self.assertIn('reader-toolbar top-controls chapter-tools', chapter)
        toolbar = chapter[chapter.index('reader-toolbar top-controls chapter-tools'):]
        toolbar = toolbar[:toolbar.index('</div>')]
        for control_id in ('bookHomeToggle', 'tocToggle', 'settingsControlBtn'):
            self.assertIn(control_id, toolbar)
        self.assertNotIn('togglePagination', toolbar)

        css = Path('epub_browser/assets/breadcrumb.css').read_text(encoding='utf-8')
        self.assertIn('.reader-toolbar.top-controls {', css)
        self.assertIn('position: fixed;', css)
        self.assertIn('transform: translateY(-50%);', css)
        self.assertIn('body.reader-drawer-open .reader-toolbar.top-controls', css)
        self.assertIn('#scrollToTopBtn.is-visible', css)

    def test_primary_navigation_is_stable_and_consistent_across_reader_pages(self):
        pages = (self._library_html(), self._book_html(), self._chapter_html())
        for html in pages:
            match = re.search(r'<nav\b[^>]*\bclass=(?:["\'])?app-nav[^>]*>.*?</nav>', html, re.S)
            self.assertIsNotNone(match)
            nav = match.group(0)
            self.assertRegex(nav, r'\bid=(?:["\'])?bookshelfBtn(?:["\' >])')
            shelf = re.search(r'<button\b[^>]*\bid=(?:["\'])?bookshelfBtn(?:["\' >])[^>]*>', nav)
            self.assertIsNotNone(shelf)
            self.assertNotRegex(shelf.group(0), r'\bstyle=(?:["\'])?display:\s*none')
            self.assertRegex(nav, r'data-annotation-hub')
            self.assertRegex(nav, r'class=(?:["\'])?app-nav-brand')
            self.assertRegex(nav, r'class=(?:["\'])?app-nav-brand[^>]*\bhref=(?:["\'])?/(?:["\' >])')
            self.assertNotRegex(nav, r'class=(?:["\'])?app-nav-link[^>]*\bhref=(?:["\'])?/(?:["\' >])')
            self.assertNotRegex(nav, r'\bclass=(?:["\'])?[^"\']*\bis-active\b')
            self.assertNotRegex(nav, r'\baria-current=')
            self.assertNotRegex(nav, r'data-i18n=(?:["\'])?reader\.book(?:["\'])?')

        for asset in ('library.js', 'book.js', 'chapter.js'):
            script = Path('epub_browser/assets', asset).read_text(encoding='utf-8')
            self.assertNotIn("bookshelfBtn.style.display = ''", script)

    def test_reader_chapter_navigation_uses_one_accessible_drawer_system(self):
        chapter = self._chapter_html()
        chapter_js = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')
        chapter_css = Path('epub_browser/assets/chapter.css').read_text(encoding='utf-8')

        for panel_id in ('bookHomeFloating', 'tocFloating'):
            panel = re.search(
                rf'<nav\b[^>]*\bid=(?:["\'])?{panel_id}(?:["\' >])[^>]*>',
                chapter,
            )
            self.assertIsNotNone(panel)
            self.assertRegex(panel.group(0), r'\bclass=(?:["\'])?[^"\']*\breader-drawer\b')
            self.assertRegex(panel.group(0), r'\baria-hidden=(?:["\'])?true(?:["\' >])')

        self.assertRegex(chapter, r'\bid=(?:["\'])?readerDrawerBackdrop(?:["\' >])')
        self.assertRegex(chapter, r'\bid=(?:["\'])?bookHomeToggle[^>]*\baria-controls=(?:["\'])?bookHomeFloating')
        self.assertRegex(chapter, r'\bid=(?:["\'])?tocToggle[^>]*\baria-controls=(?:["\'])?tocFloating')
        self.assertIn('function openReaderDrawer(', chapter_js)
        self.assertIn('function closeReaderDrawers(', chapter_js)
        self.assertIn("readerDrawerBackdrop.addEventListener('click'", chapter_js)
        self.assertIn("event.key === 'Escape'", chapter_js)
        self.assertIn('.reader-drawer-backdrop.is-active', chapter_css)
        self.assertIn('transform: translateX(calc(100% + 42px));', chapter_css)
        self.assertIn('body.reader-drawer-open', chapter_css)

    def test_continuous_reader_disables_the_chapter_local_toc(self):
        chapter = self._chapter_html()
        chapter_js = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')

        mobile_toc = re.search(
            r'<button\b[^>]*\bid=(?:["\'])?mobileTocBtn(?:["\' >])[^>]*>',
            chapter,
        )
        self.assertIsNotNone(mobile_toc)
        self.assertIn('syncChapterTocAvailability(document, isContinuousScroll)', chapter_js)
        self.assertRegex(chapter, r'/assets/immutable/reader-layout\.[0-9a-f]{12}\.js')

    def test_reader_settings_offer_four_responsive_page_widths(self):
        chapter = self._chapter_html()
        chapter_css = Path('epub_browser/assets/chapter.css').read_text(encoding='utf-8')
        reading_tab = chapter[chapter.index('id="reading-tab"'):]

        self.assertRegex(
            reading_tab,
            r'id="pageWidthSlider"[^>]+min="1"[^>]+max="4"[^>]+value="3"',
        )
        self.assertNotIn('id="pageWidthValue"', reading_tab)
        self.assertNotIn('<output', reading_tab)
        for key in (
            'settings.pageWidth',
            'settings.pageWidthNarrow',
            'settings.pageWidthComfortable',
            'settings.pageWidthWide',
            'settings.pageWidthExtraWide',
        ):
            self.assertIn(f'data-i18n="{key}"', reading_tab)
        self.assertIn('max-width: var(--reader-page-width, 1000px);', chapter_css)
        self.assertIn('updatePageWidth(pageWidthPreset, false);', Path(
            'epub_browser/assets/chapter.js'
        ).read_text(encoding='utf-8'))

    def test_reader_settings_use_the_same_glass_slide_in_drawer_language(self):
        chapter = self._chapter_html()
        chapter_css = Path('epub_browser/assets/chapter.css').read_text(encoding='utf-8')
        chapter_js = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')
        modal = re.search(
            r'<div\b(?=[^>]*\bid=(?:["\'])?settingsModal(?:["\' >]))[^>]*>',
            chapter,
        ).group(0)

        self.assertRegex(modal, r'\brole=(?:["\'])?dialog(?:["\' >])')
        self.assertRegex(modal, r'\baria-modal=(?:["\'])?true(?:["\' >])')
        self.assertRegex(modal, r'\baria-hidden=(?:["\'])?true(?:["\' >])')
        for control_id in ('settingsControlBtn', 'mobileSettingsBtn'):
            control = re.search(
                rf'<button\b(?=[^>]*\bid=(?:["\'])?{control_id}(?:["\' >]))[^>]*>',
                chapter,
            ).group(0)
            self.assertRegex(control, r'\baria-controls=(?:["\'])?settingsModal')
            self.assertRegex(control, r'\baria-expanded=(?:["\'])?false')

        settings_rules = chapter_css[
            chapter_css.index('.settings-modal {'):
            chapter_css.index('}', chapter_css.index('.settings-modal {'))
        ]
        self.assertIn('top: 84px;', settings_rules)
        self.assertIn('right: 18px;', settings_rules)
        self.assertIn('bottom: 18px;', settings_rules)
        self.assertIn('transform: translateX(calc(100% + 42px));', settings_rules)
        self.assertIn('backdrop-filter: blur(18px) saturate(130%);', settings_rules)
        self.assertNotIn('translate(-50%, -50%)', settings_rules)
        self.assertIn("settingsModal.setAttribute('aria-hidden', 'false')", chapter_js)
        self.assertIn('settingsOpener.focus()', chapter_js)

    def test_scroll_reader_uses_a_compact_book_level_navigation_bar(self):
        chapter = self._chapter_html()
        chapter_css = Path('epub_browser/assets/chapter.css').read_text(encoding='utf-8')

        home = re.search(
            r'<a\b[^>]*\bid=(?:["\'])?navigationHomeBtn(?:["\' >])[^>]*>',
            chapter,
        )
        self.assertIsNotNone(home)
        self.assertRegex(home.group(0), r'\bhref=(?:["\'])?/book/[^ >]+/index\.html')
        self.assertRegex(home.group(0), r'data-i18n-aria-label=(?:["\'])?reader\.book')
        self.assertIn('body:not(.pagination-mode) .navigation {', chapter_css)
        self.assertIn('width: min(100%, 520px);', chapter_css)
        self.assertIn('body:not(.pagination-mode) .navigation .control-btn', chapter_css)
        self.assertIn('flex-direction: row;', chapter_css)

    def test_theme_action_is_a_compact_icon_control(self):
        css = Path('epub_browser/assets/breadcrumb.css').read_text(encoding='utf-8')
        theme_rules = css[css.index('.app-nav .app-nav-theme {'):css.index('}', css.index('.app-nav .app-nav-theme {'))]
        self.assertIn('width: 44px;', theme_rules)
        self.assertIn('height: 44px;', theme_rules)
        self.assertIn('padding: 0;', theme_rules)
        self.assertIn('flex-direction: row;', theme_rules)
        self.assertIn('.app-nav .app-nav-theme .app-nav-action-label', css)

    def test_shared_navigation_keeps_touch_targets_at_least_44_pixels(self):
        css = Path('epub_browser/assets/breadcrumb.css').read_text(encoding='utf-8')
        action_rules = css[
            css.index('.app-nav-link,\n.app-nav-action {'):
            css.index('}', css.index('.app-nav-link,\n.app-nav-action {'))
        ]
        brand_rules = css[
            css.index('.app-nav-brand {'):
            css.index('}', css.index('.app-nav-brand {'))
        ]
        locale_rules = css[
            css.index('.app-nav .app-nav-locale-toggle {'):
            css.index('}', css.index('.app-nav .app-nav-locale-toggle {'))
        ]
        compact_rules = css.split('@media (max-width: 940px)', 1)[1]
        compact_rules = compact_rules.split('@media (max-width: 768px)', 1)[0]
        mobile_rules = css.split('@media (max-width: 768px)', 1)[1]
        mobile_rules = mobile_rules.split('@media (max-width: 430px)', 1)[0]

        self.assertIn('min-height: 44px;', brand_rules)
        self.assertIn('min-height: 44px;', action_rules)
        self.assertIn('min-height: 44px;', locale_rules)
        self.assertRegex(
            compact_rules,
            r'\.app-nav-action,[^}]*width:\s*44px;',
        )
        self.assertRegex(
            mobile_rules,
            r'\.app-nav-brand\s*\{[^}]*min-height:\s*44px;',
        )

    def test_scroll_to_top_visibility_is_driven_by_scroll_state(self):
        css = Path('epub_browser/assets/breadcrumb.css').read_text(encoding='utf-8')
        self.assertIn('opacity: 0;', css)
        self.assertIn('#scrollToTopBtn.is-visible', css)
        for asset in ('library.js', 'book.js', 'chapter.js'):
            script = Path('epub_browser/assets', asset).read_text(encoding='utf-8')
            self.assertIn('function updateScrollToTopVisibility()', script)
            self.assertIn("classList.add('is-visible')", script)
            self.assertIn("classList.remove('is-visible')", script)

    def test_ssg_install_action_is_part_of_navigation_not_floating_controls(self):
        html = self._library_html()
        nav = html[html.index('<nav'):html.index('</nav>')]
        self.assertIn('id=pwa-install-btn', nav)
        script = Path('epub_browser/assets/library.js').read_text(encoding='utf-8')
        self.assertIn("getElementById('pwa-install-btn')", script)
        self.assertNotIn('readingControls.appendChild(installBtn)', script)

    def test_library_book_and_chapter_open_annotation_center_as_a_modal(self):
        library_html = self._library_html()
        book_html = self._book_html()
        chapter_html = self._chapter_html()

        self.assertRegex(library_html, r'\bid=(?:["\'])?annotationsBtn')
        self.assertRegex(library_html, r'\bdata-annotation-hub')
        self.assertNotRegex(library_html, r'\bdata-ai-reading-hub')
        self.assertIn('aria-haspopup=dialog', library_html)
        self.assertRegex(library_html, r'/assets/immutable/annotation\.[0-9a-f]{12}\.js')
        self.assertRegex(library_html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.js')
        self.assertNotRegex(library_html, r'ai-reading-hub\.[0-9a-f]{12}\.(?:css|js)')
        self.assertNotIn('/annotations/index.html', library_html)
        self.assertRegex(book_html, r'\bid=(?:["\'])?bookAnnotationsBtn')
        self.assertRegex(book_html, r'\bdata-book-hash=')
        self.assertIn('aria-haspopup=dialog', book_html)
        self.assertRegex(book_html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.css')
        self.assertRegex(chapter_html, r'\bid=(?:["\'])?chapterAnnotationsBtn')
        self.assertRegex(chapter_html, r'\bdata-book-hash=')
        self.assertRegex(chapter_html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.css')
        self.assertRegex(chapter_html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.js')
        self.assertRegex(chapter_html, r'<article[^>]+id="eb-content"[^>]+data-chapter-title=')

        server_html = self._server_html()
        self.assertRegex(server_html, r'\bdata-ai-reading-hub')
        self.assertRegex(server_html, r'/assets/immutable/ai-reading-hub\.[0-9a-f]{12}\.css')
        self.assertRegex(server_html, r'/assets/immutable/ai-reading-hub\.[0-9a-f]{12}\.js')

    def test_annotation_modal_assets_are_immutable_and_not_a_separate_page(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            library.create_library_home()
            html = Path(directory, 'index.html').read_text(encoding='utf-8')
            self.assertFalse(Path(directory, 'annotations', 'index.html').exists())

        self.assertRegex(html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.js')
        self.assertRegex(html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.css')

    def test_annotation_modal_keeps_keyboard_and_scroll_return_paths(self):
        script = Path("epub_browser/assets/annotation-hub.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation-hub.css").read_text(encoding="utf-8")

        self.assertIn("modal.setAttribute('role', 'dialog')", script)
        self.assertIn("modal.setAttribute('aria-modal', 'true')", script)
        self.assertIn("if (event.key === 'Escape')", script)
        self.assertIn("document.body.classList.add('annotation-hub-open')", script)
        self.assertIn("modalState.opener.focus()", script)
        self.assertIn('.annotation-hub-header-button[hidden] { display: none; }', css)
        self.assertIn('grid-column: 3;', css)

    def test_annotation_modal_announces_loading_while_data_is_requested(self):
        script = Path("epub_browser/assets/annotation-hub.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation-hub.css").read_text(encoding="utf-8")

        self.assertIn('function renderLoading()', script)
        self.assertIn("container.setAttribute('aria-busy', 'true');", script)
        self.assertIn("loading.setAttribute('role', 'status');", script)
        self.assertIn('renderLoading();', script)
        self.assertIn('.annotation-hub-spinner', css)
        self.assertIn('@keyframes annotation-hub-spin', css)
        self.assertIn('.annotation-hub-spinner { animation: none;', css)

    def test_annotation_hub_routes_state_copy_through_i18n(self):
        script = Path("epub_browser/assets/annotation-hub.js").read_text(encoding="utf-8")

        self.assertIn("function tr(key, params)", script)
        self.assertIn("tr('loading')", script)
        self.assertIn("tr('loadHubFailed')", script)
        self.assertIn("tr('noAnnotationsTitle')", script)
        self.assertIn("tr('noBookAnnotationsTitle')", script)
        self.assertIn('function translateChrome()', script)
        self.assertIn('function renderCurrentView()', script)
        self.assertIn('i18n().onLocaleChange(function()', script)
        self.assertNotIn("'Unable to load annotations'", script)
        self.assertNotIn("'Please try again.'", script)
        self.assertNotIn("'No annotations yet'", script)
        self.assertNotIn("'No annotations in this book'", script)

    def test_annotation_hub_offers_accessible_confirmed_deletion(self):
        script = Path("epub_browser/assets/annotation-hub.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation-hub.css").read_text(encoding="utf-8")

        self.assertIn("element('button', 'annotation-card-delete'", script)
        self.assertIn("deleteButton.setAttribute('aria-label', tr('deleteAnnotation'))", script)
        self.assertIn("root.EpubDialog.confirm({", script)
        self.assertIn("destructive: true", script)
        self.assertIn("root.AnnotationStorage.delete(annotation.id)", script)
        self.assertIn("notify('deleted', 'success')", script)
        self.assertIn('.annotation-card-delete:focus-visible', css)
        self.assertIn('.annotation-card-row:hover .annotation-card-delete', css)
        self.assertIn('@media (hover: none), (pointer: coarse)', css)
        self.assertIn('@media (max-width: 600px)', css)

    def test_chapter_puts_custom_css_in_the_reading_settings_tab(self):
        html = self._chapter_html()

        reading_tab_start = html.index('id="reading-tab"')
        editor_start = html.index('id="customCssInput"')
        self.assertGreater(editor_start, reading_tab_start)
        self.assertIn('Custom styles', html)
        self.assertIn('Optional', html)
        self.assertNotIn('Reading appearance (advanced)', html)
        self.assertNotIn('id="cssPanelToggle"', html)

    def test_reader_template_marks_static_ui_and_preserves_chapter_content(self):
        html = self._chapter_html()

        for key in (
            'reader.thisChapterContents', 'reader.previous', 'reader.next',
            'settings.appearance', 'settings.readingMode', 'settings.paginationMode',
            'settings.customStyles',
        ):
            self.assertIn('data-i18n="' + key + '"', html)
        article = html[html.index('<article'):html.index('</article>')]
        self.assertIn('<p>Text</p>', article)
        self.assertNotIn('data-i18n', article)

    def test_reader_mobile_controls_use_translatable_accessible_labels(self):
        html = self._chapter_html()

        self.assertIn('data-i18n="reader.theme"', html)
        self.assertIn('data-i18n-aria-label="reader.openBookHome"', html)

    def test_ai_reading_controls_use_the_native_canvas_without_extra_book_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor(
                "book.epub", directory, deployment_mode="server"
            )
            processor.book_title = "A Book"
            processor.chapters = [{"title": "One"}]
            chapter = processor.create_chapter_template("<p>Text</p>", "", 0, "One")
        script = Path('epub_browser/assets/ai-canvas.js').read_text(encoding='utf-8')
        stylesheet = Path('epub_browser/assets/ai-canvas.css').read_text(encoding='utf-8')
        chat_script = Path('epub_browser/assets/ai-chat.js').read_text(encoding='utf-8')
        chat_stylesheet = Path('epub_browser/assets/ai-chat.css').read_text(encoding='utf-8')

        self.assertIn('data-ai-learning-canvas', chapter)
        self.assertIn('aria-label="AI reading"', chapter)
        self.assertIn('aria-pressed="false"', chapter)
        self.assertIn('data-i18n-aria-label="ai.chapterRead"', chapter)
        self.assertIn('data-ai-followup-drawer', chapter)
        self.assertIn('data-i18n-aria-label="ai.askChapter"', chapter)
        self.assertIn('data-ai-reading-hub', chapter)
        self.assertRegex(chapter, r'/assets/immutable/ai-reading-hub\.[0-9a-f]{12}\.css')
        self.assertRegex(chapter, r'/assets/immutable/ai-reading-hub\.[0-9a-f]{12}\.js')
        self.assertRegex(chapter, r'/assets/immutable/ai-chat\.[0-9a-f]{12}\.css')
        self.assertRegex(chapter, r'/assets/immutable/ai-chat\.[0-9a-f]{12}\.js')
        self.assertIn("content.annotations", script)
        self.assertIn("range.surroundContents(mark)", script)
        self.assertIn("job.progress_current || 0", script)
        self.assertIn("chapter: context.chapterIndex", script)
        self.assertNotIn("chapter: context.chapterIndex + 1", script)
        self.assertIn("new root.EventSource('/api/ai/events?job_id='", script)
        self.assertIn('.ai-canvas-mark', stylesheet)
        self.assertIn('ai-chapter-guide', script)
        self.assertIn('placeParagraphNote', script)
        self.assertIn('ai-paragraph-note-trigger', script)
        self.assertIn('ai-paragraph-popover-close', script)
        self.assertIn('ai-guide-map-modal', script)
        self.assertIn('ai-guide-map-dialog', script)
        self.assertIn('ai-guide-map-close', script)
        self.assertIn("panel.setAttribute('role', 'dialog')", script)
        self.assertIn("panel.setAttribute('aria-modal', 'true')", script)
        self.assertIn('ai-guide-map-trigger', script)
        self.assertIn('ai-chapter-reflection', script)
        self.assertIn("data-ai-canvas-color', mark.getAttribute", script)
        self.assertIn('diagram_mermaid', script)
        self.assertIn("['mindmap'", script)
        self.assertIn('requestedResultId()', script)
        self.assertIn('item.book_id !== context.bookId', script)
        self.assertIn('current_template_version', script)
        self.assertIn('.ai-paragraph-note-trigger', stylesheet)
        self.assertIn('.ai-paragraph-popover-close', stylesheet)
        self.assertIn('.ai-guide-map-modal', stylesheet)
        self.assertIn('.ai-guide-map-dialog', stylesheet)
        self.assertIn('.ai-chapter-reflection', stylesheet)
        self.assertIn('.ai-canvas-status { position: fixed;', stylesheet)
        self.assertIn("classList.toggle('is-active'", script)
        self.assertIn("setAttribute('aria-pressed'", script)
        self.assertIn("document.body.classList.contains('pagination-mode')", script)
        self.assertIn("ai.unavailableInPagination", script)
        self.assertIn("appendKicker(", script)
        self.assertNotIn("trigger.addEventListener('mouseenter', open)", script)
        self.assertNotIn("mapTrigger.addEventListener('mouseenter', openMap)", script)
        self.assertIn('[data-ai-learning-canvas].is-active', stylesheet)
        self.assertIn('linear-gradient(105deg', stylesheet)
        self.assertNotIn('ai-reading-artifact-surface', script)
        self.assertIn("'/api/ai/books/'", chat_script)
        self.assertIn("{ number: Number(turn.chapter_index) }", chat_script)
        self.assertNotIn("turn.chapter_index) + 1", chat_script)
        self.assertIn("[data-ai-book-chat]", chat_script)
        self.assertIn("'book_overview'", chat_script)
        self.assertIn("new root.EventSource('/api/ai/events?chat_id='", chat_script)
        self.assertIn("context_mode", chat_script)
        self.assertIn("chapterContext(button)", chat_script)
        self.assertIn("function chapterScope(value)", chat_script)
        self.assertIn("function drawerScope(value)", chat_script)
        self.assertIn("ai.askScope", chat_script)
        self.assertIn("ai.chatScope", chat_script)
        self.assertIn("ai_reading_required", chat_script)
        self.assertIn('root.EpubBrowserAIRich.render', chat_script)
        self.assertIn('ai.chatNoReadingTitle', chat_script)
        self.assertIn("'/api/ai/status'", chat_script)
        self.assertIn("ai_disabled", chat_script)
        self.assertIn('.ai-chat-panel', chat_stylesheet)
        self.assertIn('var(--card-bg', chat_stylesheet)
        self.assertIn('var(--button-bg', chat_stylesheet)
        self.assertIn('body.ai-chat-open:not(.pagination-mode) .container', chat_stylesheet)

        Path(processor.web_dir).mkdir(parents=True, exist_ok=True)
        processor.create_index_page()
        book_page = Path(processor.web_dir, 'index.html').read_text(encoding='utf-8')
        self.assertIn('data-ai-reading-hub', book_page)
        self.assertIn('data-ai-book-chat', book_page)
        self.assertIn('data-ai-reading-indicators', book_page)
        self.assertRegex(book_page, r'data-chapter-index(?:="|=)0')
        self.assertRegex(book_page, r'/assets/immutable/ai-reading-hub\.[0-9a-f]{12}\.js')
        book_script = Path('epub_browser/assets/book.js').read_text(encoding='utf-8')
        self.assertIn("/api/books/" + "' + encodeURIComponent(book_hash) + '/metadata", book_script)
        self.assertIn('renderEffectiveBookTags', book_script)
        self.assertIn("titleWithSync.insertBefore(syncTag, aiBadge.nextSibling)", book_script)
        reading_hub_script = Path('epub_browser/assets/ai-reading-hub.js').read_text(encoding='utf-8')
        self.assertIn("function resultGroups(book)", reading_hub_script)
        self.assertIn("function resultTimestamp(result)", reading_hub_script)
        self.assertIn("group.results.sort(function(left, right)", reading_hub_script)
        self.assertIn("Number(left.result.chapter_index) - Number(right.result.chapter_index)", reading_hub_script)
        self.assertIn("{ number: index }", reading_hub_script)
        self.assertNotIn("{ number: index + 1 }", reading_hub_script)
        self.assertIn("function refreshChapterIndicators(node)", reading_hub_script)
        self.assertIn("epub-browser:chapter-toc-loaded", reading_hub_script)
        self.assertIn("method: 'DELETE'", reading_hub_script)
        self.assertIn("titleGroup.insertBefore(badge, syncTag || null)", reading_hub_script)
        self.assertIn("state.back.hidden = !Boolean(state.bookId);", reading_hub_script)
        self.assertIn("?ai_result=' + encodeURIComponent(result.id)", reading_hub_script)
        self.assertIn("ai.libraryGeneratedAt", reading_hub_script)
        chapter_stylesheet = Path('epub_browser/assets/chapter.css').read_text(encoding='utf-8')
        self.assertIn("#bookHomeTocList .toc-item > a > .chapter-title-with-sync > .chapter-title", chapter_stylesheet)
        self.assertIn("requestedResultId()", script)
        self.assertIn("'/api/ai/results/' + encodeURIComponent(requested)", script)
        self.assertNotIn('ai-learning-hub', book_page)
        self.assertNotIn('ai-chat.html', book_page)
        self.assertFalse(Path(processor.web_dir, 'ai-chat.html').exists())

        chapter_script = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')
        annotation_script = Path('epub_browser/assets/annotation-hub.js').read_text(encoding='utf-8')
        self.assertNotIn('nextIdx + 1', chapter_script)
        self.assertNotIn('prevIdx + 1', chapter_script)
        self.assertNotIn('{ number: index + 1 }', annotation_script)
        self.assertIn('epub-browser:chapter-toc-loaded', chapter_script)
        self.assertIn("item.kind === 'section'", chapter_script)
        self.assertIn('var currentVisibleChapter = visibleChapterIndex;', chapter_script)

    def test_ssg_reader_surfaces_do_not_ship_server_only_ai_reading(self):
        forbidden = (
            'data-ai-reading-hub', 'data-ai-learning-canvas',
            'data-ai-followup-drawer', 'data-ai-reading-indicators',
            'ai-canvas', 'ai-chat', 'ai-reading-hub', 'ai-rich-text',
            'katex', 'mermaid',
        )
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            for marker in forbidden:
                self.assertNotIn(marker, html)

        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            self.assertFalse(any(
                logical_path.startswith(('ai-', 'vendor/katex/', 'vendor/mermaid/'))
                for logical_path in library.asset_manifest.assets
            ))

    def test_library_and_chapter_link_the_shared_loading_stylesheet(self):
        self.assertRegex(self._library_html(), r'/assets/immutable/loading\.[0-9a-f]{12}\.css')
        self.assertRegex(self._chapter_html(), r'/assets/immutable/loading\.[0-9a-f]{12}\.css')

    def test_bookshelf_templates_localize_labels_without_translating_business_values(self):
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            self.assertRegex(html, r'data-i18n=(?:["\'])?bookshelf\.addGroup')
            self.assertRegex(html, r'data-i18n=(?:["\'])?bookshelf\.addBook')
            self.assertRegex(html, r'data-i18n=(?:["\'])?bookshelf\.export')
            self.assertRegex(html, r'data-i18n=(?:["\'])?bookshelf\.import')
            self.assertNotIn('id="syncShelfBtn"', html)
            self.assertNotIn('bookshelfTagFilter', html)
            self.assertNotIn('groupTagFilter', html)

    def test_bookshelf_script_routes_user_messages_through_i18n(self):
        script = Path('epub_browser/assets/bookshelf.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")
        self.assertIn("i18n.t('bookshelf.currentStats'", script)

    def test_bookshelf_renders_adversarial_group_and_book_metadata_as_text(self):
        script = Path('epub_browser/assets/bookshelf.js').read_text(encoding='utf-8')

        self.assertIn('titleElement.textContent = group.name;', script)
        self.assertIn('titleElement.textContent = bookInfo.title;', script)
        self.assertIn('authorElement.textContent = bookInfo.author;', script)
        self.assertIn('name.textContent = book.title;', script)
        self.assertIn('pathItem.textContent = name;', script)
        self.assertNotRegex(
            script,
            r'innerHTML\s*=\s*[\s\S]{0,300}(?:group\.name|bookInfo\.(?:title|author))',
        )
