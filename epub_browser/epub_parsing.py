"""Unified lxml parsing for EPUB XML and XHTML documents.

Every EPUB document -- container, OPF, NCX, navigation and chapter XHTML --
is parsed through this module, so malformed input is handled once, in one
place, and no parser is ever allowed to load external entities or DTDs.

The policy is strict-first.  A document is parsed with recovery disabled; only
an outright failure retries with recovery enabled.  XHTML that still cannot be
parsed as XML falls back to :mod:`lxml.html`, the only parser able to cope with
legacy EPUB 2 content that predates XHTML.

The book identity byte-writer (:mod:`epub_browser.epub_identity`) is
deliberately outside this module.  It uses Expat's ``CurrentByteIndex`` to
patch a few bytes of the OPF without re-serialising the document, and must keep
that dedicated locator.
"""

import codecs
import re
import urllib.parse
from html.entities import html5
from pathlib import Path, PurePosixPath

from lxml import etree, html as lxml_html


__all__ = [
    "EPUBParseError",
    "parse_xml_bytes",
    "parse_xml_document",
    "parse_xhtml_bytes",
    "parse_xhtml_document",
    "local_name",
    "iter_local",
    "find_local",
    "findall_local",
    "find_descendant_local",
    "element_text",
    "entity_reference_name",
    "allowed_entity_name",
    "decode_html_bytes",
    "require_single_rootfile",
    "validate_manifest_ids",
    "validate_spine_references",
    "is_safe_internal_path",
]


class EPUBParseError(Exception):
    """Raised when an EPUB document cannot be parsed, even with recovery.

    This deliberately does not derive from :class:`ValueError`.  Callers treat
    a ``ValueError`` as an unsafe EPUB path that must abort the conversion,
    while an unparsable document degrades to the next available source (an
    empty table of contents, the NCX fallback, and so on).
    """


# Entities an untrusted EPUB may legitimately use.  Anything else (in
# particular a locally declared entity such as ``&xxe;``) is dropped instead of
# being carried into the output, where a lenient parser might expand it.
_ALLOWED_ENTITY_NAMES = frozenset(
    name[:-1] for name in html5 if name.endswith(";")
)


def _xml_parser(recover):
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        huge_tree=False,
        recover=recover,
    )


def _html_parser():
    return lxml_html.HTMLParser(recover=True, no_network=True, huge_tree=False)


def _strip_xml_declaration(text):
    """Drop a leading ``<?xml ...?>`` so the HTML fallback accepts ``str``.

    lxml's ``fromstring`` refuses ``str`` input that carries an encoding
    declaration -- the encoding has already been decoded, so the declaration
    is meaningless -- and raises ``ValueError`` before the HTML parser runs.
    """
    if text.startswith("<?xml"):
        end = text.find("?>")
        if end != -1:
            text = text[end + 2:].lstrip()
    return text


def decode_html_bytes(data):
    """Decode bytes into str for HTML content, never failing.

    lxml's HTML parser decodes input whose encoding it cannot detect as
    latin-1, which garbles the UTF-8 content EPUB mandates (a smart quote
    becomes ``â\x80\x99``).  Decode explicitly instead -- a BOM wins, then a
    meta charset declaration, then UTF-8 -- and hand the parser ``str`` so no
    byte-guessing happens downstream.  Sloppy real-world EPUBs ship chapters
    in GB18030/GBK (exported by Chinese tools) without a usable declaration;
    rather than failing a chapter that every reader shows, fall back through
    the legacy encodings and finally replacement characters.  Plain text
    decoding is inert, so none of these paths can execute or load anything.
    """
    if isinstance(data, str):
        return _strip_xml_declaration(data)
    for bom, encoding, width in (
        (codecs.BOM_UTF32_LE, "utf-32-le", 4),
        (codecs.BOM_UTF32_BE, "utf-32-be", 4),
        (codecs.BOM_UTF16_LE, "utf-16-le", 2),
        (codecs.BOM_UTF16_BE, "utf-16-be", 2),
        (codecs.BOM_UTF8, "utf-8", 3),
    ):
        if data.startswith(bom):
            return _strip_xml_declaration(data[width:].decode(encoding))
    match = re.search(
        br'charset\s*=\s*["\']?([A-Za-z0-9._-]+)',
        data[:4096],
        re.IGNORECASE,
    )
    if match:
        encoding = match.group(1).decode("ascii", "ignore")
        try:
            return _strip_xml_declaration(data.decode(encoding))
        except (LookupError, UnicodeDecodeError, ValueError):
            pass
    try:
        return _strip_xml_declaration(data.decode("utf-8"))
    except UnicodeDecodeError:
        for encoding in ("gb18030", "latin-1"):
            try:
                return _strip_xml_declaration(data.decode(encoding))
            except UnicodeDecodeError:
                continue
        return _strip_xml_declaration(data.decode("utf-8", errors="replace"))


