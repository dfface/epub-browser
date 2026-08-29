import os
import ntpath
import posixpath
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
import re
import hashlib
import base64
import html
import json
import urllib.parse
import minify_html
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Optional, TYPE_CHECKING

from .asset_publisher import (
    AssetPublisher,
    PublishedAssets,
    SERVER_ONLY_ASSET_PATHS,
    SERVER_ONLY_ASSET_PREFIXES,
    rewrite_asset_urls,
)
from .models import BookMetadata, ConvertedBook
from .reporting import Reporter
from .server_chrome import (
    SERVER_ACCOUNT_CONTROL,
    SERVER_ACCOUNT_PANEL,
    SERVER_ACCOUNT_STYLESHEET,
    SERVER_AUTH_SCRIPT,
    SERVER_LOCALE_CONTROL,
    SERVER_LOCALE_SCRIPT,
)
from .source_format import EPUB_FORMAT, PDF_FORMAT
from .urls import SiteURLs, rewrite_root_urls
from .version import render_footer

if TYPE_CHECKING:
    from .pdf_processor import PDFMetadata

# Server mode stores only EPUB-derived content. Reader HTML is rendered from
# that cache for each request, so changes to UI, i18n, permissions, or hashed
# assets never require reconverting unchanged EPUB files.
SERVER_OUTPUT_REVISION_FILE = ".server-content-revision"
# Bump whenever the EPUB-derived server cache schema or chapter semantics change.
# Server reader chrome and assets are deliberately outside this revision.
SERVER_OUTPUT_REVISION = "server-content-v9"

SERVER_PASSIVE_RESOURCE_SUFFIXES = frozenset({
    "aac", "avif", "bmp", "css", "eot", "flac", "gif", "ico", "jpe", "jfif", "jpeg",
    "jpg", "m4a", "m4v", "mp3", "mp4", "mpeg", "mpg", "oga", "ogg",
    "ogv", "opus", "otf", "png", "svg", "ttf", "wav", "webm", "webp",
    "woff", "woff2",
})
_GENERATED_READER_PAGE = re.compile(r"^(?:index|chapter_[0-9]+)\.html$")


def server_book_public_path_allowed(relative_path):
    """Return whether a Server book path is generated or a passive resource."""
    candidate = PurePosixPath(str(relative_path or ""))
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    parts = candidate.parts
    if len(parts) == 1:
        return parts[0] == "toc.json" or bool(
            _GENERATED_READER_PAGE.fullmatch(parts[0])
        )
    if len(parts) < 2 or parts[0] != "resources":
        return False
    suffix = candidate.suffix.casefold().lstrip(".")
    return suffix in SERVER_PASSIVE_RESOURCE_SUFFIXES


_SAFE_HTML_TAGS = frozenset({
    "a", "abbr", "address", "article", "aside", "b", "bdi", "bdo",
    "blockquote", "br", "caption", "cite", "code", "col", "colgroup",
    "dd", "del", "details", "dfn", "div", "dl", "dt", "em",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hr", "i", "img", "ins", "kbd", "li", "main",
    "mark", "nav", "ol", "p", "pre", "q", "rp", "rt", "ruby", "s",
    "samp", "section", "small", "span", "strong", "sub", "summary",
    "sup", "table", "tbody", "td", "tfoot", "th", "thead", "time",
    "tr", "u", "ul", "var", "wbr", "audio", "video", "source",
})
_VOID_HTML_TAGS = frozenset({"br", "col", "hr", "img", "source", "wbr"})
_DROP_HTML_CONTENT_TAGS = frozenset({
    "applet", "base", "button", "canvas", "embed", "form", "iframe",
    "input", "math", "meta", "object", "option", "script", "select",
    "style", "svg", "template", "textarea",
})
_GLOBAL_HTML_ATTRIBUTES = frozenset({
    "class", "dir", "id", "lang", "role", "title", "xml:lang",
})
_TAG_HTML_ATTRIBUTES = {
    "a": frozenset({"href"}),
    "audio": frozenset({"controls", "loop", "muted", "preload", "src"}),
    "col": frozenset({"span"}),
    "colgroup": frozenset({"span"}),
    "img": frozenset({"alt", "height", "loading", "src", "width"}),
    "li": frozenset({"value"}),
    "ol": frozenset({"reversed", "start", "type"}),
    "source": frozenset({"src", "type"}),
    "td": frozenset({"colspan", "headers", "rowspan"}),
    "th": frozenset({"colspan", "headers", "rowspan", "scope"}),
    "time": frozenset({"datetime"}),
    "video": frozenset({
        "controls", "height", "loop", "muted", "poster", "preload", "src",
        "width",
    }),
}
_URL_HTML_ATTRIBUTES = frozenset({"href", "poster", "src"})
_SAFE_LINK_SCHEMES = frozenset({"http", "https", "mailto", "tel"})
_SAFE_MEDIA_SCHEMES = frozenset({"http", "https"})
_SAFE_DATA_IMAGE = re.compile(
    r"^data:image/(?:gif|jpe?g|png|webp);base64,[a-z0-9+/=\s]+$",
    re.IGNORECASE,
)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_ESCAPE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})\s?|([^\r\n]))")
_RISKY_CSS = re.compile(
    r"(?:@import|@namespace|expression\s*\(|javascript\s*:|behavior\s*:|"
    r"-moz-binding|(?:-webkit-)?image-set\s*\()",
    re.IGNORECASE,
)
_CSS_DECLARATION_AT_RULES = frozenset({
    "counter-style", "font-face", "page", "property",
})
_CSS_GROUP_AT_RULES = frozenset({
    "container", "keyframes", "layer", "media", "scope", "supports",
    "-webkit-keyframes",
})
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_SAFE_SVG_TAGS = frozenset({
    "circle", "clipPath", "defs", "desc", "ellipse", "g", "line",
    "linearGradient", "mask", "path", "polygon", "polyline", "radialGradient",
    "rect", "stop", "svg", "symbol", "text", "title", "tspan",
})
_SAFE_SVG_ATTRIBUTES = frozenset({
    "class", "clip-path", "cx", "cy", "d", "dominant-baseline", "dx", "dy",
    "fill", "fill-opacity", "fill-rule", "font-family", "font-size",
    "font-style", "font-weight", "gradientTransform", "gradientUnits", "height",
    "id", "line-height", "mask", "offset", "opacity", "pathLength", "points",
    "preserveAspectRatio", "r", "rotate", "rx", "ry", "spreadMethod", "stop-color",
    "stop-opacity", "stroke", "stroke-dasharray", "stroke-dashoffset",
    "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-opacity",
    "stroke-width", "text-anchor", "transform", "viewBox", "width", "x", "x1",
    "x2", "y", "y1", "y2",
})


def _safe_html_url(tag, attribute, value):
    if not isinstance(value, str):
        return None
    candidate = html.unescape(value).strip()
    if not candidate or any(ord(character) < 32 for character in candidate):
        return None
    if candidate.startswith("#"):
        return candidate
    parsed = urllib.parse.urlsplit(candidate)
    scheme = parsed.scheme.casefold()
    if not scheme:
        if (
            attribute == "href"
            and not parsed.netloc
            and parsed.path.startswith("/")
        ):
            return candidate
        resource_path = PurePosixPath(parsed.path)
        suffix = resource_path.suffix.casefold().lstrip(".")
        if attribute in {"src", "poster"}:
            return (
                candidate
                if suffix in SERVER_PASSIVE_RESOURCE_SUFFIXES
                else None
            )
        if attribute == "href" and suffix:
            if _GENERATED_READER_PAGE.fullmatch(resource_path.name):
                return candidate
            return (
                candidate
                if suffix in SERVER_PASSIVE_RESOURCE_SUFFIXES
                else None
            )
        return candidate
    if attribute == "href" and scheme in _SAFE_LINK_SCHEMES:
        return candidate
    if attribute in {"src", "poster"}:
        if scheme in _SAFE_MEDIA_SCHEMES:
            return candidate
        if tag == "img" and _SAFE_DATA_IMAGE.fullmatch(candidate):
            return candidate
    return None


class _EPUBHTMLSanitizer(HTMLParser):
    """Serialize a conservative, inert fragment from untrusted EPUB markup."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []
        self._suppressed = []

    @staticmethod
    def _tag_name(tag):
        return str(tag or "").casefold().rsplit(":", 1)[-1]

    def handle_starttag(self, tag, attrs):
        name = self._tag_name(tag)
        if self._suppressed:
            if name in _DROP_HTML_CONTENT_TAGS:
                self._suppressed.append(name)
            return
        if name in _DROP_HTML_CONTENT_TAGS:
            self._suppressed.append(name)
            return
        if name not in _SAFE_HTML_TAGS:
            return
        allowed = _TAG_HTML_ATTRIBUTES.get(name, frozenset())
        serialized = []
        for raw_name, raw_value in attrs:
            attribute = str(raw_name or "").casefold()
            if attribute.startswith("on") or attribute in {"srcdoc", "formaction"}:
                continue
            if attribute == "style":
                safe_style = sanitize_css_declarations(raw_value)
                if safe_style:
                    serialized.append(
                        " style=\"{}\"".format(html.escape(safe_style, quote=True))
                    )
                continue
            if not (
                attribute in _GLOBAL_HTML_ATTRIBUTES
                or attribute in allowed
                or attribute.startswith("aria-")
                or attribute.startswith("data-")
            ):
                continue
            value = attribute if raw_value is None else str(raw_value)
            if attribute in _URL_HTML_ATTRIBUTES:
                value = _safe_html_url(name, attribute, value)
                if value is None:
                    continue
            serialized.append(
                " {}=\"{}\"".format(attribute, html.escape(value, quote=True))
            )
        self.output.append("<{}{}>".format(name, "".join(serialized)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        name = self._tag_name(tag)
        if self._suppressed:
            if name == self._suppressed[-1]:
                self._suppressed.pop()
            return
        if name in _SAFE_HTML_TAGS and name not in _VOID_HTML_TAGS:
            self.output.append("</{}>".format(name))

    def handle_data(self, data):
        if not self._suppressed:
            self.output.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if not self._suppressed:
            self.output.append("&{};".format(name))

    def handle_charref(self, name):
        if not self._suppressed:
            self.output.append("&#{};".format(name))

    def fragment(self):
        return "".join(self.output)


class _MetadataTextParser(HTMLParser):
    """Extract display text from metadata before context-specific escaping."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []

    def handle_data(self, data):
        self.output.append(data)


def metadata_text(value):
    parser = _MetadataTextParser()
    parser.feed(str(value or ""))
    parser.close()
    return "".join(parser.output)


def sanitize_html_fragment(content):
    sanitizer = _EPUBHTMLSanitizer()
    sanitizer.feed(str(content or ""))
    sanitizer.close()
    return sanitizer.fragment()


def _decode_css_escapes(content):
    def replace(match):
        if match.group(1):
            try:
                codepoint = int(match.group(1), 16)
                return chr(codepoint) if codepoint else "\ufffd"
            except (OverflowError, ValueError):
                return "\ufffd"
        return match.group(2) or ""

    return _CSS_ESCAPE.sub(replace, str(content or ""))


def _safe_css_url(value):
    candidate = html.unescape(_decode_css_escapes(value)).strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] \
            and candidate[0] in {'"', "'"}:
        candidate = candidate[1:-1].strip()
    if not candidate or any(ord(character) < 32 for character in candidate):
        return False
    if candidate.startswith("#"):
        return True
    if candidate.casefold().startswith("data:"):
        return bool(_SAFE_DATA_IMAGE.fullmatch(candidate))
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme or parsed.netloc or candidate.startswith(("/", "\\")):
        return False
    decoded_path = parsed.path
    for _ in range(3):
        unquoted = urllib.parse.unquote(decoded_path)
        if unquoted == decoded_path:
            break
        decoded_path = unquoted
    suffix = PurePosixPath(decoded_path.replace("\\", "/")).suffix.casefold().lstrip(".")
    return suffix in SERVER_PASSIVE_RESOURCE_SUFFIXES


def _css_urls_are_safe(content):
    decoded = _decode_css_escapes(content)
    position = 0
    while True:
        match = re.search(r"url\s*\(", decoded[position:], re.IGNORECASE)
        if match is None:
            return True
        start = position + match.end()
        index = start
        quote = None
        escaped = False
        while index < len(decoded):
            character = decoded[index]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif quote:
                if character == quote:
                    quote = None
            elif character in {'"', "'"}:
                quote = character
            elif character == ")":
                break
            index += 1
        if index >= len(decoded) or quote is not None:
            return False
        if not _safe_css_url(decoded[start:index]):
            return False
        position = index + 1


def _split_css_declarations(content):
    parts = []
    start = 0
    quote = None
    escaped = False
    parentheses = 0
    for index, character in enumerate(content):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "(":
            parentheses += 1
        elif character == ")" and parentheses:
            parentheses -= 1
        elif character == ";" and not parentheses:
            parts.append(content[start:index])
            start = index + 1
    parts.append(content[start:])
    return parts


def sanitize_css_declarations(content):
    declarations = []
    for raw_declaration in _split_css_declarations(str(content or "")):
        declaration = raw_declaration.strip()
        if not declaration or ":" not in declaration:
            continue
        decoded = _decode_css_escapes(declaration)
        if _RISKY_CSS.search(decoded) or not _css_urls_are_safe(declaration):
            continue
        declarations.append(declaration)
    return "; ".join(declarations)


def _css_at_rule_name(prelude):
    match = re.match(r"\s*@([\w-]+)", _decode_css_escapes(prelude))
    return match.group(1).casefold() if match else ""


