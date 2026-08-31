"""Unit tests for the unified lxml parsing pipeline (epub_parsing.py).

The pipeline is the single entry point for every EPUB XML/XHTML document:
strict-first XML, controlled recovery, structural validation, and a final HTML
parser fallback for legacy EPUB 2 content.  These tests pin down the security
boundaries that the rest of the converter relies on.
"""

import unittest

from lxml import etree

from epub_browser.epub_parsing import (
    EPUBParseError,
    allowed_entity_name,
    is_safe_internal_path,
    parse_xhtml_bytes,
    parse_xhtml_fragment,
    parse_xml_bytes,
    require_single_rootfile,
    validate_manifest_ids,
    validate_spine_references,
)


class ParseXmlBytesTests(unittest.TestCase):
    def test_parses_well_formed_xml_strictly(self):
        root = parse_xml_bytes(b"<package version='3.0'/>")
        self.assertEqual(etree.QName(root).localname, "package")

    def test_does_not_expand_entities_so_xxe_carries_no_file_access(self):
        # A doctype declaring a local entity is the classic XXE carrier.  The
        # parser must keep it inert: the entity node survives unexpanded and
        # is not on the allowlist for sanitized output.
        data = (
            b'<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b"<root>&xxe;</root>"
        )
        root = parse_xml_bytes(data)
        names = [
            getattr(child, "name", None)
            for child in root
            if getattr(child, "name", None)
        ]
        self.assertEqual(names, ["xxe"])
        self.assertFalse(allowed_entity_name("xxe"))
        self.assertTrue(allowed_entity_name("nbsp"))

    def test_standard_entities_are_allowed_in_sanitized_output(self):
        for name in ("amp", "lt", "gt", "quot", "apos", "nbsp", "mdash"):
            self.assertTrue(allowed_entity_name(name), name)


class RequireSingleRootfileTests(unittest.TestCase):
    @staticmethod
    def _container(full_paths):
        rootfiles = "".join(
            (
                f'<rootfile full-path="{path}"'
                ' media-type="application/oebps-package+xml"/>'
            )
            for path in full_paths
        )
        return parse_xml_bytes(
            (
                '<container xmlns="urn:oasis:names:tc:opendocument:'
                'xmlns:container"><rootfiles>'
                + rootfiles
                + "</rootfiles></container>"
            ).encode()
        )

    def test_single_rootfile_is_returned(self):
        root = self._container(["OEBPS/content.opf"])
        self.assertEqual(require_single_rootfile(root), "OEBPS/content.opf")

    def test_missing_rootfile_is_rejected(self):
        root = parse_xml_bytes(b"<container><rootfiles/></container>")
        with self.assertRaises(EPUBParseError):
            require_single_rootfile(root)

    def test_ambiguous_multiple_rootfiles_are_rejected(self):
        root = self._container(["OEBPS/a.opf", "OEBPS/b.opf"])
        with self.assertRaisesRegex(EPUBParseError, "multiple rootfiles"):
            require_single_rootfile(root)

    def test_rootfile_escaping_the_archive_is_rejected(self):
        root = self._container(["../outside.opf"])
        with self.assertRaisesRegex(EPUBParseError, "unsafe"):
            require_single_rootfile(root)


class ManifestAndSpineValidationTests(unittest.TestCase):
    @staticmethod
    def _item(item_id):
        element = etree.Element("item")
        if item_id is not None:
            element.set("id", item_id)
        return element

    def test_missing_manifest_id_is_rejected(self):
        with self.assertRaisesRegex(EPUBParseError, "missing its id"):
            validate_manifest_ids([self._item("a"), self._item(None)])

    def test_duplicate_manifest_id_is_rejected(self):
        with self.assertRaisesRegex(EPUBParseError, "duplicate id"):
            validate_manifest_ids([self._item("a"), self._item("a")])

    def test_spine_reference_to_undeclared_id_is_rejected(self):
        with self.assertRaisesRegex(EPUBParseError, "undeclared manifest ids"):
            validate_spine_references(["a", "ghost", "b"], {"a", "b"})

    def test_valid_spine_references_pass_through_in_order(self):
        self.assertEqual(
            validate_spine_references(["b", "a", None, " "], {"a", "b"}),
            ("b", "a"),
        )


class SafeInternalPathTests(unittest.TestCase):
    def test_accepts_plain_internal_relative_paths(self):
        for path in ("OEBPS/ch1.xhtml", "text/1.xhtml", "images/a.png"):
            self.assertTrue(is_safe_internal_path(path), path)

    def test_rejects_external_and_absolute_references(self):
        for path in (
            "https://attacker.example/x",
            "file:///etc/passwd",
            "/absolute/path",
            "OEBPS/../outside",
            "a%2F..%2Fb",
            "a\\\\b",
            "a\x00b",
        ):
            self.assertFalse(is_safe_internal_path(path), path)


class ParseXhtmlFragmentTests(unittest.TestCase):
    def test_multi_sibling_fragment_is_not_truncated_by_xml_recovery(self):
        # The XML parser must not silently keep only the first sibling; the
        # HTML fallback wraps and preserves every node.
        nodes = parse_xhtml_fragment("<p>a</p><p>b</p>")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(etree.QName(nodes[0]).localname, "html")
        body = nodes[0].find("body")
        self.assertEqual(
            [etree.QName(child).localname for child in body], ["p", "p"]
        )

    def test_plain_text_fragment_parses(self):
        nodes = parse_xhtml_fragment("just text")
        self.assertEqual(len(nodes), 1)

    def test_legacy_html_with_unclosed_void_tags_parses(self):
        nodes = parse_xhtml_fragment('<link rel="stylesheet"><p>Hi</p>')
        self.assertEqual(len(nodes), 1)

    def test_utf8_punctuation_survives_the_html_fallback(self):
        # The HTML fallback must not decode UTF-8 bytes as latin-1: a smart
        # quote used to come back as the mojibake ``â\x80\x99``.
        nodes = parse_xhtml_fragment("Don\u2019t ban \u2014 ok")
        body = nodes[0].find("body")
        self.assertIn("\u2019", body.text_content())
        self.assertNotIn("\u00e2", body.text_content())

    def test_html_fallback_bytes_default_to_utf8(self):
        nodes = parse_xhtml_bytes("Brazil\u2019s economy".encode("utf-8"))
        self.assertEqual(nodes.text_content(), "Brazil\u2019s economy")

    def test_html_fallback_bytes_honor_meta_charset(self):
        # A non-UTF-8 document declaration must still win over the UTF-8
        # fallback; 0xE9 is ``é`` in windows-1252.
        data = (
            b'<html><head><meta charset="windows-1252"></head>'
            b"<body><p>\xe9</p></body></html>"
        )
        root = parse_xhtml_bytes(data)
        self.assertEqual(root.text_content(), "\u00e9")


if __name__ == "__main__":
    unittest.main()