def parse_xml_bytes(data, *, allow_recovery=True):
    """Parse XML bytes strictly, falling back to recovery on failure."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    for recover in ((False, True) if allow_recovery else (False,)):
        try:
            root = etree.fromstring(data, _xml_parser(recover))
        except etree.XMLSyntaxError as error:
            failure = error
            continue
        except ValueError as error:
            # lxml raises ValueError for empty or non-XML input.
            raise EPUBParseError(str(error) or "Unparsable XML document") from error
        if root is not None:
            return root
        # Recovery abandoned the document entirely; retrying never helps.
        raise EPUBParseError("Unparsable XML document: no root element")
    raise EPUBParseError(f"Unparsable XML document: {failure}") from failure


def parse_xml_document(path, *, allow_recovery=True):
    """Parse an XML file from disk strictly, then with recovery."""
    for recover in ((False, True) if allow_recovery else (False,)):
        try:
            return etree.parse(str(path), _xml_parser(recover)).getroot()
        except etree.XMLSyntaxError as error:
            failure = error
        except OSError:
            raise
    raise EPUBParseError(
        f"Unparsable XML document {path}: {failure}"
    ) from failure


def parse_xhtml_bytes(data):
    """Parse an XHTML document, falling back to the HTML parser.

    XHTML goes through strict XML first.  It does not use XML recovery:
    recovery silently keeps only the first root when a fragment has several
    siblings, dropping chapter content.  The HTML parser handles malformed
    markup, void elements and multi-sibling fragments without losing nodes.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        return parse_xml_bytes(data, allow_recovery=False)
    except EPUBParseError:
        pass
    try:
        return lxml_html.document_fromstring(
            decode_html_bytes(data), parser=_html_parser()
        )
    except (etree.ParserError, etree.XMLSyntaxError) as error:
        raise EPUBParseError(f"Unparsable XHTML document: {error}") from error


def parse_xhtml_document(path):
    """Parse an XHTML file, falling back to the HTML parser.

    The file is read once.  Legacy EPUB 2 chapters are not strict XML, so the
    strict attempt fails and the same bytes feed the HTML fallback; reading
    the file twice on that path is pure waste for such books.
    """
    data = Path(path).read_bytes()
    try:
        return parse_xml_bytes(data, allow_recovery=False)
    except EPUBParseError:
        pass
    try:
        return lxml_html.document_fromstring(
            decode_html_bytes(data), parser=_html_parser()
        )
    except (etree.ParserError, etree.XMLSyntaxError) as error:
        raise EPUBParseError(
            f"Unparsable XHTML document {path}: {error}"
        ) from error


def parse_xhtml_fragment(data):
    """Return the root node of an XHTML fragment or document.

    A chapter body is a fragment with any number of siblings, which XML cannot
    represent as one document.  Such content -- and only such content -- is
    handed to the HTML parser, which wraps the siblings in ``html``/``body``.
    Callers unwrap that wrapper before rendering.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        return [parse_xml_bytes(data, allow_recovery=False)]
    except EPUBParseError:
        pass
    try:
        return [
            lxml_html.document_fromstring(
                decode_html_bytes(data), parser=_html_parser()
            )
        ]
    except (etree.ParserError, etree.XMLSyntaxError) as error:
        raise EPUBParseError(f"Unparsable XHTML fragment: {error}") from error


def local_name(tag):
    """Return an element's tag without its namespace, prefix, or comments."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def iter_local(root, name):
    """Iterate every descendant whose local name matches, namespace-agnostic."""
    for element in root.iter():
        if local_name(element.tag) == name:
            yield element