def _find_css_boundary(content, start):
    quote = None
    escaped = False
    parentheses = 0
    for index in range(start, len(content)):
        character = content[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "(":
            parentheses += 1
        elif character == ")" and parentheses:
            parentheses -= 1
        elif not parentheses and character in "{;":
            return index, character
    return len(content), ""


def _find_matching_css_brace(content, opening):
    quote = None
    escaped = False
    depth = 1
    for index in range(opening + 1, len(content)):
        character = content[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _sanitize_css_stylesheet(content):
    output = []
    position = 0
    while position < len(content):
        while position < len(content) and content[position].isspace():
            position += 1
        boundary, kind = _find_css_boundary(content, position)
        prelude = content[position:boundary].strip()
        if not kind:
            break
        if kind == ";":
            rule_name = _css_at_rule_name(prelude)
            if rule_name not in {"import", "namespace", "charset"} \
                    and prelude and not _RISKY_CSS.search(_decode_css_escapes(prelude)):
                output.append(prelude + ";")
            position = boundary + 1
            continue

        closing = _find_matching_css_brace(content, boundary)
        if closing is None:
            break
        body = content[boundary + 1:closing]
        rule_name = _css_at_rule_name(prelude)
        if rule_name:
            if rule_name in _CSS_DECLARATION_AT_RULES:
                safe_body = sanitize_css_declarations(body)
            elif rule_name in _CSS_GROUP_AT_RULES:
                safe_body = _sanitize_css_stylesheet(body)
            else:
                safe_body = ""
        elif _RISKY_CSS.search(_decode_css_escapes(prelude)):
            safe_body = ""
        else:
            safe_body = sanitize_css_declarations(body)
        if prelude and safe_body:
            output.append("{} {{ {} }}".format(prelude, safe_body))
        position = closing + 1
    return "\n".join(output)


def sanitize_css_text(content):
    candidate = _CSS_COMMENT.sub("", str(content or ""))
    if not _RISKY_CSS.search(_decode_css_escapes(candidate)) \
            and _css_urls_are_safe(candidate):
        return candidate
    return _sanitize_css_stylesheet(candidate)


def _xml_local_name(name):
    return str(name).rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def sanitize_svg_content(content):
    try:
        source_root = ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError("Unsafe or malformed SVG resource") from error
    if _xml_local_name(source_root.tag) != "svg":
        raise ValueError("Unsafe SVG resource root")

    def clean(source):
        name = _xml_local_name(source.tag)
        if name not in _SAFE_SVG_TAGS:
            return None
        target = ET.Element("{{{}}}{}".format(_SVG_NAMESPACE, name))
        for raw_name, raw_value in source.attrib.items():
            attribute = _xml_local_name(raw_name)
            if attribute not in _SAFE_SVG_ATTRIBUTES:
                continue
            value = str(raw_value).strip()
            if "url(" in value.casefold() and not re.fullmatch(
                r"url\(#[A-Za-z_][\w.-]*\)",
                value,
            ):
                continue
            target.set(attribute, value)
        if source.text:
            target.text = source.text
        for child in source:
            cleaned = clean(child)
            if cleaned is not None:
                target.append(cleaned)
                if child.tail:
                    cleaned.tail = child.tail
        return target

    ET.register_namespace("", _SVG_NAMESPACE)
    return ET.tostring(clean(source_root), encoding="unicode")


class EPUBProcessor:
    """处理EPUB文件的类"""

    @classmethod
    def from_pdf_metadata(
        cls,
        *,
        book_id: str,
        metadata: "PDFMetadata",
        cover_path: Optional[str],
        asset_manifest: PublishedAssets,
        urls: SiteURLs,
        deployment_mode: str,
    ) -> "EPUBProcessor":
        """Hydrate PDF pages into the state consumed by the shared templates."""
        if deployment_mode not in {"ssg", "server"}:
            raise ValueError(f"Unsupported deployment mode: {deployment_mode}")

        processor = cls.__new__(cls)
        processor.epub_path = ""
        processor.output_dir = None
        processor.urls = urls or SiteURLs()
        processor.reporter = Reporter(False)
        processor.deployment_mode = deployment_mode
        processor.source_format = PDF_FORMAT
        processor._caller_supplied_book_id = True
        processor.book_hash = str(book_id)
        processor.temp_dir = ""
        processor.extract_dir = ""
        processor.web_dir = ""
        processor.book_title = metadata.title or "PDF Book"
        processor.authors = list(metadata.authors)
        processor.tags = list(metadata.tags)
        processor.description = None
        processor.epub_identifier = None
        processor.cover_info = (
            {"full_path": cover_path, "web_path": cover_path}
            if cover_path else None
        )
        processor.lang = metadata.language or "en"
        processor.chapters = [
            {
                "title": f"Page {page.page_number}",
                "path": f"chapter_{page.page_number - 1}.html",
            }
            for page in metadata.pages
        ]
        processor.toc = [
            {
                "title": f"Page {page.page_number}",
                "level": 0,
                "kind": "chapter",
                "chapter_index": page.page_number - 1,
                "chapter_file": f"chapter_{page.page_number - 1}.html",
                "page_label": str(page.page_number),
                "outline_labels": list(page.outline_labels),
            }
            for page in metadata.pages
        ]
        processor.resources_base = "resources"
        processor._server_chapter_payloads = {}
        processor.asset_manifest = asset_manifest
        processor._pdf_pages = tuple(metadata.pages)
        processor._pdf_encrypted = bool(metadata.encrypted)
        processor._pdf_has_extractable_text = bool(metadata.has_extractable_text)
        return processor

    @classmethod
    def from_server_content_cache(
        cls,
        *,
        book_id,
        metadata,
        asset_manifest,
        urls=None,
        reporter=None,
    ):
        """Restore the minimal render state for a Server content cache.

        Server mode deliberately persists EPUB-derived content rather than
        rendered HTML.  This named constructor keeps the cache hydration
        contract beside the shared templates, so ServerPageRenderer remains a
        thin adapter instead of becoming a second page implementation.
        """
        if not isinstance(metadata, dict):
            raise ValueError("Server content metadata must be an object")
        title = metadata.get("title")
        chapters = metadata.get("chapters")
        toc = metadata.get("toc")
        if not isinstance(title, str) or not isinstance(chapters, list) or not isinstance(toc, list):
            raise ValueError("Server content metadata is invalid")

        processor = cls.__new__(cls)
        processor.epub_path = ""
        processor.output_dir = None
        processor.urls = urls or SiteURLs()
        processor.reporter = reporter or Reporter(False)
        processor.deployment_mode = "server"
        processor.source_format = EPUB_FORMAT
        processor._caller_supplied_book_id = True
        processor.book_hash = str(book_id)
        processor.temp_dir = ""
        processor.extract_dir = ""
        processor.web_dir = ""
        processor.book_title = title
        processor.authors = list(metadata.get("authors") or ())
        processor.tags = list(metadata.get("tags") or ())
        processor.description = metadata.get("description")
        processor.epub_identifier = metadata.get("epub_identifier")
        processor.cover_info = metadata.get("cover_info")
        processor.lang = metadata.get("language") or "en"
        processor.chapters = chapters
        processor.toc = toc
        processor.resources_base = metadata.get("resources_base") or "resources"
        processor._server_chapter_payloads = {}
        processor.asset_manifest = asset_manifest
        return processor
    
    def __init__(
        self,
        epub_path,
        output_dir=None,
        asset_manifest=None,
        book_id=None,
        urls=None,
        reporter=None,
        deployment_mode="ssg",
    ):
        self.epub_path = os.fspath(epub_path)
        self.output_dir = output_dir
        self.urls = urls or SiteURLs()
        self.reporter = reporter or Reporter(False)
        if deployment_mode not in {"ssg", "server"}:
            raise ValueError(f"Unsupported deployment mode: {deployment_mode}")
        self.deployment_mode = deployment_mode
        self.source_format = EPUB_FORMAT
        self._caller_supplied_book_id = book_id is not None
        self.book_hash = book_id or base64.urlsafe_b64encode(
            hashlib.md5(self.epub_path.encode('utf-8')).digest()
        ).decode().rstrip('=')  # 使用哈希值作为标识，后续可能会根据 ncx 更新
        
        if output_dir:
            # 使用用户指定的输出目录
            # 这里一般会始终使用 base_directory，也就是上层已经处理了，可能是 temp dir
            self.temp_dir = os.path.join(output_dir, f'epub_{self.book_hash}')
            os.makedirs(self.temp_dir, exist_ok=True)
        else:
            # 使用系统临时目录
            # 本程序永远走不到这里来的，除非作为库被别人调用
            self.temp_dir = tempfile.mkdtemp(prefix='epub_')
            
        self.extract_dir = os.path.join(self.temp_dir, 'extracted')
        self.web_dir = os.path.join(self.temp_dir, 'web')
        self.book_title = "EPUB Book"
        self.authors = None
        self.tags = None
        self.description = None
        self.epub_identifier = None
        self.cover_info = None
        self.lang = 'en'
        self.chapters = []
        self.toc = []  # 存储目录结构
        self.resources_base = "resources"  # 资源文件的基础路径
        self._server_chapter_payloads = {}
        if asset_manifest is not None:
            self.asset_manifest = asset_manifest
        else:
            assets_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets')
            asset_output_dir = output_dir or self.temp_dir
            self.asset_manifest = AssetPublisher(
                assets_dir,
                asset_output_dir,
                urls=self.urls,
                excluded_paths=(
                    SERVER_ONLY_ASSET_PATHS
                    if self.deployment_mode == "ssg"
                    else ()
                ),
                excluded_prefixes=(
                    SERVER_ONLY_ASSET_PREFIXES
                    if self.deployment_mode == "ssg"
                    else ()
                ),
            ).publish()
    
    def cleanup(self):
        # 诸如 extract 失败
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def _server_ai_feature_assets(self):
        """Expose immutable optional AI assets without putting them on the critical path."""
        if self.deployment_mode != "server":
            return ""
        logical_assets = {
            "aiCanvasCss": "ai-canvas.css",
            "aiCanvas": "ai-canvas.js",
            "aiReadingHubCss": "ai-reading-hub.css",
            "aiReadingHub": "ai-reading-hub.js",
            "aiChatCss": "ai-chat.css",
            "aiChat": "ai-chat.js",
            "aiRichTextCss": "ai-rich-text.css",
            "aiRichText": "ai-rich-text.js",
            "markdownIt": "vendor/markdown-it/markdown-it.min.js",
            "katexCss": "vendor/katex/katex.min.css",
            "katex": "vendor/katex/katex.min.js",
            "mermaid": "vendor/mermaid/mermaid.min.js",
        }
        urls = {
            name: self.asset_manifest.url_for(logical_name)
            for name, logical_name in logical_assets.items()
        }
        return (
            '<script>window.EpubBrowserFeatureAssets='
            + json.dumps(urls, separators=(",", ":"))
            + ';</script>'
        )

    def _resolve_internal_path(self, reference, base=""):
        """Resolve an EPUB URI path without allowing it outside extraction."""
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("Unsafe EPUB internal path: empty reference")

        raw_reference = reference.strip()
        parsed = urllib.parse.urlsplit(raw_reference)
        if parsed.scheme or parsed.netloc:
            raise ValueError(f"Unsafe EPUB internal path: {reference}")

        decoded_path = urllib.parse.unquote(parsed.path)
        probe = parsed.path
        for _ in range(4):
            if "\x00" in probe or "\\" in probe:
                raise ValueError(f"Unsafe EPUB internal path: {reference}")
            drive, _ = ntpath.splitdrive(probe)
            candidate = PurePosixPath(probe)
            if drive or candidate.is_absolute():
                raise ValueError(f"Unsafe EPUB internal path: {reference}")
            decoded_probe = urllib.parse.unquote(probe)
            if decoded_probe == probe:
                break
            decoded_candidate = PurePosixPath(decoded_probe)
            decoded_drive, _ = ntpath.splitdrive(decoded_probe)
            if (
                "\x00" in decoded_probe
                or "\\" in decoded_probe
                or decoded_drive
                or decoded_candidate.is_absolute()
                or ".." in decoded_candidate.parts
            ):
                raise ValueError(f"Unsafe EPUB internal path: {reference}")
            probe = decoded_probe

        combined = posixpath.normpath(posixpath.join(base or "", decoded_path))
        drive, _ = ntpath.splitdrive(combined)
        relative = PurePosixPath(combined)
        if (
            not combined
            or combined == "."
            or drive
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise ValueError(f"Unsafe EPUB internal path: {reference}")

        extract_root = Path(self.extract_dir).resolve()
        target = extract_root.joinpath(*relative.parts).resolve()
        try:
            target.relative_to(extract_root)
        except ValueError as error:
            raise ValueError(f"Unsafe EPUB internal path: {reference}") from error
        return relative.as_posix()

    def _internal_file(self, reference, base=""):
        relative = self._resolve_internal_path(reference, base)
        return Path(self.extract_dir).resolve().joinpath(
            *PurePosixPath(relative).parts
        ).resolve()

    @staticmethod
    def _is_external_reference(reference):
        parsed = urllib.parse.urlsplit(reference)
        return (
            parsed.scheme.lower() in {"http", "https", "data", "mailto", "tel"}
            or bool(parsed.netloc)
            or reference.startswith("#")
        )

    def _resource_reference(self, reference, base):
        parsed = urllib.parse.urlsplit(reference)
        relative = self._resolve_internal_path(reference, base)
        result = f"{self.resources_base}/{relative}"
        if parsed.query:
            result += "?" + parsed.query
        if parsed.fragment:
            result += "#" + parsed.fragment
        return result

    def generate_hash(self):
        """生成书籍 Hash
        一般来说，用路径受到用户传参影响，每次都是绝对路径则都是一样；
        content.opf 可能因修改元数据如标签而更改；
        toc.ncx 一般不会变化，用这个来 Hash 比较合适，而这个解析出来的是 toc 变量；
        """
        if self._caller_supplied_book_id:
            return
        if self.toc:
            # 预处理 self.toc，只取  'title', 'src', 'level'，不取 'anchor'
            toc_to_hash = []
            for toc_item in self.toc:
                toc_to_hash.append({
                    'title': toc_item.get('title'),
                    'src': toc_item.get('src'),
                    'level': toc_item.get('level'),
                })
            # 1. 压缩成稳定一行JSON
            json_str = json.dumps(toc_to_hash, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
            # 2. 生成完整128位MD5字节
            md5_bytes = hashlib.md5(json_str.encode('utf-8')).digest()
            # 3. URL安全Base64 + 去掉无用的=填充符
            safe_str = base64.urlsafe_b64encode(md5_bytes).decode().rstrip('=')
            self.book_hash = safe_str
            # 如果重新生成 Hash，需要修改路径
            if self.output_dir:
                new_temp_dir = os.path.join(self.output_dir, f'epub_{self.book_hash}')
                try:
                    if not os.path.exists(new_temp_dir):
                        os.rename(self.temp_dir, new_temp_dir)
                    self.temp_dir = new_temp_dir
                    self.web_dir = os.path.join(self.temp_dir, 'web')
                    self.extract_dir = os.path.join(self.temp_dir, 'extracted')
                except OSError:
                    return
        
    def extract_epub(self):
        """解压EPUB文件"""
        try:
            with zipfile.ZipFile(self.epub_path, 'r') as zip_ref:
                extract_root = Path(self.extract_dir).resolve()
                extract_root.mkdir(parents=True, exist_ok=True)
                for member in zip_ref.infolist():
                    member_name = member.filename.replace("\\", "/")
                    member_path = PurePosixPath(member_name)
                    for candidate_name in (
                        member_name,
                        urllib.parse.unquote(member_name),
                    ):
                        drive, _ = ntpath.splitdrive(candidate_name)
                        candidate_path = PurePosixPath(candidate_name)
                        if (
                            "\x00" in candidate_name
                            or "\\" in candidate_name
                            or drive
                            or candidate_path.is_absolute()
                            or ".." in candidate_path.parts
                        ):
                            raise ValueError(
                                f"Unsafe EPUB archive path: {member.filename}"
                            )
                    destination = extract_root.joinpath(*member_path.parts).resolve()
                    try:
                        destination.relative_to(extract_root)
                    except ValueError as error:
                        raise ValueError(
                            f"Unsafe EPUB archive path: {member.filename}"
                        ) from error
                    zip_ref.extract(member, extract_root)
            return True
        except ValueError:
            raise
        except (OSError, zipfile.BadZipFile):
            return False

    def convert(self):
        """Convert one EPUB into its caller-owned staging directory."""
        if not self.extract_epub():
            raise ValueError(f"Unable to extract EPUB file: {self.epub_path}")
        opf_path = self.parse_container()
        if not opf_path:
            raise ValueError(f"Unable to parse EPUB container file: {self.epub_path}")
        if not self.parse_opf(opf_path):
            raise ValueError(f"Unable to parse EPUB package file: {self.epub_path}")
        self.generate_hash()
        self.create_web_interface()
        if self.deployment_mode == "server":
            Path(self.web_dir, SERVER_OUTPUT_REVISION_FILE).write_text(
                SERVER_OUTPUT_REVISION + "\n",
                encoding="utf-8",
            )
        return ConvertedBook(
            book_id=self.book_hash,
            source_path=Path(self.epub_path),
            output_dir=Path(self.web_dir),
            metadata=self.get_metadata(),
            chapter_count=len(self.chapters),
        )
    
    def parse_container(self):
        """解析container.xml获取内容文件路径"""
        container_path = os.path.join(self.extract_dir, 'META-INF', 'container.xml')
        if not os.path.exists(container_path):
            self.reporter.detail("container.xml file not found")
            return None
            
        try:
            tree = ET.parse(container_path)
            root = tree.getroot()
            # 查找rootfile元素
            ns = {'ns': 'urn:oasis:names:tc:opendocument:xmlns:container'}
            rootfile = root.find('.//ns:rootfile', ns)
            if rootfile is not None:
                return self._resolve_internal_path(rootfile.get('full-path'))
        except ValueError:
            raise
        except Exception as e:
            self.reporter.detail(f"Failed to parse container.xml: {e}")
            
        return None
    
    def find_cover_info(self, opf_tree, namespaces):
        """
        在 OPF 文件中查找封面信息
        """
        # 方法1: 查找 meta 标签中声明的封面
        cover_id = None
        meta_elements = opf_tree.findall('.//opf:metadata/opf:meta', namespaces)
        for meta in meta_elements:
            if meta.get('name') in ['cover', 'cover-image']:
                cover_id = meta.get('content')
                break
        
        # 方法2: 查找 manifest 中的封面项
        manifest_items = opf_tree.findall('.//opf:manifest/opf:item', namespaces)
        
        # 优先使用 meta 标签中指定的封面
        if cover_id:
            for item in manifest_items:
                if item.get('id') == cover_id:
                    return {
                        'href': item.get('href'),
                        'media-type': item.get('media-type'),
                        'id': item.get('id')
                    }
        
        # 方法3: 通过文件名模式查找
        cover_patterns = ['cover', 'Cover', 'COVER', 'titlepage', 'TitlePage']
        for item in manifest_items:
            media_type = item.get('media-type', '')
            href = item.get('href', '')
            
            # 检查是否是图片文件
            if media_type.startswith('image/'):
                # 检查文件名是否匹配封面模式
                if any(pattern in href for pattern in cover_patterns):
                    return {
                        'href': href,
                        'media-type': media_type,
                        'id': item.get('id')
                    }
        
        # 方法4: 查找第一个图片作为备选
        for item in manifest_items:
            media_type = item.get('media-type', '')
            if media_type.startswith('image/'):
                return {
                    'href': item.get('href'),
                    'media-type': media_type,
                    'id': item.get('id')
                }
        
        return None

    def find_ncx_file(self, opf_path, manifest):
        """查找NCX文件路径"""
        opf_dir = posixpath.dirname(opf_path)
        
        # 首先查找OPF中明确指定的toc
        try:
            tree = ET.parse(self._internal_file(opf_path))
            root = tree.getroot()
            ns = {'opf': 'http://www.idpf.org/2007/opf'}
            
            spine = root.find('.//opf:spine', ns)
            if spine is not None:
                toc_id = spine.get('toc')
                if toc_id and toc_id in manifest:
                    ncx_path = manifest[toc_id]['full_path']
                    if ncx_path and self._internal_file(ncx_path).is_file():
                        return ncx_path
        except ValueError:
            raise
        except Exception as e:
            self.reporter.detail(f"Failed to find toc attribute: {e}")
        
        # 如果没有明确指定，查找media-type为application/x-dtbncx+xml的文件
        for item_id, item in manifest.items():
            if item['media_type'] == 'application/x-dtbncx+xml':
                ncx_path = item['full_path']
                if ncx_path and self._internal_file(ncx_path).is_file():
                    return ncx_path
        
        # 最后，尝试查找常见的NCX文件名
        common_ncx_names = ['toc.ncx', 'nav.ncx', 'ncx.ncx']
        for name in common_ncx_names:
            ncx_path = self._resolve_internal_path(name, opf_dir)
            if self._internal_file(ncx_path).is_file():
                return ncx_path
        
        return None

    def find_nav_file(self, manifest):
        """Return the EPUB 3 navigation document declared in the manifest."""
        for item in manifest.values():
            properties = item.get('properties', '').split()
            if 'nav' not in properties:
                continue
            nav_path = item.get('full_path')
            if nav_path and self._internal_file(nav_path).is_file():
                return nav_path
        return None

    def parse_nav(self, nav_path):
        """Parse the EPUB 3 navigation document's ``toc`` nav element."""
        nav_full_path = self._internal_file(nav_path)
        if not nav_full_path.is_file():
            self.reporter.detail(f"EPUB navigation document not found: {nav_full_path}")
            return []

        try:
            root = ET.parse(nav_full_path).getroot()
            epub_type = '{http://www.idpf.org/2007/ops}type'

            def local_name(element):
                return element.tag.rsplit('}', 1)[-1]

            toc_nav = next(
                (
                    element for element in root.iter()
                    if local_name(element) == 'nav'
                    and 'toc' in element.get(epub_type, element.get('type', '')).split()
                ),
                None,
            )
            if toc_nav is None:
                return []

            def direct_child(element, name):
                return next(
                    (child for child in element if local_name(child) == name), None
                )

            def item_label(item):
                for child in item:
                    if local_name(child) in {'a', 'span'}:
                        label = ' '.join(''.join(child.itertext()).split())
                        if label:
                            return html.unescape(label), child
                label = ' '.join((item.text or '').split())
                return html.unescape(label), None

            toc = []
            nav_dir = posixpath.dirname(nav_path)

            def process_list(list_element, level=0):
                for item in list_element:
                    if local_name(item) != 'li':
                        continue
                    title, link = item_label(item)
                    child_list = direct_child(item, 'ol')
                    if title:
                        toc_item = {'title': title, 'level': level}
                        href = link.get('href') if link is not None else None
                        if href:
                            source, anchor = urllib.parse.urldefrag(href)
                            if source:
                                full_src = self._resolve_internal_path(source, nav_dir)
                                toc_item.update({
                                    'src': full_src,
                                    'kind': 'chapter',
                                    'old_file_name': posixpath.basename(source),
                                })
                                if anchor:
                                    toc_item['anchor'] = anchor
                            elif child_list is not None:
                                toc_item['kind'] = 'section'
                        elif child_list is not None:
                            toc_item['kind'] = 'section'
                        if toc_item.get('kind') or toc_item.get('src'):
                            toc.append(toc_item)
                    if child_list is not None:
                        process_list(child_list, level + 1)

            list_element = direct_child(toc_nav, 'ol')
            if list_element is not None:
                process_list(list_element)
            return toc
        except ValueError:
            raise
        except Exception as error:
            self.reporter.detail(f"Failed to parse EPUB navigation document: {error}")
            return []
    
    def parse_ncx(self, ncx_path):
        """解析NCX文件获取目录结构"""
        ncx_full_path = self._internal_file(ncx_path)
        if not ncx_full_path.is_file():
            self.reporter.detail(f"NCX file not found: {ncx_full_path}")
            return []
            
        try:
            # 注册命名空间
            ET.register_namespace('', 'http://www.daisy.org/z3986/2005/ncx/')
            
            tree = ET.parse(ncx_full_path)
            root = tree.getroot()
            
            # 获取书籍标题（这一步应该在 opf 文件解析那里做）
            # doc_title = root.find('.//{http://www.daisy.org/z3986/2005/ncx/}docTitle/{http://www.daisy.org/z3986/2005/ncx/}text')
            # if doc_title is not None and doc_title.text:
            #     self.book_title = doc_title.text
            
            # 解析目录
            nav_map = root.find('.//{http://www.daisy.org/z3986/2005/ncx/}navMap')
            if nav_map is None:
                return []
            
            toc = []
            
            ncx_namespace = 'http://www.daisy.org/z3986/2005/ncx/'
            ncx_dir = posixpath.dirname(ncx_path)

            def navpoint_target(navpoint):
                """Return a navPoint's *own* NCX target, if it has one.

                A navPoint is allowed to be a structural grouping node.  Do
                not use a descendant ``content`` element here: doing so makes
                a group look like a chapter and consumes a public chapter
                index that belongs to the OPF spine.
                """
                content = navpoint.find(f'{{{ncx_namespace}}}content')
                if content is None or not content.get('src'):
                    return None
                source, anchor = urllib.parse.urldefrag(content.get('src'))
                if not source:
                    return None
                return (
                    self._resolve_internal_path(source, ncx_dir),
                    anchor or None,
                    posixpath.basename(source),
                )

            # 递归处理navPoint
            def process_navpoint(navpoint, level=0):
                # 处理子navPoint
                child_navpoints = navpoint.findall(f'{{{ncx_namespace}}}navPoint')
                target = navpoint_target(navpoint)
                child_targets = [navpoint_target(child) for child in child_navpoints]
                # Publishers often use a parent navPoint as a section label
                # and repeat its first child's target.  It is not another OPF
                # chapter; retain it for hierarchy, but make it non-navigable.
                is_section = target is not None and any(
                    child_target is not None
                    and child_target[0] == target[0]
                    and child_target[1] == target[1]
                    for child_target in child_targets
                )
                nav_label = navpoint.find(
                    f'{{{ncx_namespace}}}navLabel/{{{ncx_namespace}}}text'
                )

                if nav_label is not None and nav_label.text and target is not None:
                    full_src, anchor, old_file_name = target
                    toc_item = {
                        'title': nav_label.text,
                        'src': full_src,
                        'level': level,
                        'kind': 'section' if is_section else 'chapter',
                        'old_file_name': old_file_name,
                    }
                    if anchor:
                        toc_item['anchor'] = anchor
                    toc.append(toc_item)

                for child in child_navpoints:
                    process_navpoint(child, level + 1)
            
            # 处理所有顶级navPoint
            top_navpoints = nav_map.findall('{http://www.daisy.org/z3986/2005/ncx/}navPoint')
            for navpoint in top_navpoints:
                process_navpoint(navpoint, 0)
            
            # print(f"Parsed NCX table of contents items: {[(t['title'], t['src']) for t in toc]}")
            return toc
            
        except ValueError:
            raise
        except Exception as e:
            self.reporter.detail(f"Failed to parse NCX file: {e}")
            return []
    
    def parse_opf(self, opf_path):
        """解析OPF文件获取书籍信息和章节列表"""
        opf_full_path = self._internal_file(opf_path)
        if not opf_full_path.is_file():
            self.reporter.detail(f"OPF file not found: {opf_full_path}")
            return False
            
        try:
            tree = ET.parse(opf_full_path)
            root = tree.getroot()
            
            # 获取命名空间
            ns = {'opf': 'http://www.idpf.org/2007/opf',
                  'dc': 'http://purl.org/dc/elements/1.1/'}
            
            # 获取书名
            title_elem = root.find('.//dc:title', ns)
            if title_elem is not None and title_elem.text:
                self.book_title = title_elem.text

            identifier_elem = root.find('.//dc:identifier', ns)
            if identifier_elem is not None and identifier_elem.text:
                self.epub_identifier = identifier_elem.text.strip() or None
            
            # 获取作者名
            authors = tree.findall('.//dc:creator', ns)
            self.authors = [author.text for author in authors] if authors else None

            # 获取标签
            tags = tree.findall('.//dc:subject', ns)
            self.tags = [tag.text for tag in tags] if tags else None

            # 获取描述
            description = tree.find('.//dc:description', ns)
            self.description = description.text if description is not None and description.text else None

            # 获取语言
            lang = root.find('.//dc:language', ns)
            self.lang = lang.text.strip() if lang is not None and lang.text and lang.text.strip() else 'en'
                
            # 获取manifest（所有资源）
            manifest = {}
            opf_dir = posixpath.dirname(opf_path)
            # 获取封面
            cover_info = self.find_cover_info(tree, ns)
            if cover_info:
                href = cover_info["href"]
                cover_info["full_path"] = (
                    self._resolve_internal_path(href, opf_dir) if href else None
                )
            self.cover_info = cover_info
            # 获取其他资源 xhtml、font、css 等
            for item in root.findall('.//opf:item', ns):
                item_id = item.get('id')
                href = item.get('href')
                media_type = item.get('media-type', '')
                # 构建相对于EPUB根目录的完整路径
                full_path = (
                    self._resolve_internal_path(href, opf_dir) if href else None
                )
                manifest[item_id] = {
                    'href': href,
                    'media_type': media_type,
                    'full_path': full_path,
                    'properties': item.get('properties', ''),
                }
            
            # EPUB 3 navigation documents are authoritative; NCX remains the
            # EPUB 2 and backward-compatibility fallback.
            nav_path = self.find_nav_file(manifest)
            if nav_path:
                self.toc = self.parse_nav(nav_path)
            if not self.toc:
                ncx_path = self.find_ncx_file(opf_path, manifest)
                if ncx_path:
                    self.toc = self.parse_ncx(ncx_path)
            
            # 获取spine（阅读顺序）
            spine = root.find('.//opf:spine', ns)
            if spine is not None:
                for itemref in spine.findall('opf:itemref', ns):
                    idref = itemref.get('idref')
                    if idref in manifest:
                        item = manifest[idref]
                        # 只处理HTML/XHTML内容
                        if item['media_type'] in ['application/xhtml+xml', 'text/html']:
                            # EPUB spine items marked non-linear are auxiliary
                            # material (most commonly a cover).  They must not
                            # consume a public chapter index: NCX links point to
                            # the linear reading sequence.
                            if itemref.get('linear', 'yes').lower() == 'no':
                                self.reporter.detail(
                                    "Skipping non-linear spine item: "
                                    f"{item['full_path']}"
                                )
                                continue
                            # The OPF spine is the canonical sequence for
                            # chapter_N.  Some publishers include a real
                            # section landing page in that sequence, while
                            # their NCX points the section label at the first
                            # article instead.  Preserve the landing page as
                            # its own chapter instead of letting NCX make it
                            # disappear.
                            section_index_title = self.find_section_index_title(
                                item['full_path']
                            )
                            # 尝试从toc中查找对应的标题
                            title = section_index_title or self.find_chapter_title(
                                item['full_path']
                            )
                            
                            self.chapters.append({
                                'id': idref,
                                'path': item['full_path'],
                                # The fallback title must agree with the public
                                # chapter_index used by reader, annotations and AI.
                                'title': title or f"Chapter {len(self.chapters)}",
                                'is_section_index': bool(section_index_title),
                            })
            
            # print(f"Found {len(self.chapters)} chapters")
            # print(f"Chapter list: {[(c['title'], c['path']) for c in self.chapters]}")
            return True
            
        except ValueError:
            raise
        except Exception as e:
            self.reporter.detail(f"Failed to parse OPF file: {e}")
            return False

    def find_chapter_title(self, chapter_path):
        """根据章节路径在toc中查找对应的标题"""
        def title_from_matches(matches):
            # A section label may intentionally share its target with its
            # first article.  The article title is the chapter title; the
            # section remains a TOC-only grouping label.
            for toc_item in matches:
                if toc_item.get('kind', 'chapter') != 'section':
                    return toc_item['title']
            return matches[0]['title'] if matches else None

        # 先尝试精确匹配
        matching = [
            item for item in self.toc if item.get('src') == chapter_path
        ]
        title = title_from_matches(matching)
        if title:
            return title
        
        # 如果直接匹配失败，尝试基于文件名匹配
        chapter_filename = posixpath.basename(chapter_path)
        matching = [
            item for item in self.toc
            if item.get('src')
            and posixpath.basename(item['src']) == chapter_filename
        ]
        title = title_from_matches(matching)
        if title:
            return title
        
        # 尝试规范化路径后再匹配
        normalized_chapter_path = posixpath.normpath(chapter_path)
        matching = [
            item for item in self.toc
            if item.get('src')
            and posixpath.normpath(item['src']) == normalized_chapter_path
        ]
        title = title_from_matches(matching)
        if title:
            return title
        
        # print(f"Chapter title not found: {chapter_path}")
        return None

    def find_section_index_title(self, chapter_path):
        """Return the title of a real EPUB section-index page, when present.

        ``chapter_N`` is defined solely by the linear OPF spine.  A number of
        EPUBs put a real section landing page in that spine but describe the
        same section in NCX as a parent node whose target repeats the first
        article.  Detecting the landing page from its own markup lets the TOC
        map that parent label to the correct, distinct chapter index.
        """
        try:
            content = self._internal_file(chapter_path).read_text(
                encoding="utf-8", errors="ignore"
            )
        except (OSError, ValueError):
            return None

        match = re.search(
            r"<(?P<tag>h[1-6]|div|p)\b(?=[^>]*\bclass\s*=\s*"  # i18n-allow-literal: CSS/HTML syntax
            r"(?:['\"])[^'\"]*\bsection_index_title\b[^'\"]*"
            r"(?:['\"]))[^>]*>(?P<content>.*?)</(?P=tag)\s*>",
            content,
            flags=re.IGNORECASE | re.DOTALL | re.VERBOSE,
        )
        if not match:
            return None
        title = re.sub(r"<[^>]+>", " ", match.group("content"))
        title = " ".join(metadata_text(html.unescape(title)).split())
        return title or None
    
    def create_web_interface(self):
        """创建网页界面"""
        os.makedirs(self.web_dir, exist_ok=True)
        
        # Server mode deliberately keeps page chrome out of the conversion
        # cache. The current application code renders it at request time.
        self.create_index_page(write=self.deployment_mode != "server")
        
        # 创建章节页面
        self.create_chapter_pages(write=self.deployment_mode != "server")
        
        # 复制资源文件（CSS、图片、字体等）并删除 extracted 文件夹
        self.copy_resources()

        if self.deployment_mode == "server":
            self._write_server_content_cache()
        
        # print(f"Web interface created at: {self.web_dir}")
        return self.web_dir
    
    def create_index_page(self, write=True, initial_book_review=None):
        """创建章节索引页面"""
        is_pdf_book = getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT
        sync_shelf_button = (
            ""
            if self.deployment_mode == "server"
            else '''<button class="bookshelf-action-btn" id="syncShelfBtn">
                    <i class="fas fa-sync" aria-hidden="true"></i> <span data-i18n="bookshelf.sync">Sync</span>
                </button>'''
        )
        book_language = html.escape(self.lang or 'en', quote=True)
        bookshelf_data_actions = """
                <button class="bookshelf-action-btn" id="exportShelfBtn">
                    <i class="fas fa-upload" aria-hidden="true"></i> <span data-i18n="bookshelf.export">Export</span>
                </button>
                <button class="bookshelf-action-btn" id="importShelfBtn">
                    <i class="fas fa-download" aria-hidden="true"></i> <span data-i18n="bookshelf.import">Import</span>
                </button>
                <input type="file" id="importShelfFile" accept=".json" style="display: none;">""" if self.deployment_mode == "ssg" else ""
        safe_book_title = metadata_text(self.book_title)
        book_title_text = html.escape(safe_book_title, quote=False)
        book_title_attribute = html.escape(safe_book_title, quote=True)
        book_id_attribute = html.escape(str(self.book_hash), quote=True)
        book_id_url = urllib.parse.quote(str(self.book_hash), safe='')
        if self.authors:
            authors_text = " & ".join(
                html.escape(metadata_text(author), quote=False)
                for author in self.authors
            )
            authors_html = f'<p class="book-info-author" lang="{book_language}" dir="auto">{authors_text}</p>'
        else:
            authors_html = '<p class="book-info-author" data-i18n="book.unknownAuthor">Unknown author</p>'
        ai_feature_assets = "" if is_pdf_book else self._server_ai_feature_assets()
        book_feature_assets = json.dumps({
            "bookshelf": self.asset_manifest.url_for("bookshelf.js"),
            "annotationHubCss": self.asset_manifest.url_for("annotation-hub.css"),
            "annotation": self.asset_manifest.url_for("annotation.js"),
            "annotationHub": self.asset_manifest.url_for("annotation-hub.js"),
            "sortable": self.asset_manifest.url_for("vendor/sortablejs/sortable.min.js"),
        }, separators=(",", ":"))
        if self.deployment_mode == "server":
            book_feature_assets = json.dumps({
                **json.loads(book_feature_assets),
                "readingInsightsCss": self.asset_manifest.url_for("reading-insights.css"),
                "readingInsights": self.asset_manifest.url_for("reading-insights.js"),
            }, separators=(",", ":"))
        ai_reading_navigation = (
            f'<button type="button" class="app-nav-link" data-ai-reading-hub '
            f'data-book-id="{book_id_attribute}" aria-haspopup="dialog">'
            '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>'
            '<span data-i18n="ai.library">AI readings</span></button>'
            if self.deployment_mode == "server" and not is_pdf_book else ""
        )
        reading_insights_navigation = (
            '<button type="button" class="app-nav-link" data-reading-insights '
            'aria-haspopup="dialog"><i class="fas fa-chart-column" '
            'aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></button>'
            if self.deployment_mode == "server" else ""
        )
        ai_reading_indicators = (
            f' data-ai-reading-indicators data-book-id="{book_id_attribute}"'
            if self.deployment_mode == "server" and not is_pdf_book else ""
        )
        ai_reading_script = (
            '<script src="/assets/ai-feature-loader.js" defer></script>'
            if self.deployment_mode == "server" and not is_pdf_book else ""
        )
        ai_book_chat_button = (
            f'<button type="button" class="css-btn secondary" data-ai-book-chat '
            f'data-book-id="{book_id_attribute}"><i class="fas fa-comments" aria-hidden="true"></i>'
            '<span data-i18n="ai.askBook">Ask AI</span></button>'
            if self.deployment_mode == "server" and not is_pdf_book else ""
        )
        ai_book_chat_script = ""
        book_review_assets = (
            '<link rel="stylesheet" href="' + self.asset_manifest.url_for("book-reviews.css") + '">'
            '<script src="' + self.asset_manifest.url_for("book-reviews.js") + '" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        book_review_panel = (
            f'<div class="book-review-modal" data-book-review-modal hidden>'
            f'<section class="book-review-dialog" id="book-review-dialog" role="dialog" '
            f'aria-modal="true" aria-label="Write review" data-i18n-aria-label="bookReviews.write" tabindex="-1">'
            f'<section data-book-reviews data-book-id="{book_id_attribute}"></section>'
            f'</section></div>'
            if self.deployment_mode == "server" else ""
        )
        # Book reviews are account-private runtime data.  In Server mode the
        # authenticated request may provide the current user's review so the
        # first paint already reserves its final position.  Never use this in
        # SSG output or persist it in the EPUB-derived content cache.
        initial_review = None
        if self.deployment_mode == "server" and isinstance(initial_book_review, dict):
            initial_rating = initial_book_review.get("rating")
            initial_text = initial_book_review.get("review_text")
            if (
                isinstance(initial_rating, int)
                and not isinstance(initial_rating, bool)
                and 1 <= initial_rating <= 5
                and isinstance(initial_text, str)
            ):
                initial_review = {
                    "rating": initial_rating,
                    "review_text": initial_text,
                }
        if self.deployment_mode != "server":
            book_review_display = ""
            book_review_initial_data = ""
        elif initial_review is None:
            book_review_display = (
                f'<section class="book-review-display" data-book-review-display '
                f'data-book-id="{book_id_attribute}" hidden></section>'
            )
            book_review_initial_data = ""
        else:
            review_rating = initial_review["rating"]
            review_text = initial_review["review_text"]
            review_copy = html.escape(review_text, quote=False)
            review_stars = "★★★★★"[:review_rating]
            review_body = (
                f'<p class="book-review-display-copy is-collapsed">{review_copy}</p>'
                f'<button type="button" class="book-review-expand" data-book-review-expand '
                f'aria-expanded="false"{"" if len(review_text) > 100 else " hidden"} '
                f'data-i18n="bookReviews.showMore">Show more</button>'
                if review_text else ""
            )
            book_review_display = f'''<section class="book-review-display" data-book-review-display data-book-id="{book_id_attribute}">
        <div class="book-review-display-header">
            <h2 data-i18n="bookReviews.title">My review</h2>
            <span class="book-review-display-rating" aria-label="{review_rating}/5">
                <span aria-hidden="true">{review_stars}</span><span class="book-review-display-score">{review_rating}/5</span>
            </span>
        </div>
        {review_body}
    </section>'''
            initial_review_json = json.dumps(initial_review, ensure_ascii=False).replace("<", "\\u003c").replace(
                ">", "\\u003e"
            ).replace("&", "\\u0026")
            book_review_initial_data = (
                '<script type="application/json" data-book-review-initial>'
                + initial_review_json
                + '</script>'
            )
        book_review_trigger = (
            '<button type="button" class="css-btn secondary" data-book-review-toggle '
            'aria-controls="book-review-dialog" aria-expanded="false">'
            '<i class="fas fa-pen" aria-hidden="true"></i>'
            '<span data-i18n="bookReviews.write">Write review</span></button>'
            if self.deployment_mode == "server" else ""
        )
        book_reading_time = (
            '<p class="book-reading-time" data-book-reading-time hidden>'
            '<i class="fas fa-chart-column" aria-hidden="true"></i>'
            '<span data-book-reading-time-label></span></p>'
            if self.deployment_mode == "server" else ""
        )
        book_source_format = (
            '<span class="book-source-format" aria-label="PDF" data-i18n-aria-label="pdf.formatBadge" '
            'data-i18n="pdf.formatBadge">PDF</span>'
            if is_pdf_book else ""
        )
        server_account_stylesheet = SERVER_ACCOUNT_STYLESHEET if self.deployment_mode == "server" else ""
        # Locale selection is shared navigation chrome in both SSG and Server.
        server_locale_control = SERVER_LOCALE_CONTROL
        server_account_control = SERVER_ACCOUNT_CONTROL if self.deployment_mode == "server" else ""
        server_account_panel = SERVER_ACCOUNT_PANEL if self.deployment_mode == "server" else ""
        server_locale_script = SERVER_LOCALE_SCRIPT
        index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#244548">
    <meta name="description" content="{book_title_attribute} - EPUB Browser">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="EPUB Browser">
    <title>{book_title_text}</title>
    <script src="/assets/i18n.js"></script>
    <script>window.EpubBrowserI18n.init();</script>
    {ai_feature_assets}
    <noscript><link rel="manifest" href="/assets/manifest.en.json"></noscript>
    <link rel="stylesheet" href="/assets/vendor/fontawesome/css/all.min.css">
    <link rel="stylesheet" href="/assets/theme.css">
    <link rel="stylesheet" href="/assets/notification.css">
    <link rel="stylesheet" href="/assets/dialog.css">
    <link rel="stylesheet" href="/assets/book.css?v=13">
    <link rel="stylesheet" href="/assets/breadcrumb.css?v=3">
    <link rel="stylesheet" href="/assets/loading.css?v=15">
    <link rel="icon" type="image/png" href="/assets/favicon.png">
    <link rel="apple-touch-icon" href="/assets/icon-192.png">
    <link rel="stylesheet" href="/assets/bookshelf.css">
    {server_account_stylesheet}
    {book_review_assets}
"""
        index_html += """
    <script>
    // 立即应用主题，避免闪现 —— Kindle 兼容版
    function isKindleDevice() {
    // 优先从 window 缓存读取
    if (window.epubBrowserCache && window.epubBrowserCache.kindle_mode !== undefined) {
        return window.epubBrowserCache.kindle_mode === "true";
    }
    // 检测设备
    var ua = navigator.userAgent.toLowerCase();
    var isKindle = ua.indexOf("kindle") !== -1 || ua.indexOf("silk") !== -1;
    
    if (!window.epubBrowserCache) {
        window.epubBrowserCache = {};
    }
    window.epubBrowserCache.kindle_mode = isKindle ? "true" : "false";
    return isKindle;
    }

    // 通用 Cookie 方法（只定义一次）
    function getCookie(key) {
    var cookies = document.cookie.split("; ");
    for (var i = 0; i < cookies.length; i++) {
        var parts = cookies[i].split("=");
        var cookieKey = parts[0];
        var cookieValue = parts.slice(1).join("=");
        if (cookieKey === key) {
        return decodeURIComponent(cookieValue);
        }
    }
    return null;
    }

    var theme = "light";
    var isKindle = false;

    try {
    // 优先从 window 缓存读取
    var storedTheme = null;
    if (window.epubBrowserCache && window.epubBrowserCache.theme) {
        storedTheme = window.epubBrowserCache.theme;
    } else {
        storedTheme = localStorage.getItem("theme");
        if (storedTheme) {
        if (!window.epubBrowserCache) {
            window.epubBrowserCache = {};
        }
        window.epubBrowserCache.theme = storedTheme;
        }
    }

    if (storedTheme) {
        theme = storedTheme;
    } else if (isKindleDevice()) {
        isKindle = true;
        theme = getCookie("theme") || "light";
    }
    } catch (e) {
    // 捕获异常，兼容 Kindle
    if (isKindleDevice()) {
        isKindle = true;
        theme = getCookie("theme") || "light";
    }
    }

    // 使用 html 元素添加类名
    var htmlElement = document.documentElement;
    htmlElement.classList.add(theme + "-mode");
    if (isKindle) {
    htmlElement.classList.add("kindle-mode");
    }
    </script>
</head>
<body>
"""
        index_html += f"""
<header class="app-header">
    <nav class="app-nav" aria-label="Book navigation" data-i18n-aria-label="book.navigation">
        <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" width="32" height="32" alt=""><span data-i18n="common.brand">EPUB Browser</span></a>
        <div class="app-nav-links">
            <button type="button" class="app-nav-link" id="bookshelfBtn" aria-haspopup="dialog" aria-controls="bookshelfModal"><i class="fas fa-bookmark" aria-hidden="true"></i><span data-i18n="book.shelf">Shelf</span></button>
            <button type="button" class="app-nav-link" id="bookAnnotationsBtn" data-annotation-hub data-book-hash="{book_id_attribute}" aria-haspopup="dialog"><i class="fas fa-highlighter" aria-hidden="true"></i><span data-i18n="book.annotations">Annotations</span></button>
            {reading_insights_navigation}
            {ai_reading_navigation}
        </div>
        <div class="app-nav-actions">
            {server_locale_control}
            <button class="theme-toggle app-nav-action app-nav-theme" id="themeToggle" type="button" aria-label="Theme" data-i18n-aria-label="book.theme"><i class="fas fa-moon" aria-hidden="true"></i><span class="app-nav-action-label" data-i18n="book.theme">Theme</span></button>
            {server_account_control}
        </div>
    </nav>
</header>
<div class="container">
    <div class="book-info-card" data-id="book-info-card">
            <div class="book-info-cover-wrap">
                <div class="book-info-cover">
                    <img src="{html.escape(self.get_book_info()['cover'], quote=True)}" alt="">
                </div>
                {book_reading_time}
                {book_source_format}
            </div>
            <div class="book-info-content">
                <h2 class="book-info-title" lang="{book_language}" dir="auto">{book_title_text}</h2>
                {authors_html}"""
        if self.description:
            description = sanitize_html_fragment(self.description)
            index_html += f""" 
                <div class="book-info-desc" lang="{book_language}" dir="auto">
                    {description}
                </div>"""
        index_html += f"""
                <div class="book-info-tags" lang="{book_language}" dir="auto">"""
        if self.tags:
            for tag in self.tags:
                tag_text = html.escape(metadata_text(tag), quote=False)
                index_html += """<span class="book-tag">{}</span>""".format(tag_text)
        index_html += f"""
                </div>
                <div class="css-controls clearReadingProgress">
                    <div class="continue-reading-control" id="continueReadingControl">
                        <a class="css-btn primary" id="continueReadingBtn" href="#" aria-label="Start reading" data-i18n-aria-label="book.startReading"><i class="fas fa-book-open"></i><span id="continueReadingBtnText" data-i18n="book.startReading">Start reading</span></a>
                        <button type="button" class="continue-reading-menu-toggle" id="continueReadingMenuToggle" aria-label="More reading actions" data-i18n-aria-label="book.moreReadingActions" aria-expanded="false" aria-controls="clearReadingProgressMenu" hidden><i class="fas fa-chevron-down" aria-hidden="true"></i></button>
                        <div class="continue-reading-menu" id="clearReadingProgressMenu" hidden>
                            <button type="button" class="continue-reading-menu-item" id="clearReadingProgressBtn" aria-label="Clear reading progress" data-i18n-aria-label="book.clearReadingProgress" hidden><i class="fas fa-eraser" aria-hidden="true"></i><span data-i18n="book.clear">Clear</span></button>
                        </div>
                    </div>
                    {ai_book_chat_button}
                    <button class="css-btn secondary" id="toggleShelfBtn"><i class="fas fa-bookmark"></i><span id="toggleShelfBtnText" data-i18n="book.addToShelf">Add to Shelf</span></button>
                    {book_review_trigger}
                </div>
            </div>
    </div>
    {book_review_display}
    {book_review_initial_data}
    {book_review_panel}
    <div class="toc-container" data-id="toc-container"{ai_reading_indicators}>
        <div class="toc-header">
            <h2 data-i18n="book.tableOfContents">Table of contents</h2>
            <div class="chapter-count" data-i18n="book.totalChapters" data-i18n-params='{{"count": {len(self.chapters)}}}'>Total: {len(self.chapters)}</div>
        </div>
        <ul class="chapter-list">
"""
        
        # OPF spine owns public chapter indexes.  EPUB navigation only
        # contributes titles, anchors and non-navigable grouping nodes.
        for toc_item in self._build_toc_data():
            level_class = f"toc-level-{min(toc_item.get('level', 0), 3)}"
            toc_title = html.escape(
                metadata_text(toc_item.get("title")), quote=False
            )
            toc_title_attributes = f' lang="{book_language}" dir="auto"'
            if getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT and toc_item.get('page_label'):
                page_params = html.escape(
                    json.dumps(
                        {'number': toc_item['page_label']},
                        separators=(',', ':'),
                    ),
                    quote=True,
                )
                toc_title_attributes += (
                    f' data-i18n="pdf.page" data-i18n-params="{page_params}"'
                )
            outline_labels_html = ""
            if getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT and toc_item.get('outline_labels'):
                outline_labels = " · ".join(
                    html.escape(metadata_text(label), quote=False)
                    for label in toc_item['outline_labels']
                )
                outline_labels_html = (
                    f'<span class="chapter-outline-labels" lang="{book_language}" '
                    f'dir="auto">{outline_labels}</span>'
                )
            if toc_item.get('kind') == 'section':
                index_html += f'        <li class="{level_class} toc-section"><span class="chapter-section-title" lang="{book_language}" dir="auto">{toc_title}</span></li>\n'
                continue

            chapter_index = toc_item['chapter_index']
            chapter_anchor = toc_item.get('anchor')
            chapter_title_group = (
                f'<span class="chapter-title-with-sync"><span class="chapter-title"'
                f'{toc_title_attributes}>{toc_title}</span>{outline_labels_html}</span>'
            )
            if chapter_anchor is not None:
                safe_anchor = urllib.parse.quote(str(chapter_anchor), safe='')
                index_html += f'        <li class="{level_class}"><a class="chapter-link" href="/book/{book_id_url}/chapter_{chapter_index}.html#{safe_anchor}" id="eb_ci_{chapter_index}#{safe_anchor}" data-chapter-index="{chapter_index}">{chapter_title_group}<span class="chapter-page">chapter_{chapter_index}.html</span></a></li>\n'
            else:
                index_html += f'        <li class="{level_class}"><a class="chapter-link" href="/book/{book_id_url}/chapter_{chapter_index}.html" id="eb_ci_{chapter_index}" data-chapter-index="{chapter_index}">{chapter_title_group}<span class="chapter-page">chapter_{chapter_index}.html</span></a></li>\n'
        
        index_html += f"""    </ul>
    </div>
</div>
<div class="reading-controls" data-id="reading-controls">
    <button class="control-btn" id="scrollToTopBtn" type="button" aria-label="Top" data-i18n-aria-label="book.top">
        <i class="fas fa-arrow-up"></i>
        <span class="control-name" data-i18n="book.top">Top</span>
    </button>
</div>
<!-- 书架弹窗 -->
<div class="bookshelf-modal" id="bookshelfModal" role="dialog" aria-modal="true" aria-labelledby="bookshelfModalTitle">
    <div class="bookshelf-content" tabindex="-1">
        <div class="bookshelf-header">
            <div class="bookshelf-header-left">
                <button class="bookshelf-action-btn" id="addShelfGroupBtn">
                    <i class="fas fa-folder-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addGroup">Add Group</span>
                </button>
                <button class="bookshelf-action-btn" id="addShelfBookBtn">
                    <i class="fas fa-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addBook">Add Book</span>
                </button>
                {bookshelf_data_actions}
            </div>
            <h2 class="bookshelf-title" id="bookshelfModalTitle"><i class="fas fa-home" aria-hidden="true"></i> <span data-i18n="bookshelf.title">Bookshelf</span></h2>
            <div class="bookshelf-header-right">
                <button class="bookshelf-close-btn" id="bookshelfCloseBtn" aria-label="Close" data-i18n-aria-label="bookshelf.close">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
        <div class="bookshelf-loading" id="bookshelfLoading" role="status" aria-label="Loading bookshelf" data-i18n-aria-label="bookshelf.loading">
            <div class="loading-spinner"></div>
        </div>
        <div class="bookshelf-body" id="bookshelfBody">
        </div>
        <div class="bookshelf-footer" id="bookshelfFooter">
            <span id="bookshelfStats"></span>
        </div>
    </div>
</div>

<!-- 分组弹窗 -->
<div class="bookshelf-modal" id="groupModal" role="dialog" aria-modal="true" aria-labelledby="groupModalTitle">
    <div class="bookshelf-content" tabindex="-1">
        <div class="bookshelf-header">
            <div class="bookshelf-header-left">
                <button class="bookshelf-action-btn" id="addGroupSubGroupBtn">
                    <i class="fas fa-folder-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addGroup">Add Group</span>
                </button>
                <button class="bookshelf-action-btn" id="addGroupBookBtn">
                    <i class="fas fa-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addBook">Add Book</span>
                </button>
                <button class="bookshelf-action-btn" id="renameGroupBtn">
                    <i class="fas fa-edit" aria-hidden="true"></i> <span data-i18n="bookshelf.rename">Rename</span>
                </button>
                <button class="bookshelf-action-btn bookshelf-delete-btn" id="deleteGroupBtn">
                    <i class="fas fa-trash" aria-hidden="true"></i> <span data-i18n="bookshelf.deleteGroup">Delete Group</span>
                </button>
            </div>
            <h2 class="bookshelf-title" id="groupModalTitle" data-i18n="bookshelf.group">Group</h2>
            <div class="bookshelf-header-right">
                <button class="bookshelf-close-btn" id="groupCloseBtn" aria-label="Back to bookshelf" data-i18n-aria-label="bookshelf.home">
                    <i class="fas fa-home"></i>
                </button>
                <button class="bookshelf-close-btn" id="groupCloseAllBtn" aria-label="Close" data-i18n-aria-label="bookshelf.close">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
        <div class="bookshelf-loading" id="groupLoading" role="status" aria-label="Loading bookshelf" data-i18n-aria-label="bookshelf.loading">
            <div class="loading-spinner"></div>
        </div>
        <div class="bookshelf-body" id="groupBody">
        </div>
        <div class="bookshelf-footer" id="groupFooter">
            <span id="groupStats"></span>
        </div>
    </div>
</div>
{server_account_panel}
{render_footer(datetime.now().year, release_api_url='/api/version' if self.deployment_mode == 'server' else '')}"""

        cache_boundary_script = (
            '<script src="/assets/cache-boundary.js" defer></script>'
            if self.deployment_mode == "server"
            else ""
        )
        auth_script = (
            SERVER_AUTH_SCRIPT
            if self.deployment_mode == "server"
            else ""
        )
        startup = (
            """function startBookClients() {
    if (!window.EpubBrowserAuth) return;
        window.EpubBrowserAuth.init().then(function(session) {
            if (!session) return;
            if (window.initScriptBook) window.initScriptBook();
            var reviewRoot = document.querySelector('[data-book-reviews]');
            if (reviewRoot && window.EpubBookReviews) {
                window.EpubBookReviews.mount(
                    reviewRoot,
                    reviewRoot.getAttribute('data-book-id'),
                    document.querySelector('[data-book-review-display]')
                );
            }
        });
}
if (window.EpubBrowserCacheBoundary) {
    window.EpubBrowserCacheBoundary.start(startBookClients);
}"""
            if self.deployment_mode == "server"
            else "if (window.initScriptBook) window.initScriptBook();"
        )
        index_html += f"""
{cache_boundary_script}
<script src="/assets/notification.js" defer></script>
{auth_script}
{server_locale_script}
<script src="/assets/theme.js" defer></script>
<script src="/assets/dialog.js" defer></script>
<script src="/assets/version-check.js" defer></script>
<script src="/assets/reading-progress.js" defer></script>
<script src="/assets/reader-layout.js" defer></script>
<script>window.EpubBrowserBookFeatureAssets={book_feature_assets};</script>
<script src="/assets/book-feature-loader.js" defer></script>
<script src="/assets/book.js?v=13" defer></script>
{ai_reading_script}
{ai_book_chat_script}
<script>
document.addEventListener('DOMContentLoaded', function() {{
    {startup}
}});
</script>
</body>
</html>"""
        index_html = rewrite_asset_urls(index_html, self.asset_manifest)
        index_html = self._inject_deployment_mode(index_html)
        index_html = rewrite_root_urls(index_html, self.urls)
        # kindle 支持，不能压缩 css 和 js
        index_html = minify_html.minify(index_html, minify_css=False, minify_js=False)
        if write:
            with open(os.path.join(self.web_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(index_html)
            # 生成目录 JSON 文件
            self.create_toc_json()
        return index_html
    
    def _build_chapter_index_maps(self):
        """构建章节路径到索引的映射（支持多种路径格式）
        
        Returns:
            tuple: (chapter_index_map, chapter_filename_map)
        """
        chapter_index_map = {}
        chapter_filename_map = {}
        for i, chapter in enumerate(self.chapters):
            # 原始路径
            chapter_index_map[chapter['path']] = i
            # 规范化路径（去除 ./ 前缀）
            normalized_path = chapter['path'].lstrip('./').lstrip('/')
            chapter_index_map[normalized_path] = i
            # 文件名匹配
            chapter_filename = posixpath.basename(chapter['path'])
            chapter_filename_map[chapter_filename] = i
        return chapter_index_map, chapter_filename_map
    
    def _find_chapter_index(self, toc_src, chapter_index_map, chapter_filename_map):
        """根据toc_src查找章节索引
        
        Args:
            toc_src: 目录项的src路径
            chapter_index_map: 章节路径到索引的映射
            chapter_filename_map: 章节文件名到索引的映射
            
        Returns:
            int or None: 章节索引，未找到则返回None
        """
        # 1. 直接匹配
        if toc_src in chapter_index_map:
            return chapter_index_map[toc_src]
        # 2. 规范化路径匹配（去除 ./ 前缀）
        elif toc_src.lstrip('./').lstrip('/') in chapter_index_map:
            return chapter_index_map[toc_src.lstrip('./').lstrip('/')]
        # 3. URL解码后匹配（处理%20等编码字符）
        elif urllib.parse.unquote(toc_src) in chapter_index_map:
            return chapter_index_map[urllib.parse.unquote(toc_src)]
        elif urllib.parse.unquote(toc_src).lstrip('./').lstrip('/') in chapter_index_map:
            return chapter_index_map[urllib.parse.unquote(toc_src).lstrip('./').lstrip('/')]
        # 4. 文件名匹配
        elif posixpath.basename(toc_src) in chapter_filename_map:
            return chapter_filename_map[posixpath.basename(toc_src)]
        # 5. URL解码后的文件名匹配
        elif posixpath.basename(urllib.parse.unquote(toc_src)) in chapter_filename_map:
            return chapter_filename_map[posixpath.basename(urllib.parse.unquote(toc_src))]
        return None
    
    def _build_toc_data(self):
        """Return the EPUB-derived table of contents for either publisher."""
        if getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT:
            return [dict(item) for item in self.toc]

        toc_data = []

        def title_key(value):
            return " ".join(metadata_text(value).split()).casefold()

        def chapter_record(title, level, chapter_index, anchor=None):
            record = {
                'title': title,
                'level': level,
                'kind': 'chapter',
                'chapter_index': chapter_index,
                'chapter_file': f'chapter_{chapter_index}.html',
            }
            if anchor is not None:
                record['anchor'] = anchor
            return record
        
        # 如果有详细的toc信息，使用toc生成目录
        if self.toc:
            chapter_index_map, chapter_filename_map = self._build_chapter_index_maps()
            section_indexes_by_title = {}
            for index, chapter in enumerate(self.chapters):
                if chapter.get('is_section_index'):
                    section_indexes_by_title.setdefault(
                        title_key(chapter['title']), []
                    ).append(index)

            used_section_indexes = set()
            represented_indexes = set()
            
            # 根据toc生成目录
            for order, toc_item in enumerate(self.toc):
                if toc_item.get('kind') == 'section' and not toc_item.get('src'):
                    toc_data.append({
                        'title': toc_item['title'],
                        'level': toc_item.get('level', 0),
                        'kind': 'section',
                    })
                    continue
                toc_src = toc_item['src']
                target_index = self._find_chapter_index(
                    toc_src, chapter_index_map, chapter_filename_map
                )
                if toc_item.get('kind', 'chapter') == 'section':
                    # A repeated NCX target is normally only a grouping node.
                    # However, if OPF has a separate linear section-index page
                    # with the same label, that page is a real chapter and
                    # must own its own chapter_N slot.
                    candidates = section_indexes_by_title.get(
                        title_key(toc_item['title']), []
                    )
                    section_index = next(
                        (
                            candidate for candidate in candidates
                            if candidate not in used_section_indexes
                            and (target_index is None or candidate < target_index)
                        ),
                        None,
                    )
                    if section_index is not None:
                        used_section_indexes.add(section_index)
                        represented_indexes.add(section_index)
                        toc_data.append(chapter_record(
                            toc_item['title'],
                            toc_item.get('level', 0),
                            section_index,
                        ))
                    else:
                        # Keep genuinely structural groups, but never let one
                        # claim an OPF chapter index belonging to its child.
                        toc_data.append({
                            'title': toc_item['title'],
                            'level': toc_item.get('level', 0),
                            'kind': 'section',
                        })
                    continue
                chapter_anchor = toc_item.get('anchor', None)
                if target_index is not None:
                    represented_indexes.add(target_index)
                    toc_data.append(chapter_record(
                        toc_item['title'], toc_item.get('level', 0),
                        target_index, chapter_anchor,
                    ))
                else:
                    self.reporter.detail(
                        f"Chapter index not found for toc item: "
                        f"{toc_item['title']} (src: {toc_src})"
                    )

        else:
            # 回退到简单章节列表
            for i, chapter in enumerate(self.chapters):
                toc_data.append(chapter_record(chapter['title'], 0, i))
        
        return toc_data

    def create_toc_json(self):
        """生成目录 JSON 文件到书籍自己的文件夹下"""
        toc_data = self._build_toc_data()
        # 保存为 JSON 文件到书籍自己的文件夹下
        toc_json_path = os.path.join(self.web_dir, 'toc.json')
        with open(toc_json_path, 'w', encoding='utf-8') as f:
            json.dump(toc_data, f, ensure_ascii=False, separators=(',', ':'))
        
        # print(f"TOC JSON file created: {toc_json_path} with {len(toc_data)} items")
    
    def create_chapter_pages(self, write=True):
        """创建章节页面"""
        def create_chapter_page(chapter_path, chapter, i):
            try:
                # 读取章节内容
                with open(chapter_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 处理HTML内容，修复资源链接并提取样式
                body_content, style_links = self.process_html_content(content, chapter['path'])
                
                if self.deployment_mode == "server":
                    self._server_chapter_payloads[i] = {
                        "index": i,
                        "title": chapter['title'],
                        "content": body_content,
                        "style_links": style_links,
                    }
                if write:
                    # Static builds remain self-contained and write their
                    # complete reader page during EPUB conversion.
                    chapter_html = self.create_chapter_template(
                        body_content, style_links, i, chapter['title']
                    )
                    with open(os.path.join(self.web_dir, f'chapter_{i}.html'), 'w', encoding='utf-8') as f:
                        f.write(chapter_html)
                    
            except Exception as e:
                self.reporter.detail(
                    f"Failed to process chapter {chapter['path']}: {e}"
                )
                raise
        
        # 创建并启动线程
        with ThreadPoolExecutor(max_workers=10) as executor:  # 限制最大10个并发线程
            futures = []
            for i, chapter in enumerate(self.chapters):
                chapter_path = self._internal_file(chapter['path'])
                if chapter_path.is_file():
                    # 使用线程池提交任务
                    future = executor.submit(create_chapter_page, chapter_path, chapter, i)
                    futures.append(future)
            for future in futures:
                future.result()

    def _write_server_content_cache(self):
        """Persist only immutable EPUB-derived data for Server mode.

        HTML shells, application navigation, i18n attributes, and app assets
        intentionally stay out of this cache. They are rendered from current
        code for every authenticated reader-page request.
        """
        content_dir = Path(self.web_dir, "content")
        content_dir.mkdir(parents=True, exist_ok=True)
        book_payload = {
            "title": self.book_title,
            "authors": list(self.authors or ()),
            "tags": list(self.tags or ()),
            "description": self.description,
            "epub_identifier": self.epub_identifier,
            "cover_info": self.cover_info,
            "language": self.lang or "en",
            "chapters": self.chapters,
            "toc": self.toc,
            "resources_base": self.resources_base,
        }
        (content_dir / "metadata.json").write_text(
            json.dumps(book_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        (content_dir / "toc.json").write_text(
            json.dumps(self._build_toc_data(), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        if len(self._server_chapter_payloads) != len(self.chapters):
            raise ValueError("Server content cache is missing one or more chapters")
        for index, payload in self._server_chapter_payloads.items():
            (content_dir / f"chapter_{index}.json").write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
                
    
    def process_html_content(self, content, chapter_path):
        """处理HTML内容，修复资源链接并提取样式"""
        # 提取head中的样式链接
        style_links = self.extract_style_links(content, chapter_path)
        
        # 提取body内容
        body_content = self.clean_html_content(content)

        if self.deployment_mode == "server":
            # Rewrite known spine links before the allowlist rejects arbitrary
            # HTML documents. Only generated chapter_N.html links survive.
            body_content = self.fix_html_file_links(body_content, chapter_path)
            body_content = sanitize_html_fragment(body_content)
        
        # 修复body中的图片链接
        body_content = self.fix_image_links(body_content, chapter_path)

        # 修复body 中可能的 html 文件链接，比如有些书有目录页面
        if self.deployment_mode != "server":
            body_content = self.fix_html_file_links(body_content, chapter_path)
        
        # 修复body中的其他资源链接
        body_content = self.fix_other_links(body_content, chapter_path)
        
        return body_content, style_links
    
    def extract_style_links(self, content, chapter_path):
        """从head中提取样式链接"""
        if self.deployment_mode != "server":
            def add_class_to_link(tag, class_name):
                if 'class=' in tag:
                    return re.sub(
                        r'class="([^"]*)"',
                        f'class="\\1 {class_name}"',
                        tag,
                    )
                return tag.replace('<link ', f'<link class="{class_name}" ', 1)

            def add_class_to_style(tag, class_name):
                if 'class=' in tag:
                    return re.sub(
                        r'class="([^"]*)"',
                        f'class="\\1 {class_name}"',
                        tag,
                    )
                return tag.replace('<style', f'<style class="{class_name}"', 1)

            style_links = []
            head_match = re.search(
                r'<head[^>]*>(.*?)</head>',
                content,
                re.DOTALL | re.IGNORECASE,
            )
            if head_match:
                head_content = head_match.group(1)
                links = re.findall(
                    r'<link[^>]+rel=["\']stylesheet["\'][^>]*>',
                    head_content,
                    re.IGNORECASE,
                )
                for link in links:
                    link = add_class_to_link(link, "eb")
                    href_match = re.search(r'href=["\']([^"\']+)["\']', link)
                    if not href_match:
                        continue
                    href = href_match.group(1)
                    if self._is_external_reference(href):
                        style_links.append(link)
                    else:
                        chapter_dir = posixpath.dirname(chapter_path)
                        web_href = self._resource_reference(href, chapter_dir)
                        style_links.append(
                            link.replace(f'href="{href}"', f'href="{web_href}"')
                        )
                styles = re.findall(
                    r'<style[^>]*>.*?</style>',
                    head_content,
                    re.DOTALL,
                )
                for style in styles:
                    style_links.append(add_class_to_style(style, "eb"))
            return '\n        '.join(style_links)

        style_links = []
        
        # 匹配head标签
        head_match = re.search(r'<head[^>]*>(.*?)</head>', content, re.DOTALL | re.IGNORECASE)
        if head_match:
            head_content = head_match.group(1)
            
            # 匹配link标签（CSS样式表）
            link_pattern = r'<link[^>]+rel=["\']stylesheet["\'][^>]*>'
            links = re.findall(link_pattern, head_content, re.IGNORECASE)
            
            for link in links:
                # 提取href属性
                href_match = re.search(
                    r'href\s*=\s*["\']([^"\']+)["\']',
                    link,
                    re.IGNORECASE,
                )
                if href_match:
                    href = href_match.group(1)
                    safe_href = _safe_html_url("link", "href", href)
                    if safe_href and not self._is_external_reference(safe_href):
                        chapter_dir = posixpath.dirname(chapter_path)
                        web_href = self._resource_reference(safe_href, chapter_dir)
                        style_links.append(
                            '<link class="eb" rel="stylesheet" href="{}">'.format(
                                html.escape(web_href, quote=True)
                            )
                        )
            
            # 匹配style标签
            style_pattern = r'<style[^>]*>(.*?)</style>'
            styles = re.findall(style_pattern, head_content, re.DOTALL | re.IGNORECASE)
            for style in styles:
                safe_style = sanitize_css_text(style)
                if safe_style:
                    style_links.append('<style class="eb">{}</style>'.format(safe_style))
        
        return '\n        '.join(style_links)
    
    def clean_html_content(self, content):
        """清理HTML内容"""
        # 提取body内容（如果存在）
        if '<body' in content.lower():
            try:
                # 提取body内容
                start = content.lower().find('<body')
                start = content.find('>', start) + 1
                end = content.lower().find('</body>')
                content = content[start:end]
            except:
                pass
        
        return content
    
    @staticmethod
    def _image_dimensions(path):
        """Return intrinsic dimensions for common EPUB raster resources."""
        try:
            with open(path, "rb") as image:
                header = image.read(32)
                if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
                    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
                if header[:6] in (b"GIF87a", b"GIF89a") and len(header) >= 10:
                    return int.from_bytes(header[6:8], "little"), int.from_bytes(header[8:10], "little")
                if header.startswith(b"\xff\xd8"):
                    image.seek(2)
                    while True:
                        marker_prefix = image.read(1)
                        while marker_prefix == b"\xff":
                            marker_prefix = image.read(1)
                        if not marker_prefix:
                            return None
                        marker = marker_prefix[0]
                        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                            continue
                        length = int.from_bytes(image.read(2), "big")
                        if length < 2:
                            return None
                        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                            values = image.read(5)
                            if len(values) < 5:
                                return None
                            return int.from_bytes(values[3:5], "big"), int.from_bytes(values[1:3], "big")
                        image.seek(length - 2, os.SEEK_CUR)
                if header.startswith(b"RIFF") and header[8:12] == b"WEBP" and len(header) >= 30:
                    kind = header[12:16]
                    if kind == b"VP8X":
                        return (
                            1 + int.from_bytes(header[24:27], "little"),
                            1 + int.from_bytes(header[27:30], "little"),
                        )
                    if kind == b"VP8L" and len(header) >= 25 and header[20] == 0x2F:
                        bits = int.from_bytes(header[21:25], "little")
                        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        except OSError:
            return None
        return None

    def fix_image_links(self, content, chapter_path):
        """修复图片链接"""
        # 匹配img标签的src属性
        img_pattern1 = r'<img[^>]+src="([^"]+)"[^>]*>'
        img_pattern2 = r'<image[^>]+xlink:href="([^"]+)"[^>]*>'
        
        def replace_img_link(match):
            src = match.group(1)

            # 如果已经是绝对路径或数据URI，则不处理
            if self._is_external_reference(src):
                return match.group(0)

            chapter_dir = posixpath.dirname(chapter_path)
            web_src = self._resource_reference(src, chapter_dir)
            tag = match.group(0).replace(f'"{src}"', f'"{web_src}"')
            if tag.lstrip().lower().startswith("<img") and not re.search(r"\b(?:width|height)\s*=", tag, re.IGNORECASE):
                resource_path = self._resolve_internal_path(src, chapter_dir)
                dimensions = self._image_dimensions(os.path.join(self.extract_dir, resource_path))
                if dimensions and all(value > 0 for value in dimensions):
                    width, height = dimensions
                    tag = re.sub(
                        r"(\s*/?>)$",
                        f' width="{width}" height="{height}"\\1',
                        tag,
                    )
            return tag

        replaced_content = re.sub(img_pattern1, replace_img_link, content)
        replaced_content = re.sub(img_pattern2, replace_img_link, replaced_content)
        return replaced_content

    def fix_html_file_links(self, content, chapter_path):
        """修复html/xhtml文件链接"""
        # 根据目录中的文件名做新旧的映射
        old_file2new_file = {}
        for toc_item in self.toc:
            if 'old_file_name' in toc_item and 'new_file_name' in toc_item:
                old_file2new_file[toc_item['old_file_name']] = toc_item['new_file_name']

        # 匹配a标签的href属性
        a_pattern = r'<a[^>]+href="([^"]+)"[^>]*>'

        def replace_a_link(match):
            src = match.group(1)
            parsed_src = urllib.parse.urlsplit(html.unescape(src).strip())

            # Root-relative anchors navigate the web origin rather than the
            # extracted EPUB archive, so they must not enter path resolution.
            if (
                not parsed_src.scheme
                and not parsed_src.netloc
                and parsed_src.path.startswith("/")
            ):
                return match.group(0)

            # 如果已经是绝对路径或数据URI，则不处理
            if self._is_external_reference(src):
                return match.group(0)
            if self.deployment_mode == "server" and parsed_src.scheme:
                # The final allowlist removes active schemes. Avoid resolving
                # them as EPUB-internal paths before that pass.
                return match.group(0)

            chapter_dir = posixpath.dirname(chapter_path)
            self._resolve_internal_path(src, chapter_dir)
            
            # 如果有 old_file_name 则替换
            new_src = None
            for key, value in old_file2new_file.items():
                if key in src and value is not None:
                    # 直接新文件+旧 Hash，因为原来的地址可能类似 ../contents/chapterchapter_15.html#annot5
                    new_src = value
                    if '#' in src:
                        anchor = src.split('#')[1]
                        new_src += f'#{anchor}'
                    break
            
            if not new_src:
                return match.group(0)
            
            # 转换为web资源路径，这里的 html 资源不会在 resources 下，直接就在当前电子书下
            web_src = f"{new_src}"
            return match.group(0).replace(f'"{src}"', f'"{web_src}"')

        replaced_content = re.sub(a_pattern, replace_a_link, content)
        return replaced_content
    
    def fix_other_links(self, content, chapter_path):
        """修复其他资源链接"""
        # 匹配其他可能包含资源链接的属性
        link_patterns = [
            (r'url\(\s*[\'"]?([^\'"\)]+)[\'"]?\s*\)', 'url'),  # CSS中的url()
        ]
        
        for pattern, attr_type in link_patterns:
            def replace_other_link(match):
                url = match.group(1)
                # 如果已经是绝对路径或数据URI，则不处理
                if self._is_external_reference(url):
                    return match.group(0)

                chapter_dir = posixpath.dirname(chapter_path)
                web_url = self._resource_reference(url, chapter_dir)
                return match.group(0).replace(url, web_url)
            
            content = re.sub(pattern, replace_other_link, content)
        
        return content
    
    def create_pdf_chapter_template(self, chapter_index: int, document_url: str) -> str:
        """Render one PDF page through the canonical chapter template."""
        try:
            page = self._pdf_pages[chapter_index]
            chapter = self.chapters[chapter_index]
        except (AttributeError, IndexError):
            raise ValueError(f"PDF chapter index is out of range: {chapter_index}") from None
        return self.create_chapter_template(
            "",
            "",
            chapter_index,
            chapter["title"],
            pdf_page={
                "document_url": document_url,
                "page_number": page.page_number,
                "width": page.width,
                "height": page.height,
                "encrypted": self._pdf_encrypted,
                "has_extractable_text": self._pdf_has_extractable_text,
            },
        )

    def create_chapter_template(
        self,
        content,
        style_links,
        chapter_index,
        chapter_title,
        pdf_page=None,
    ):
        """创建章节页面模板"""
        if self.deployment_mode == "server":
            content = sanitize_html_fragment(content)
        book_id_url = urllib.parse.quote(str(self.book_hash), safe='')
        book_id_attribute = html.escape(str(self.book_hash), quote=True)
        safe_book_title = metadata_text(self.book_title)
        safe_chapter_title = metadata_text(chapter_title)
        book_title_text = html.escape(safe_book_title, quote=False)
        book_title_attribute = html.escape(safe_book_title, quote=True)
        chapter_title_text = html.escape(safe_chapter_title, quote=False)
        chapter_title_attribute = html.escape(safe_chapter_title, quote=True)
        pdf_config_script = ""
        pdf_stylesheet = ""
        pdf_chapter_script = ""
        pdf_reader_controls = ""
        pdf_mobile_controls = ""
        pdf_search_drawer = ""
        page_width_control_attribute = ""
        page_width_slider_attributes = 'min="1" max="4" value="3" step="1"'
        page_width_value_control = ""
        page_width_scale = '''
                            <span data-i18n="settings.pageWidthNarrow">Narrow</span>
                            <span data-i18n="settings.pageWidthComfortable">Comfortable</span>
                            <span data-i18n="settings.pageWidthWide">Wide</span>
                            <span data-i18n="settings.pageWidthExtraWide">Extra wide</span>'''
        if pdf_page is not None:
            page_number = int(pdf_page["page_number"])
            total_pages = len(self.chapters)
            page_params = html.escape(
                json.dumps(
                    {"number": page_number, "total": total_pages},
                    separators=(",", ":"),
                ),
                quote=True,
            )
            content = (
                '<div class="pdf-page-content"'
                f' data-pdf-page-number="{page_number}"'
                f' data-pdf-page-width="{html.escape(str(pdf_page["width"]), quote=True)}"'
                f' data-pdf-page-height="{html.escape(str(pdf_page["height"]), quote=True)}"'
                f' data-pdf-encrypted="{str(bool(pdf_page["encrypted"])).lower()}"'
                f' data-pdf-has-extractable-text="{str(bool(pdf_page["has_extractable_text"])).lower()}"'
                ' data-pdf-loading-message-key="pdf.loadingPage"'
                ' data-pdf-text-unavailable-message-key="pdf.textUnavailable"'
                ' data-pdf-password-required-message-key="pdf.passwordRequired"'
                f' aria-label="Page {page_number} of {total_pages}"'
                ' data-i18n-aria-label="pdf.pageOf"'
                f' data-i18n-params="{page_params}"></div>'
            )
            pdf_config = json.dumps(
                {
                    "documentUrl": str(pdf_page["document_url"]),
                    "pdfjsModuleUrl": self.asset_manifest.url_for(
                        "vendor/pdfjs/build/pdf.mjs"
                    ),
                    "pdfjsWorkerUrl": self.asset_manifest.url_for(
                        "vendor/pdfjs/build/pdf.worker.mjs"
                    ),
                    "encrypted": bool(self._pdf_encrypted),
                    "hasExtractableText": bool(self._pdf_has_extractable_text),
                },
                separators=(",", ":"),
            )
            pdf_config = (
                pdf_config.replace("&", "\\u0026")
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
            )
            pdf_config_script = f"<script>window.EpubPDFConfig={pdf_config};</script>"
            pdf_stylesheet = (
                '<link rel="stylesheet" href="'
                + self.asset_manifest.url_for("pdf-chapter.css")
                + '">'
            )
            pdf_chapter_script = (
                '<script src="'
                + self.asset_manifest.url_for("pdf-chapter.js")
                + '" defer></script>'
            )
            pdf_reader_controls = '''
            <span class="pdf-chapter-actions" data-pdf-actions>
                <button class="control-btn" id="pdfSearchToggle" type="button" aria-label="Search PDF" data-i18n-aria-label="pdf.search" aria-controls="pdfSearchDrawer" aria-expanded="false"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.search">Search PDF</span></button>
                <button class="control-btn" id="pdfZoomOut" type="button" aria-label="Zoom out" data-i18n-aria-label="pdf.zoomOut"><i class="fas fa-magnifying-glass-minus" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.zoomOut">Zoom out</span></button>
                <button class="control-btn" id="pdfZoomIn" type="button" aria-label="Zoom in" data-i18n-aria-label="pdf.zoomIn"><i class="fas fa-magnifying-glass-plus" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.zoomIn">Zoom in</span></button>
                <button class="control-btn" id="pdfFitWidth" type="button" aria-label="Fit width" data-i18n-aria-label="pdf.fitWidth" aria-pressed="false"><i class="fas fa-arrows-left-right" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.fitWidth">Fit width</span></button>
                <button class="control-btn" id="pdfFitPage" type="button" aria-label="Fit page" data-i18n-aria-label="pdf.fitPage" aria-pressed="false"><i class="fas fa-maximize" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.fitPage">Fit page</span></button>
                <button class="control-btn" id="pdfRotate" type="button" aria-label="Rotate page" data-i18n-aria-label="pdf.rotate"><i class="fas fa-rotate-right" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.rotate">Rotate page</span></button>
            </span>'''
            pdf_mobile_controls = '''
        <button class="control-btn" id="mobilePdfSearchToggle" type="button" aria-label="Search PDF" title="Search PDF" data-i18n-aria-label="pdf.search" data-i18n-title="pdf.search" aria-controls="pdfSearchDrawer" aria-expanded="false"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><span data-i18n="pdf.search">Search PDF</span></button>
        <button class="control-btn" id="mobilePdfZoomOut" type="button" aria-label="Zoom out" title="Zoom out" data-i18n-aria-label="pdf.zoomOut" data-i18n-title="pdf.zoomOut"><i class="fas fa-magnifying-glass-minus" aria-hidden="true"></i><span data-i18n="pdf.zoomOut">Zoom out</span></button>
        <button class="control-btn" id="mobilePdfZoomIn" type="button" aria-label="Zoom in" title="Zoom in" data-i18n-aria-label="pdf.zoomIn" data-i18n-title="pdf.zoomIn"><i class="fas fa-magnifying-glass-plus" aria-hidden="true"></i><span data-i18n="pdf.zoomIn">Zoom in</span></button>
        <button class="control-btn" id="mobilePdfFitWidth" type="button" aria-label="Fit width" title="Fit width" data-i18n-aria-label="pdf.fitWidth" data-i18n-title="pdf.fitWidth" aria-pressed="false"><i class="fas fa-arrows-left-right" aria-hidden="true"></i><span data-i18n="pdf.fitWidth">Fit width</span></button>
        <button class="control-btn" id="mobilePdfFitPage" type="button" aria-label="Fit page" title="Fit page" data-i18n-aria-label="pdf.fitPage" data-i18n-title="pdf.fitPage" aria-pressed="false"><i class="fas fa-maximize" aria-hidden="true"></i><span data-i18n="pdf.fitPage">Fit page</span></button>
        <button class="control-btn" id="mobilePdfRotate" type="button" aria-label="Rotate page" title="Rotate page" data-i18n-aria-label="pdf.rotate" data-i18n-title="pdf.rotate"><i class="fas fa-rotate-right" aria-hidden="true"></i><span data-i18n="pdf.rotate">Rotate page</span></button>'''
            pdf_search_drawer = '''
    <nav class="toc-floating reader-drawer pdf-search-drawer" id="pdfSearchDrawer" aria-label="Search PDF" data-i18n-aria-label="pdf.search" aria-hidden="true">
        <div class="toc-header">
            <h3 data-i18n="pdf.search">Search PDF</h3>
            <button class="toc-close" id="pdfSearchClose" type="button" aria-label="Close PDF search" data-i18n-aria-label="pdf.closeSearch"><i class="fas fa-times" aria-hidden="true"></i></button>
        </div>
        <form class="pdf-search-form" id="pdfSearchForm" role="search">
            <label class="visually-hidden" for="pdfSearchInput" data-i18n="pdf.search">Search PDF</label>
            <input id="pdfSearchInput" type="search" autocomplete="off" placeholder="Search PDF" data-i18n-placeholder="pdf.searchPlaceholder">
            <button class="control-btn" type="submit" aria-label="Search PDF" data-i18n-aria-label="pdf.search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i></button>
        </form>
        <ul class="toc-list pdf-search-results" id="pdfSearchResults" aria-live="polite"></ul>
    </nav>'''
            page_width_control_attribute = " data-pdf-zoom-control"
            page_width_slider_attributes = 'min="25" max="400" value="100" step="1"'
            page_width_value_control = '''
                        <label class="pdf-zoom-value" for="pageWidthValue">
                            <input id="pageWidthValue" type="number" min="25" max="400" value="100" step="1" aria-label="Page width" data-i18n-aria-label="settings.pageWidth">
                            <span aria-hidden="true">%</span>
                        </label>'''
            page_width_scale = '''
                            <span>25%</span>
                            <span>100%</span>
                            <span>200%</span>
                            <span>400%</span>'''
        font_size_control = "" if pdf_page is not None else '''
                <div class="settings-group">
                    <label class="settings-label" for="fontSizeSlider" data-i18n="settings.fontSize">Font size</label>
                    <div class="font-size-control">
                        <input type="range" id="fontSizeSlider" min="1" max="7" value="3" step="1">
                        <div class="font-size-scale">
                            <span class="scale-mark major"></span>
                            <span class="scale-mark"></span>
                            <span class="scale-mark"></span>
                            <span class="scale-mark major"></span>
                            <span class="scale-mark"></span>
                            <span class="scale-mark"></span>
                            <span class="scale-mark major"></span>
                        </div>
                    </div>
                </div>'''
        sync_shelf_button = (
            ""
            if self.deployment_mode == "server"
            else '''<button class="bookshelf-action-btn" id="syncShelfBtn">
                        <i class="fas fa-sync" aria-hidden="true"></i> <span data-i18n="bookshelf.sync">Sync</span>
                    </button>'''
        )
        ai_chapter_button = (
            '<button class="control-btn" type="button" aria-label="AI reading" '
            'data-i18n-aria-label="ai.chapterRead" data-ai-learning-canvas aria-pressed="false" '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}">'
            '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>'
            '<span class="control-name" data-i18n="ai.chapterRead">AI reading</span></button>'
            if self.deployment_mode == "server" and pdf_page is None
            else ""
        )
        ai_followup_button = (
            '<button class="control-btn" type="button" aria-label="Ask AI" '
            'data-i18n-aria-label="ai.askChapter" data-ai-followup-drawer '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}">'
            '<i class="fas fa-comments" aria-hidden="true"></i>'
            '<span class="control-name" data-i18n="ai.askChapter">Ask AI</span></button>'
            if self.deployment_mode == "server" and pdf_page is None
            else ""
        )
        ai_feature_assets = (
            self._server_ai_feature_assets()
            if pdf_page is None else ""
        )
        ai_reading_navigation = (
            f'<button type="button" class="app-nav-link" data-ai-reading-hub '
            f'data-book-id="{book_id_attribute}" aria-haspopup="dialog">'
            '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>'
            '<span data-i18n="ai.library">AI readings</span></button>'
            if self.deployment_mode == "server" and pdf_page is None else ""
        )
        reading_insights_navigation = (
            '<button type="button" class="app-nav-link" data-reading-insights '
            'aria-haspopup="dialog"><i class="fas fa-chart-column" '
            'aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></button>'
            if self.deployment_mode == "server" else ""
        )
        ai_reading_indicators = (
            f' data-ai-reading-indicators data-book-id="{book_id_attribute}"'
            if self.deployment_mode == "server" and pdf_page is None else ""
        )
        mobile_ai_reading_button = (
            '<button class="control-btn" id="mobileAIReadingBtn" type="button" '
            'data-ai-learning-canvas aria-pressed="false" '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}" '
            'aria-label="AI reading" title="AI reading" '
            'data-i18n-aria-label="ai.chapterRead" data-i18n-title="ai.chapterRead">'
            '<i class="fas fa-wand-magic-sparkles"></i>'
            '<span data-i18n="ai.chapterRead">AI reading</span></button>'
            if self.deployment_mode == "server" and pdf_page is None else ""
        )
        mobile_ai_followup_button = (
            '<button class="control-btn" id="mobileAIChatBtn" type="button" '
            'data-ai-followup-drawer '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}" '
            'aria-label="Ask AI" title="Ask AI" '
            'data-i18n-aria-label="ai.askChapter" data-i18n-title="ai.askChapter">'
            '<i class="fas fa-comments" aria-hidden="true"></i>'
            '<span data-i18n="ai.askChapter">Ask AI</span></button>'
            if self.deployment_mode == "server" and pdf_page is None else ""
        )
        ai_chapter_scripts = (
            '<script src="/assets/ai-feature-loader.js" defer></script>'
            if self.deployment_mode == "server" and pdf_page is None else ""
        )
        dictionary_assets = (
            '<link rel="stylesheet" href="/assets/dictionary.css">\n'
            '<script src="/assets/dictionary.js" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        reading_session_context = (
            f'<meta data-reading-session data-book-id="{book_id_attribute}" '
            f'data-chapter-index="{chapter_index}" data-chapter-label="{chapter_title_attribute}">'
            if self.deployment_mode == "server" else ""
        )
        reading_session_script = (
            '<script src="' + self.asset_manifest.url_for("reading-sessions.js") + '" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        server_account_stylesheet = SERVER_ACCOUNT_STYLESHEET if self.deployment_mode == "server" else ""
        # Locale selection is shared navigation chrome in both SSG and Server.
        server_locale_control = SERVER_LOCALE_CONTROL
        server_account_control = SERVER_ACCOUNT_CONTROL if self.deployment_mode == "server" else ""
        server_account_panel = SERVER_ACCOUNT_PANEL if self.deployment_mode == "server" else ""
        server_locale_script = SERVER_LOCALE_SCRIPT
        prev_href = f'href="/book/{book_id_url}/chapter_{chapter_index-1}.html"' if chapter_index > 0 else ''
        next_href = f'href="/book/{book_id_url}/chapter_{chapter_index+1}.html"' if chapter_index < len(self.chapters) - 1 else ''
        prev_link = f'<a {prev_href} aria-label="Previous chapter" data-i18n-aria-label="reader.previous" class="prev-chapter"> <div class="control-btn"> <i class="fas fa-arrow-left"></i><span class="control-name" data-i18n="reader.previous">Previous chapter</span></div></a>'
        next_link = f'<a {next_href} aria-label="Next chapter" data-i18n-aria-label="reader.next" class="next-chapter"> <div class="control-btn"> <i class="fas fa-arrow-right"></i><span class="control-name" data-i18n="reader.next">Next chapter</span></div></a>'
        prev_link_mobile = f'<a {prev_href} aria-label="Previous chapter" title="Previous chapter" data-i18n-aria-label="reader.previous" data-i18n-title="reader.previous"> <div class="control-btn" aria-label="Previous chapter" data-i18n-aria-label="reader.previous"> <i class="fas fa-arrow-left"></i><span data-i18n="reader.previous">Previous chapter</span></div></a>'
        next_link_mobile = f'<a {next_href} aria-label="Next chapter" title="Next chapter" data-i18n-aria-label="reader.next" data-i18n-title="reader.next"> <div class="control-btn" aria-label="Next chapter" data-i18n-aria-label="reader.next"> <i class="fas fa-arrow-right"></i><span data-i18n="reader.next">Next chapter</span></div></a>'
        bookshelf_data_actions = """
                    <button class="bookshelf-action-btn" id="exportShelfBtn">
                        <i class="fas fa-upload" aria-hidden="true"></i> <span data-i18n="bookshelf.export">Export</span>
                    </button>
                    <button class="bookshelf-action-btn" id="importShelfBtn">
                        <i class="fas fa-download" aria-hidden="true"></i> <span data-i18n="bookshelf.import">Import</span>
                    </button>
                    <input type="file" id="importShelfFile" accept=".json" style="display: none;">""" if self.deployment_mode == "ssg" else ""
        
        chapter_html =  f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#244548">
    <meta name="description" content="{chapter_title_attribute} - {book_title_attribute} - EPUB Browser">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="EPUB Browser">
    <title>{chapter_title_text} - {book_title_text}</title>
    {reading_session_context}
    <script src="/assets/i18n.js"></script>
    <script>window.EpubBrowserI18n.init();</script>
    {pdf_config_script}
    {ai_feature_assets}
    <noscript><link rel="manifest" href="/assets/manifest.en.json"></noscript>
    {style_links}
    <link id="code-light" rel="stylesheet" href="/assets/vendor/highlight/github.min.css">
    <link id="code-dark" rel="stylesheet" disabled href="/assets/vendor/highlight/github-dark.min.css">
    <link rel="stylesheet" href="/assets/vendor/fontawesome/css/all.min.css">
    <link rel="stylesheet" href="/assets/theme.css">
    <link rel="stylesheet" href="/assets/notification.css">
    <link rel="stylesheet" href="/assets/dialog.css">
    <link rel="stylesheet" href="/assets/chapter.css?v=17">
    {pdf_stylesheet}
    <link rel="stylesheet" href="/assets/breadcrumb.css?v=3">
    <link rel="stylesheet" href="/assets/loading.css?v=15">
    <link rel="stylesheet" href="/assets/annotation.css">
    <link rel="stylesheet" href="/assets/annotation-hub.css">
    {server_account_stylesheet}
    <link rel="stylesheet" href="/assets/vendor/glightbox/glightbox.min.css">
    <link rel="icon" type="image/png" href="/assets/favicon.png">
    <link rel="apple-touch-icon" href="/assets/icon-192.png">
    <link rel="stylesheet" href="/assets/bookshelf.css">
"""
        chapter_html += """
    <script>
    // 立即应用主题，避免闪现 —— Kindle 兼容版
    function isKindleDevice() {
    // 优先从 window 缓存读取
    if (window.epubBrowserCache && window.epubBrowserCache.kindle_mode !== undefined) {
        return window.epubBrowserCache.kindle_mode === "true";
    }
    // 检测设备
    var ua = navigator.userAgent.toLowerCase();
    var isKindle = ua.indexOf("kindle") !== -1 || ua.indexOf("silk") !== -1;
    
    if (!window.epubBrowserCache) {
        window.epubBrowserCache = {};
    }
    window.epubBrowserCache.kindle_mode = isKindle ? "true" : "false";
    return isKindle;
    }

    // 通用 Cookie 方法（只定义一次）
    function getCookie(key) {
    var cookies = document.cookie.split("; ");
    for (var i = 0; i < cookies.length; i++) {
        var parts = cookies[i].split("=");
        var cookieKey = parts[0];
        var cookieValue = parts.slice(1).join("=");
        if (cookieKey === key) {
        return decodeURIComponent(cookieValue);
        }
    }
    return null;
    }

    var theme = "light";
    var isKindle = false;

    try {
    // 优先从 window 缓存读取
    var storedTheme = null;
    if (window.epubBrowserCache && window.epubBrowserCache.theme) {
        storedTheme = window.epubBrowserCache.theme;
    } else {
        storedTheme = localStorage.getItem("theme");
        if (storedTheme) {
        if (!window.epubBrowserCache) {
            window.epubBrowserCache = {};
        }
        window.epubBrowserCache.theme = storedTheme;
        }
    }

    if (storedTheme) {
        theme = storedTheme;
    } else if (isKindleDevice()) {
        isKindle = true;
        theme = getCookie("theme") || "light";
    }
    } catch (e) {
    // 捕获异常，兼容 Kindle
    if (isKindleDevice()) {
        isKindle = true;
        theme = getCookie("theme") || "light";
    }
    }

    // 使用 html 元素添加类名
    var htmlElement = document.documentElement;
    htmlElement.classList.add(theme + "-mode");
    if (isKindle) {
    htmlElement.classList.add("kindle-mode");
    }
    </script>
</head>
"""
        chapter_html +=f"""
<body{(' class="pdf-source"' if pdf_page is not None else '')}>

    <a class="skip-link" href="#eb-content" data-i18n="reader.skipToContent">Skip to reading content</a>

    <div class="reading-progress-container">
        <div class="progress-bar" id="progressBar"></div>
    </div>

    <nav class="toc-floating reader-drawer" id="bookHomeFloating" aria-label="Book chapters" data-i18n-aria-label="reader.bookChapters" aria-hidden="true"{ai_reading_indicators}>
        <div class="toc-header">
            <h3 data-i18n="reader.bookChapters">Chapters</h3>
            <div class="toc-header-actions">
                <button class="toc-current-chapter" id="bookHomeLocateCurrent" type="button" aria-label="Locate current chapter" data-i18n-aria-label="reader.locateCurrentChapter">
                    <i class="fas fa-crosshairs" aria-hidden="true"></i>
                </button>
                <a class="toc-book-home" href="index.html" aria-label="Open book home" data-i18n-aria-label="reader.openBookHome">
                    <i class="fas fa-book" aria-hidden="true"></i><span data-i18n="reader.openBookHome">Open book home</span>
                </a>
                <button class="toc-close" id="bookHomeClose" type="button" aria-label="Close book home" data-i18n-aria-label="reader.closeBookHome">
                    <i class="fas fa-times" aria-hidden="true"></i>
                </button>
            </div>
        </div>
        <ul class="toc-list" id="bookHomeTocList">
            <!-- 动态生成的书籍目录将放在这里 -->
        </ul>
    </nav>

    <nav class="toc-floating reader-drawer" id="tocFloating" aria-label="This chapter contents" data-i18n-aria-label="reader.thisChapterContents" aria-hidden="true"{ai_reading_indicators}>
        <div class="toc-header">
            <h3 data-i18n="reader.thisChapterContents">This chapter</h3>
            <button class="toc-close" id="tocClose" aria-label="Close table of contents" data-i18n-aria-label="reader.closeTableOfContents">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <ul class="toc-list" id="tocList">
            <!-- 动态生成的目录将放在这里 -->
        </ul>
    </nav>
    {pdf_search_drawer}

    <div class="reader-drawer-backdrop" id="readerDrawerBackdrop" aria-hidden="true"></div>

    <header class="chapter-top-bar app-header">
        <nav class="app-nav" aria-label="Reading navigation" data-i18n-aria-label="reader.navigation">
            <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" width="32" height="32" alt=""><span data-i18n="common.brand">EPUB Browser</span></a>
            <div class="app-nav-links">
                <button type="button" class="app-nav-link" id="bookshelfBtn" aria-haspopup="dialog" aria-controls="bookshelfModal"><i class="fas fa-bookmark" aria-hidden="true"></i><span data-i18n="reader.shelf">Shelf</span></button>
                <button type="button" class="app-nav-link" id="chapterAnnotationsBtn" data-annotation-hub data-book-hash="{book_id_attribute}" aria-haspopup="dialog"><i class="fas fa-highlighter" aria-hidden="true"></i><span data-i18n="reader.annotations">Annotations</span></button>
                {reading_insights_navigation}
                {ai_reading_navigation}
            </div>
            <div class="app-nav-actions">
                {server_locale_control}
                <button class="theme-toggle app-nav-action app-nav-theme" id="themeToggle" type="button" aria-label="Theme" data-i18n-aria-label="reader.theme"><i class="fas fa-moon" aria-hidden="true"></i><span class="app-nav-action-label" data-i18n="reader.theme">Theme</span></button>
                {server_account_control}
            </div>
        </nav>
    </header>
    <div class="container">
        <div class="reader-toolbar top-controls chapter-tools" role="toolbar" aria-label="Reading tools" data-i18n-aria-label="reader.navigation">
            <button class="control-btn" id="bookHomeToggle" type="button" aria-label="Open book chapters" data-i18n-aria-label="reader.openBookChapters" aria-controls="bookHomeFloating" aria-expanded="false"><i class="fas fa-book"></i><span class="control-name" data-i18n="reader.bookChapters">Chapters</span></button>
            <button class="control-btn" id="tocToggle" type="button" aria-label="This chapter contents" data-i18n-aria-label="reader.thisChapterContents" aria-controls="tocFloating" aria-expanded="false"><i class="fas fa-list"></i><span class="control-name" data-i18n="reader.thisChapterContents">This chapter</span></button>
            <button class="control-btn" id="settingsControlBtn" type="button" aria-label="Settings" data-i18n-aria-label="reader.settings" aria-controls="settingsModal" aria-expanded="false"><i class="fas fa-cog"></i><span class="control-name" data-i18n="reader.settings">Settings</span></button>
            {pdf_reader_controls}
            {ai_chapter_button}
            {ai_followup_button}
        </div>
        <div class="eb-content-container" id="eb-content-container" data-id="eb-content-container">
            <div class="content-loading is-visible" id="contentLoading" aria-live="polite" aria-label="Loading content" data-i18n-aria-label="reader.loadingContent">
                <div class="loading-spinner"></div>
            </div>
            <article class="eb-content" id="eb-content" lang="{html.escape(self.lang or 'en', quote=True)}" dir="auto" data-eb-styles data-chapter-index="{chapter_index}" data-chapter-title="{chapter_title_attribute}" data-book-hash="{book_id_attribute}" data-total-chapters="{len(self.chapters)}">
            {content}
            </article>
        </div>

        <div class="navigation" data-id="navigation">
            {prev_link}
            <a href="/book/{book_id_url}/index.html" aria-label="Book" data-i18n-aria-label="reader.book" id="navigationHomeBtn">
                <div class="control-btn">
                    <i class="fas fa-book"></i>
                    <span class="control-name" data-i18n="reader.book">Book</span>
                </div>
            </a>

            <div id="paginationInfo" style="display: none;">
                <button class="control-btn pagination-mode-exit" id="exitPaginationMode" type="button" aria-label="Exit page-turning mode" data-i18n-aria-label="settings.exitPaginationMode" title="Exit page-turning mode" data-i18n-title="settings.exitPaginationMode">
                    <i class="fas fa-scroll"></i>
                    <span class="control-name" data-i18n="settings.exitPaginationMode">Exit page-turning mode</span>
                </button>
                <div class="control-btn" id="prevPage" style="padding-right: 40px;">
                    <i class="fas fa-chevron-left"></i>
                    <span class="control-name" data-i18n="reader.previousPage">Previous page</span>
                </div>
                <div style="display: flex; flex-direction: row;">
                    <span class="page-indicator">
                        <span id="currentPage" style="display:none;"></span>
                        <input type="number" style="margin-right:2px;" id="pageJumpInput" min="1" max="1" value="1" aria-label="Current page" data-i18n-aria-label="reader.currentPage"> / <span id="totalPages" aria-label="Total pages" data-i18n-aria-label="reader.totalPages">1</span>
                    </span>
                    <div class="control-btn" style="padding-left:10px;" id="goToPage" title="Jump" data-i18n-title="reader.jump">
                        <i class="fas fa-arrow-right-to-bracket"></i>
                        <span class="control-name" data-i18n="reader.jump">Jump</span>
                    </div>
                    <div class="control-btn" id="toggleClickPage" title="Click to turn page" data-i18n-title="reader.clickToTurn">
                        <i class="fas fa-hand-pointer"></i>
                        <span class="control-name" data-i18n="reader.clickToTurn">Click to turn page</span>
                    </div>
                    <!-- Pure button only for desktop -->
                    <div class="control-btn desktop-only" id="togglePureMode" title="Pure reading mode" data-i18n-title="reader.pureReading">
                        <i class="fas fa-book-open"></i>
                        <span class="control-name" data-i18n="reader.pureReading">Pure reading mode</span>
                    </div>
                    <!-- Reload button for pagination mode -->
                    <div class="control-btn" id="reloadPages" title="Reload pages" data-i18n-title="reader.reloadPages">
                        <i class="fas fa-rotate-right"></i>
                        <span class="control-name" data-i18n="reader.reloadPages">Reload pages</span>
                    </div>
                </div>
                <div style="display: none; flex-direction: row;" class="page-height-adjustment">
                    <span>
                        <input type="number" style="margin-right:10px;" id="pageHeightInput" value="1" aria-label="Page height" data-i18n-aria-label="reader.pageHeight">
                    </span>
                    <div class="control-btn" id="setPageHeight" style="padding: 0;" title="Set page height" data-i18n-title="reader.setPageHeight">
                        <i class="fas fa-ruler-vertical"></i>
                        <span class="control-name" data-i18n="reader.setPageHeight">Set page height</span>
                    </div>
                </div>
                <div class="control-btn" id="nextPage" style="padding-left: 40px;">
                    <i class="fas fa-chevron-right"></i>
                    <span class="control-name" data-i18n="reader.nextPage">Next page</span>
                </div>
            </div>
            {next_link}
        </div>
    </div>

    <div class="settings-overlay" id="settingsOverlay" data-id="settingsOverlay" aria-hidden="true"></div>
    <div class="settings-modal" id="settingsModal" data-id="settingsModal" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="settingsModalTitle">
        <div class="settings-header">
            <h2 class="settings-header-title" id="settingsModalTitle">
                <i class="fas fa-cog" aria-hidden="true"></i>
                <span data-i18n="reader.settings">Settings</span>
            </h2>
            <button class="settings-close-btn" id="settingsCloseBtn" type="button" aria-label="Close settings" data-i18n-aria-label="reader.closeSettings">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="settings-tabs">
            <button class="settings-tab active" data-tab="font">
                <i class="fas fa-font"></i>
                <span data-i18n="settings.appearance">Appearance</span>
            </button>
            <button class="settings-tab" data-tab="reading">
                <i class="fas fa-book-reader"></i>
                <span data-i18n="settings.reading">Reading</span>
            </button>
        </div>
        <div class="settings-content">
            <div class="settings-tab-panel active" id="font-tab">
                <div class="settings-group">
                    <label class="settings-label" data-i18n="settings.fontFamily">Font family</label>
        <div class="font-family-selector">
            <select id="fontFamilySelect">
                <option value="ebook-default" selected data-i18n="settings.bookDefault">Book default</option>
                <option value="system-ui, -apple-system, sans-serif" data-i18n="settings.systemDefault">System default</option>
                <option value="custom" data-i18n="settings.customByInput">Custom by input</option>
            </select>
        </div>
        <div class="custom-font-input" id="customFontInput" style="display: none;">
            <input type="text" id="customFontFamily" placeholder="Input font name here" data-i18n-placeholder="settings.customFontPlaceholder">
            <small data-i18n="settings.customFontTip">Tip: Font family applies globally. Ensure it’s installed in the system.</small>
            <button class="css-btn primary" id="applyFontSettings">
                <i class="fas fa-check"></i> <span data-i18n="settings.apply">Apply</span>
            </button>
        </div>
                </div>
                {font_size_control}
                <div class="settings-group">
                    <div class="settings-label-row">
                        <label class="settings-label" for="pageWidthSlider" data-i18n="settings.pageWidth">Page width</label>
                        {page_width_value_control}
                    </div>
                    <div class="page-width-control"{page_width_control_attribute}>
                        <input type="range" id="pageWidthSlider" {page_width_slider_attributes} aria-label="Page width" data-i18n-aria-label="settings.pageWidth">
                        <div class="page-width-scale" aria-hidden="true">
                            {page_width_scale}
                        </div>
                    </div>
                </div>
                <div class="settings-group settings-group-custom-css">
                    <div class="settings-section-heading">
                        <span class="settings-section-title" data-i18n="settings.customStyles">Custom styles</span>
                        <span class="settings-section-optional" data-i18n="settings.optional">Optional</span>
                    </div>
                    <p class="settings-section-description" data-i18n="settings.customStylesDescription">Use CSS to fine-tune this book’s typography and layout.</p>
                    <div class="css-editor">
                        <textarea id="customCssInput" placeholder="Please input your CSS code... For example: #eb-content-container{{background: inherit; box-shadow:inherit;}} #eb-content{{margin: 50px; width: auto}} #eb-content p {{margin-bottom: 0.8rem; line-height: 1.7;}}" data-i18n-placeholder="settings.customCssPlaceholder"></textarea>
                        <div class="css-controls">
                            <button class="css-btn primary" id="saveCssBtn">
                                <i class="fas fa-save"></i> <span data-i18n="settings.save">Save</span>
                            </button>
                            <button class="css-btn primary" id="saveAsDefaultBtn">
                                <i class="fas fa-star"></i> <span data-i18n="settings.saveAsDefault">Save as default</span>
                            </button>
                            <button class="css-btn secondary" id="resetCssBtn">
                                <i class="fas fa-undo"></i> <span data-i18n="settings.reset">Reset</span>
                            </button>
                            <button class="css-btn secondary" id="loadDefaultBtn">
                                <i class="fas fa-download"></i> <span data-i18n="settings.loadDefault">Load default</span>
                            </button>
                            <button class="css-btn secondary" id="previewCssBtn">
                                <i class="fas fa-eye"></i> <span data-i18n="settings.preview">Preview</span>
                            </button>
                        </div>
                        <div class="css-info">
                            <p><i class="fas fa-info-circle"></i> <span data-i18n="settings.defaultStyleTip">Tip: The default style will be applied to all books unless a custom style is set for specific books.</span></p>
                        </div>
                    </div>
                </div>
            </div>
            <div class="settings-tab-panel" id="reading-tab">
                <div class="settings-group">
                    <label class="settings-label" data-i18n="settings.readingMode">Reading mode</label>
                    <label class="settings-switch">
                        <input type="checkbox" id="showReadingProgressBarToggle" checked>
                        <span class="switch-slider"></span>
                        <span class="switch-text" data-i18n="settings.showReadingProgressBar">Show reading progress bar</span>
                    </label>
                    <label class="settings-switch">
                        <input type="checkbox" id="paginationModeToggle">
                        <span class="switch-slider"></span>
                        <span class="switch-text" data-i18n="settings.paginationMode">Use page-turning mode</span>
                    </label>
                    <label class="settings-switch">
                        <input type="checkbox" id="continuousScrollToggle">
                        <span class="switch-slider"></span>
                        <span class="switch-text" data-i18n="settings.continuousScroll">Enable continuous scroll</span>
                        <span class="continuous-scroll-tip" id="continuousScrollTip" tabindex="0" data-settings-tip data-tip="Automatically loads the next chapter when scrolling past the end. Note: scroll progress save/restore is disabled. Tip: press Space for a similar seamless reading experience when this is off." data-i18n-data-tip="settings.continuousScrollTip" aria-label="Automatically loads the next chapter when scrolling past the end. Note: scroll progress save/restore is disabled. Tip: press Space for a similar seamless reading experience when this is off." data-i18n-aria-label="settings.continuousScrollTip">
                            <i class="fas fa-info-circle" aria-hidden="true"></i>
                        </span>
                    </label>
                </div>
                <fieldset class="settings-group desktop-layout-settings">
                    <legend class="settings-section-title" data-i18n="settings.desktopLayout">Desktop layout</legend>
                    <div class="desktop-layout-options">
                        <label class="settings-switch desktop-layout-option desktop-setting-only">
                            <input type="checkbox" id="desktopChapterSidebarToggle">
                            <span class="switch-slider"></span>
                            <span class="switch-text" data-i18n="settings.desktopChapterSidebar">Show chapter sidebar</span>
                        </label>
                        <div class="desktop-layout-option settings-option-with-tip desktop-setting-only">
                            <label class="settings-switch">
                                <input type="checkbox" id="autoHideDesktopChapterSidebarToggle" disabled aria-disabled="true">
                                <span class="switch-slider"></span>
                                <span class="switch-text" data-i18n="settings.autoHideDesktopChapterSidebar">Auto-hide chapter sidebar</span>
                            </label>
                            <button type="button" class="settings-info-tip" data-settings-tip data-tip="Move the pointer to the left edge, or use Tab, to show the chapter sidebar." data-i18n-data-tip="settings.autoHideDesktopChapterSidebarHelp" aria-label="Move the pointer to the left edge, or use Tab, to show the chapter sidebar." data-i18n-aria-label="settings.autoHideDesktopChapterSidebarHelp">
                                <i class="fas fa-info-circle" aria-hidden="true"></i>
                            </button>
                        </div>
                        <div class="desktop-layout-option settings-option-with-tip">
                            <label class="settings-switch">
                                <input type="checkbox" id="autoHideDesktopToolbarToggle">
                                <span class="switch-slider"></span>
                                <span class="switch-text" data-i18n="settings.autoHideDesktopToolbar">Auto-hide reading toolbar</span>
                            </label>
                            <button type="button" class="settings-info-tip" data-settings-tip data-tip="Move the pointer to the right edge, or use Tab, to show the toolbar." data-i18n-data-tip="settings.autoHideDesktopToolbarHelp" aria-label="Move the pointer to the right edge, or use Tab, to show the toolbar." data-i18n-aria-label="settings.autoHideDesktopToolbarHelp">
                                <i class="fas fa-info-circle" aria-hidden="true"></i>
                            </button>
                        </div>
                    </div>
                </fieldset>
                <fieldset class="settings-group keyboard-navigation-settings">
                    <legend class="settings-section-title" data-i18n="settings.keyboardNavigation">Keyboard navigation</legend>
                    <div class="keyboard-navigation-options">
                        <label class="settings-switch keyboard-navigation-option">
                            <input type="checkbox" id="arrowKeyNavigationToggle" checked>
                            <span class="switch-slider"></span>
                            <span class="switch-text" data-i18n="settings.arrowKeyNavigation">Use Left and Right Arrow keys to navigate</span>
                        </label>
                        <label class="settings-switch keyboard-navigation-option">
                            <input type="checkbox" id="spaceKeyNavigationToggle" checked>
                            <span class="switch-slider"></span>
                            <span class="switch-text" data-i18n="settings.spaceKeyNavigation">Use Space for the next page or chapter</span>
                        </label>
                    </div>
                </fieldset>
                <fieldset class="settings-group navigation-behavior-settings" aria-describedby="navigationBehaviorHelp">
                    <legend class="settings-section-title" data-i18n="settings.navigationBehavior">Navigation bar behavior</legend>
                    <p class="settings-section-description" id="navigationBehaviorHelp" data-i18n="settings.navigationBehaviorHelp">Choose when the top navigation stays visible while you read.</p>
                    <div class="navigation-behavior-options">
                        <label class="navigation-behavior-option"><input type="radio" name="navigationBehavior" value="normal" checked><span data-i18n="settings.navigationBehavior.normal">Normal scroll</span></label>
                        <label class="navigation-behavior-option"><input type="radio" name="navigationBehavior" value="sticky"><span data-i18n="settings.navigationBehavior.sticky">Always sticky</span></label>
                        <label class="navigation-behavior-option"><input type="radio" name="navigationBehavior" value="auto-hide"><span data-i18n="settings.navigationBehavior.autoHide">Hide down, show up</span></label>
                    </div>
                </fieldset>
            </div>
        </div>
    </div>

    <div class="reading-controls" data-id="reading-controls">
        <button class="control-btn" id="scrollToTopBtn" type="button" aria-label="Top" data-i18n-aria-label="reader.top">
            <i class="fas fa-arrow-up"></i>
            <span class="control-name" data-i18n="reader.top">Top</span>
        </button>
    </div>

    <!-- 移动端控件 -->
    <div class="mobile-controls" data-id="mobile-controls">
        <button class="control-btn" id="mobileTocBtn" type="button" aria-label="This chapter contents" title="This chapter contents" data-i18n-aria-label="reader.thisChapterContents" data-i18n-title="reader.thisChapterContents" aria-controls="tocFloating" aria-expanded="false">
            <i class="fas fa-list"></i>
            <span data-i18n="reader.thisChapterContents">This chapter</span>
        </button>
        {pdf_mobile_controls}
        {mobile_ai_reading_button}
        {mobile_ai_followup_button}
        {prev_link_mobile}
        <a href="/" aria-label="Home" title="Home" data-i18n-aria-label="reader.home" data-i18n-title="reader.home">
            <div class="control-btn" aria-label="Home" data-i18n-aria-label="reader.home">
                <i class="fas fa-home"></i>
                <span data-i18n="reader.home">Home</span>
            </div>
        </a>
        {next_link_mobile}
        <button class="control-btn" id="mobileBookHomeBtn" type="button" aria-label="Open book chapters" title="Open book chapters" data-i18n-aria-label="reader.openBookChapters" data-i18n-title="reader.openBookChapters">
            <i class="fas fa-book"></i>
            <span data-i18n="reader.bookChapters">Chapters</span>
        </button>
        <button class="control-btn" id="mobileSettingsBtn" type="button" aria-label="Settings" title="Settings" data-i18n-aria-label="reader.settings" data-i18n-title="reader.settings" aria-controls="settingsModal" aria-expanded="false">
            <i class="fas fa-cog"></i>
            <span data-i18n="reader.settings">Settings</span>
        </button>
        <button class="control-btn" id="mobileTopBtn" type="button" aria-label="Top" title="Top" data-i18n-aria-label="reader.top" data-i18n-title="reader.top">
            <i class="fas fa-arrow-up"></i>
            <span data-i18n="reader.top">Top</span>
        </button>
    </div>

    <!-- 书架弹窗 -->
    <div class="bookshelf-modal" id="bookshelfModal" role="dialog" aria-modal="true" aria-labelledby="bookshelfModalTitle">
        <div class="bookshelf-content" tabindex="-1">
            <div class="bookshelf-header">
                <div class="bookshelf-header-left">
                    <button class="bookshelf-action-btn" id="addShelfGroupBtn">
                        <i class="fas fa-folder-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addGroup">Add Group</span>
                    </button>
                    <button class="bookshelf-action-btn" id="addShelfBookBtn">
                        <i class="fas fa-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addBook">Add Book</span>
                    </button>
                    {bookshelf_data_actions}
                </div>
                <h2 class="bookshelf-title" id="bookshelfModalTitle"><i class="fas fa-home" aria-hidden="true"></i> <span data-i18n="bookshelf.title">Bookshelf</span></h2>
                <div class="bookshelf-header-right">
                    <button class="bookshelf-close-btn" id="bookshelfCloseBtn" aria-label="Close" data-i18n-aria-label="bookshelf.close">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="bookshelf-loading" id="bookshelfLoading" role="status" aria-label="Loading bookshelf" data-i18n-aria-label="bookshelf.loading">
                <div class="loading-spinner"></div>
            </div>
            <div class="bookshelf-body" id="bookshelfBody">
            </div>
            <div class="bookshelf-footer" id="bookshelfFooter">
                <span id="bookshelfStats"></span>
            </div>
        </div>
    </div>

    <!-- 分组弹窗 -->
    <div class="bookshelf-modal" id="groupModal" role="dialog" aria-modal="true" aria-labelledby="groupModalTitle">
        <div class="bookshelf-content" tabindex="-1">
            <div class="bookshelf-header">
                <div class="bookshelf-header-left">
                    <button class="bookshelf-action-btn" id="addGroupSubGroupBtn">
                        <i class="fas fa-folder-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addGroup">Add Group</span>
                    </button>
                    <button class="bookshelf-action-btn" id="addGroupBookBtn">
                        <i class="fas fa-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addBook">Add Book</span>
                    </button>
                    <button class="bookshelf-action-btn" id="renameGroupBtn">
                        <i class="fas fa-edit" aria-hidden="true"></i> <span data-i18n="bookshelf.rename">Rename</span>
                    </button>
                    <button class="bookshelf-action-btn bookshelf-delete-btn" id="deleteGroupBtn">
                        <i class="fas fa-trash" aria-hidden="true"></i> <span data-i18n="bookshelf.deleteGroup">Delete Group</span>
                    </button>
                </div>
                <h2 class="bookshelf-title" id="groupModalTitle" data-i18n="bookshelf.group">Group</h2>
                <div class="bookshelf-header-right">
                    <button class="bookshelf-close-btn" id="groupCloseBtn" aria-label="Back to bookshelf" data-i18n-aria-label="bookshelf.home">
                        <i class="fas fa-home"></i>
                    </button>
                    <button class="bookshelf-close-btn" id="groupCloseAllBtn" aria-label="Close" data-i18n-aria-label="bookshelf.close">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="bookshelf-loading" id="groupLoading" role="status" aria-label="Loading bookshelf" data-i18n-aria-label="bookshelf.loading">
                <div class="loading-spinner"></div>
            </div>
            <div class="bookshelf-body" id="groupBody">
            </div>
            <div class="bookshelf-footer" id="groupFooter">
                <span id="groupStats"></span>
            </div>
        </div>
    </div>
    {server_account_panel}
    {render_footer(datetime.now().year, release_api_url='/api/version' if self.deployment_mode == 'server' else '')}
"""
        cache_boundary_script = (
            '<script src="/assets/cache-boundary.js" defer></script>'
            if self.deployment_mode == "server"
            else ""
        )
        reading_insights_assets = (
            '<link rel="stylesheet" href="' + self.asset_manifest.url_for('reading-insights.css') + '">'
            '<script src="' + self.asset_manifest.url_for('reading-insights.js') + '" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        auth_script = (
            SERVER_AUTH_SCRIPT
            if self.deployment_mode == "server"
            else ""
        )
        startup = (
            """function startChapterClients() {
        if (!window.EpubBrowserAuth) return;
        window.EpubBrowserAuth.init().then(function(session) {
            if (!session) return;
            if (window.initScriptChapter) window.initScriptChapter();
            if (window.EpubReadingSessions) window.EpubReadingSessions.start();
        });
    }
    if (window.EpubBrowserCacheBoundary) {
        window.EpubBrowserCacheBoundary.start(startChapterClients);
    }"""
            if self.deployment_mode == "server"
            else "if (window.initScriptChapter) window.initScriptChapter();"
        )
        chapter_html += f"""
    {cache_boundary_script}
    <script src="/assets/notification.js" defer></script>
    {auth_script}
    {server_locale_script}
    <script src="/assets/theme.js" defer></script>
    <script src="/assets/dialog.js" defer></script>
    <script src="/assets/version-check.js" defer></script>
    <script src="/assets/vendor/glightbox/glightbox.min.js" defer></script>
    <script src="/assets/lightbox-adapter.js" defer></script>
    <script src="/assets/vendor/web-highlighter/web-highlighter.min.js" defer></script>
    <script src="/assets/chapter-window.js" defer></script>
    <script src="/assets/viewport-anchor.js" defer></script>
    <script src="/assets/continuous-buffer.js" defer></script>
    <script src="/assets/reading-progress.js" defer></script>
    <script src="/assets/reader-layout.js" defer></script>
    {pdf_chapter_script}
    <script src="/assets/chapter.js?v=17" defer></script>
    <script src="/assets/annotation-position.js" defer></script>
    <script src="/assets/annotation.js" defer></script>
    <script src="/assets/annotation-hub.js" defer></script>
    <script src="/assets/vendor/sortablejs/sortable.min.js" defer></script>
    {dictionary_assets}
    <script src="/assets/vendor/highlight/highlight.min.js" defer></script>
    <script src="/assets/bookshelf.js" defer></script>
    {reading_insights_assets}
    {reading_session_script}
    {ai_chapter_scripts}
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        {startup}
    }});
    </script>
</body>
</html>
"""
        chapter_html = rewrite_asset_urls(chapter_html, self.asset_manifest)
        chapter_html = self._inject_deployment_mode(chapter_html)
        chapter_html = rewrite_root_urls(chapter_html, self.urls)
        # kindle 支持，不能压缩 css 和 js
        # 部分 xhtml 书籍压缩之后会丢失标签，说明压缩算法可能存在问题
        # chapter_html = minify_html.minify(chapter_html, minify_css=False, minify_js=False)
        return chapter_html

    def _inject_deployment_mode(self, page_html):
        marker = '<script>window.EpubBrowserI18n.init();</script>'
        bootstrap = (
            '<script>window.EpubBrowserBasePath='
            + json.dumps(self.urls.base_path)
            + ';window.EpubBrowserMode='
            + json.dumps(self.deployment_mode)
            + '</script>'
            + marker
        )
        return page_html.replace(marker, bootstrap, 1)
    
    def copy_resources(self):
        """复制资源文件"""
        # 复制整个提取目录到web目录下的resources文件夹
        resources_dir = os.path.join(self.web_dir, self.resources_base)
        os.makedirs(resources_dir, exist_ok=True)
        
        # 复制整个提取目录
        for root, dirs, files in os.walk(self.extract_dir):
            for file in files:
                if self.deployment_mode == "server":
                    suffix = file.rsplit(".", 1)[-1].casefold()
                    if suffix not in SERVER_PASSIVE_RESOURCE_SUFFIXES:
                        continue
                else:
                    suffix = file.split(".")[-1]
                    if suffix in (
                        "html", "xhtml", "xml", "txt", "opf", "ncx", "mimetype"
                    ):
                        # SSG retains the historical resource-copy behavior.
                        continue

                src_path = os.path.join(root, file)
                # 计算相对于提取目录的相对路径
                rel_path = os.path.relpath(src_path, self.extract_dir)
                dst_path = os.path.join(resources_dir, rel_path)
                
                # 确保目标目录存在
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                if self.deployment_mode == "server" and suffix == "svg":
                    source = Path(src_path).read_text(encoding="utf-8")
                    Path(dst_path).write_text(
                        sanitize_svg_content(source),
                        encoding="utf-8",
                    )
                elif self.deployment_mode == "server" and suffix == "css":
                    source = Path(src_path).read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                    Path(dst_path).write_text(
                        sanitize_css_text(source),
                        encoding="utf-8",
                    )
                else:
                    shutil.copy2(src_path, dst_path)
        
        # 删除原来的 extracted，以后都不用了
        if os.path.exists(self.extract_dir):
            try:
                shutil.rmtree(self.extract_dir)
            except Exception:
                pass

        # print(f"Resource files copied to: {resources_dir}")
    
    def get_book_info(self):
        """获取书籍信息"""
        cover_path = ""
        if self.cover_info and self.cover_info.get('web_path'):
            cover_path = self.cover_info['web_path']
        elif self.cover_info and self.cover_info['full_path']:
            cover_path = os.path.normpath(os.path.join(self.resources_base, self.cover_info["full_path"]))
        return {
            'title': self.book_title,
            'temp_dir': self.temp_dir,
            'path': self.web_dir,
            'hash': self.book_hash,
            'cover': cover_path,
            'authors': self.authors,
            'tags': self.tags,
            'origin_file_path': self.epub_path,
        }

    def get_metadata(self):
        """Return immutable metadata shared by SSG and Server publishers."""
        cover_path = None
        if self.cover_info and self.cover_info.get('web_path'):
            cover_path = self.cover_info['web_path']
        elif self.cover_info and self.cover_info.get('full_path'):
            cover_path = os.path.normpath(
                os.path.join(self.resources_base, self.cover_info['full_path'])
            )
        return BookMetadata(
            title=self.book_title,
            authors=tuple(self.authors or ()),
            tags=tuple(self.tags or ()),
            cover=cover_path,
            language=self.lang or 'en',
            epub_identifier=self.epub_identifier,
            source_format=self.source_format,
        )
    
    def cleanup(self):
        """清理临时文件"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            # print(f"Temporary files cleaned up for: {self.book_title}")