def find_local(element, name):
    """Return the first direct child with the given local name."""
    return next(
        (child for child in element if local_name(child.tag) == name), None
    )


def findall_local(element, name):
    """Return every direct child with the given local name."""
    return [child for child in element if local_name(child.tag) == name]


def find_descendant_local(element, name):
    """Return the first descendant with the given local name."""
    return next(iter_local(element, name), None)


def element_text(element):
    """Return an element's own display text, or None when it has none."""
    if element is None:
        return None
    text = element.text
    if not isinstance(text, str) or not text.strip():
        return None
    return text


def entity_reference_name(node):
    """Return the name of an lxml entity reference node, if it is one."""
    name = getattr(node, "name", None)
    if isinstance(name, str) and name:
        return name
    return None


def allowed_entity_name(name):
    """Report whether an entity may be carried into sanitized output."""
    if not isinstance(name, str) or not name:
        return False
    return name in _ALLOWED_ENTITY_NAMES


def require_single_rootfile(root):
    """Return the container's rootfile ``full-path``.

    A container that declares several distinct rootfiles is technically
    ambiguous, but real-world EPUBs occasionally repeat a rendition
    declaration.  Mainstream readers take the first usable one, so this does
    the same instead of rejecting the whole book.
    """
    candidates = []
    for element in iter_local(root, "rootfile"):
        full_path = element.get("full-path")
        if not isinstance(full_path, str) or not full_path.strip():
            continue
        media_type = element.get("media-type")
        if (
            isinstance(media_type, str)
            and media_type.strip().casefold() != "application/oebps-package+xml"
        ):
            continue
        candidates.append(full_path.strip())
    if not candidates:
        raise EPUBParseError("container.xml declares no OEBPS rootfile")
    full_path = candidates[0]
    if not is_safe_internal_path(full_path):
        raise EPUBParseError(
            f"container.xml declares an unsafe rootfile path: {full_path}"
        )
    return full_path


def validate_manifest_ids(items):
    """Validate manifest ids, returning the first occurrence of each id.

    A missing id is common in sloppy real-world EPUBs and never addressable by
    a spine ``idref``, so the item is skipped rather than failing the whole
    book: losing one unreferenced resource declaration costs far less than
    refusing content every mainstream reader accepts.  A duplicated id (a
    repeated declaration, usually of the same ``href``) is likewise accepted:
    the first occurrence wins and later ones are dropped, so a spine ``idref``
    always binds deterministically.
    """
    seen = set()
    ordered = []
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        ordered.append(item_id)
    return ordered


def validate_spine_references(idrefs, manifest_ids):
    """Filter a spine to the manifest ids it actually declares.

    A spine ``idref`` for an undeclared manifest id cannot be bound to any
    resource, but dropping it -- rather than rejecting the whole book -- is
    the behavior mainstream readers use: such references are usually leftover
    ``toc`` entries or publisher mistakes, and the remaining, resolvable
    chapters still form a consistent reading sequence.  Skipping the dangling
    reference never binds content to the wrong resource.
    """
    return tuple(
        idref
        for idref in idrefs
        if isinstance(idref, str) and idref.strip() and idref in manifest_ids
    )


def is_safe_internal_path(reference):
    """Report whether an EPUB-internal reference stays inside the archive."""
    if not isinstance(reference, str) or not reference.strip():
        return False
    parsed = urllib.parse.urlsplit(reference.strip())
    if parsed.scheme or parsed.netloc:
        return False
    candidate = parsed.path
    for _ in range(4):
        if "\x00" in candidate or "\\" in candidate:
            return False
        unquoted = urllib.parse.unquote(candidate)
        if unquoted == candidate:
            break
        candidate = unquoted
    if "\x00" in candidate or "\\" in candidate:
        return False
    # Reject parent traversal on the raw segments: normpath would silently
    # collapse ``OEBPS/../outside`` to ``outside`` before it could be seen.
    parts = PurePosixPath(candidate).parts
    if candidate.startswith("/") or ".." in parts:
        return False
    return True
