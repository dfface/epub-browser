"""EPUB markup and resource validation shared by conversion and rendering."""

import html
import re
import urllib.parse
from html.parser import HTMLParser
from pathlib import PurePosixPath

from lxml import etree

from .epub_parsing import (
    EPUBParseError, allowed_entity_name, entity_reference_name, find_local, local_name,
    parse_xhtml_fragment, parse_xml_bytes,
)


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


# An ``html`` or ``body`` root is a wrapper, never chapter content: the HTML
# parser adds one when a fragment has several siblings, and a real XHTML
# chapter carries its own.  Only the wrapper's contents are rendered.
_HTML_WRAPPER_TAGS = frozenset({"html", "body"})


def _append_sanitized_text(output, value):
    if not value:
        return
    output.append(html.escape(value, quote=False))


def _sanitized_attributes(element, name):
    """Serialize the attributes one element is allowed to keep."""
    allowed = _TAG_HTML_ATTRIBUTES.get(name, frozenset())
    serialized = []
    for raw_name, raw_value in element.attrib.items():
        attribute = local_name(raw_name).casefold()
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
        value = str(raw_value)
        if attribute in _URL_HTML_ATTRIBUTES:
            value = _safe_html_url(name, attribute, value)
            if value is None:
                continue
        serialized.append(
            " {}=\"{}\"".format(attribute, html.escape(value, quote=True))
        )
    return "".join(serialized)


def _render_sanitized(node, output):
    """Serialize one parsed node with the shared EPUB allowlist.

    Unknown elements keep their children but lose their own tags, so a
    publisher's wrapper element never hides a paragraph from the reader.
    """
    entity_name = entity_reference_name(node)
    if entity_name is not None:
        # A locally declared entity (an XXE carrier) is dropped outright;
        # only entities the HTML vocabulary already defines survive.
        if allowed_entity_name(entity_name):
            output.append("&{};".format(entity_name))
        _append_sanitized_text(output, node.tail)
        return
    if not isinstance(node.tag, str):
        # Comments and processing instructions carry no reader content.
        _append_sanitized_text(output, node.tail)
        return
    name = local_name(node.tag).casefold()
    dropped = name in _DROP_HTML_CONTENT_TAGS
    kept = name in _SAFE_HTML_TAGS
    if kept and not dropped:
        output.append("<{}{}>".format(name, _sanitized_attributes(node, name)))
    if not dropped:
        _append_sanitized_text(output, node.text)
        for child in node:
            _render_sanitized(child, output)
    if kept and not dropped and name not in _VOID_HTML_TAGS:
        output.append("</{}>".format(name))
    _append_sanitized_text(output, node.tail)


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
    """Serialize a conservative, inert fragment from untrusted EPUB markup.

    The fragment is parsed once, through the shared lxml pipeline, so malformed
    EPUB 2 markup, XHTML and legacy HTML all reach the same allowlist.
    """
    markup = str(content or "")
    if not markup.strip():
        return ""
    try:
        nodes = parse_xhtml_fragment(markup)
    except EPUBParseError:
        # Nothing could be trusted as structure; emit the text inertly.
        return html.escape(markup, quote=False)
    output = []
    for node in nodes:
        if isinstance(node, str):
            _append_sanitized_text(output, node)
            continue
        if local_name(node.tag).casefold() == "html":
            # Descend to ``body`` first so a chapter's ``head`` never leaks
            # its title or metadata into the rendered text.
            body = find_local(node, "body")
            if body is not None:
                node = body
        if local_name(node.tag).casefold() in _HTML_WRAPPER_TAGS:
            _append_sanitized_text(output, node.text)
            for child in node:
                _render_sanitized(child, output)
            continue
        _render_sanitized(node, output)
    return "".join(output)


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


# Font/sizing properties written with fixed (px, pt) or root/percentage
# relative (rem, %) units ignore or only partially honor the reader's font-size
# control: `px`/`pt` are absolute, `rem` is relative to the document root which
# the reader never changes (so it behaves like a fixed size), and `%` is
# normalized for consistency. We convert all of them to `em` (relative to the
# parent / content container) so they scale with that control. Only
# text-sizing/spacing properties are touched; layout-critical properties
# (borders, margins, widths, images, ...) are left alone. `em` is kept as-is;
# `calc()`/`var()`/`clamp()` values and exotic units (ex, ch, vw, ...) are
# preserved.
_FIXED_UNIT_EM_PROPERTIES = frozenset({
    "font-size",
    "letter-spacing",
    "word-spacing",
    "line-height",
})

# The reader applies its font-size control as `font-size: <n>rem` on the content
# container. `em` is relative to that container, so converted values scale with
# the control; `rem` is relative to the document root (which the reader never
# changes) so it would NOT scale -- that is exactly why `rem` is rewritten to
# `em` here. This also avoids double scaling because the reader never changes the
# root font-size.
_ROOT_FONT_SIZE_PX = 16.0
_PT_PER_PX = 4.0 / 3.0  # 1pt = 1/72in, 1px = 1/96in -> 1pt = 4/3 px

# Matches fixed (px, pt) and root/percentage relative (rem, %) lengths. These are
# all normalized to `em` for font/sizing properties; `em` itself and other values
# are left to the broader passthrough below.
_FONT_TO_EM_RE = re.compile(
    r"^\s*(-?\d*\.?\d+)(px|pt|rem|%)\s*(!\s*important)?\s*$",
    re.IGNORECASE,
)
_CSS_DECL_NAME_RE = re.compile(r"^\s*([\w-]+)\s*:")


def _length_to_px(value):
    # Absolute length in px, used to resolve a block's own font-size so a px/pt
    # line-height can be converted relative to it. Percentages are relative and
    # cannot be expressed as an absolute px without parent context, so they are
    # skipped (they are still normalized to `em` by the converter below). `rem`
    # maps cleanly to px (1rem == 16px) and is kept.
    match = _FONT_TO_EM_RE.match(value)
    if not match:
        return None
    unit = match.group(2).lower()
    if unit == "%":
        return None
    number = float(match.group(1))
    if unit == "pt":
        number *= _PT_PER_PX
    elif unit == "rem":
        number *= _ROOT_FONT_SIZE_PX
    return number


def _format_em(value_px, reference_px):
    em = value_px / reference_px
    if em == 0:
        return "0"
    return format(em, ".4f").rstrip("0").rstrip(".") + "em"


def _normalize_font_unit_to_em(name, value, font_size_px_ref):
    """Normalize a font/sizing length to `em`.

    `px`/`pt` are absolute, `rem` is root-relative, and `%` is relative to the
    parent; all three are rewritten to `em` (relative to the content container)
    so they honor the reader font-size control instead of staying pinned. `em`
    and any value not matched here (calc/var/ex/ch/vw/...) pass through.
    """
    if name not in _FIXED_UNIT_EM_PROPERTIES:
        return None
    match = _FONT_TO_EM_RE.match(value)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    important = match.group(3)
    if unit == "%":
        em_value = _format_em(number / 100.0, 1.0)
    elif unit == "rem":
        # 1rem == 16px; divide by the same 16 so 1rem -> 1em. `em` then scales
        # with the reader control while `rem` (root-relative) would not.
        em_value = _format_em(number * _ROOT_FONT_SIZE_PX, _ROOT_FONT_SIZE_PX)
    else:  # px / pt
        px = number * (_PT_PER_PX if unit == "pt" else 1.0)
        reference = font_size_px_ref if (
            name == "line-height" and font_size_px_ref
        ) else _ROOT_FONT_SIZE_PX
        em_value = _format_em(px, reference)
    if important:
        em_value = em_value + " " + important.strip()
    return "{}: {}".format(name, em_value)


def _declaration_name_value(declaration):
    name_match = _CSS_DECL_NAME_RE.match(declaration)
    if not name_match:
        return "", ""
    name = name_match.group(1).casefold()
    value = declaration.split(":", 1)[1].strip()
    return name, value


def sanitize_css_declarations(content, *, normalize_only=False):
    parsed = []
    for raw_declaration in _split_css_declarations(str(content or "")):
        declaration = raw_declaration.strip()
        if not declaration or ":" not in declaration:
            continue
        decoded = _decode_css_escapes(declaration)
        if not normalize_only and (
            _RISKY_CSS.search(decoded) or not _css_urls_are_safe(declaration)
        ):
            continue
        parsed.append(declaration)
    # Resolve the block's own font-size (px) so a px/pt line-height can be
    # converted relative to it; otherwise line-height falls back to the root.
    font_size_px_ref = None
    for declaration in parsed:
        name, value = _declaration_name_value(declaration)
        if name == "font-size":
            font_size_px_ref = _length_to_px(value)
            if font_size_px_ref is not None:
                break
    converted = []
    for declaration in parsed:
        name, value = _declaration_name_value(declaration)
        replacement = _normalize_font_unit_to_em(name, value, font_size_px_ref)
        converted.append(replacement if replacement else declaration)
    return "; ".join(converted)


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


def _sanitize_css_stylesheet(content, *, normalize_only=False):
    output = []
    position = 0
    while position < len(content):
        while position < len(content) and content[position].isspace():
            position += 1
        boundary, kind = _find_css_boundary(content, position)
        prelude = content[position:boundary].strip()
        if not kind:
            if normalize_only and prelude:
                output.append(prelude)
            break
        if kind == ";":
            rule_name = _css_at_rule_name(prelude)
            if prelude and (normalize_only or (
                rule_name not in {"import", "namespace", "charset"}
                and not _RISKY_CSS.search(_decode_css_escapes(prelude))
            )):
                output.append(prelude + ";")
            position = boundary + 1
            continue

        closing = _find_matching_css_brace(content, boundary)
        if closing is None:
            if normalize_only:
                output.append(content[position:])
            break
        body = content[boundary + 1:closing]
        rule_name = _css_at_rule_name(prelude)
        if rule_name:
            if rule_name in _CSS_DECLARATION_AT_RULES:
                safe_body = sanitize_css_declarations(body, normalize_only=normalize_only)
            elif rule_name in _CSS_GROUP_AT_RULES:
                safe_body = _sanitize_css_stylesheet(body, normalize_only=normalize_only)
            else:
                safe_body = body if normalize_only else ""
        elif not normalize_only and _RISKY_CSS.search(_decode_css_escapes(prelude)):
            safe_body = ""
        elif normalize_only and ("{" in body or "}" in body):
            # Leave nested rules intact. The declaration parser reads flat blocks.
            safe_body = body
        else:
            safe_body = sanitize_css_declarations(body, normalize_only=normalize_only)
        if prelude and safe_body:
            output.append("{} {{ {} }}".format(prelude, safe_body))
        position = closing + 1
    return "\n".join(output)


_INLINE_STYLE_ATTR_RE = re.compile(r'style="([^"]*)"', re.IGNORECASE)


def _convert_inline_styles(html):
    """Convert fixed font/length units inside inline `style` attributes.

    The SSG build does not run the full HTML sanitizer, so inline-styled text
    would otherwise ignore the reader font-size control. We only rewrite the
    font/length declarations (via sanitize_css_declarations); everything else is
    passed through untouched.
    """
    def _replace(match):
        converted = sanitize_css_declarations(match.group(1))
        return 'style="{}"'.format(converted) if converted else match.group(0)
    return _INLINE_STYLE_ATTR_RE.sub(_replace, html)


def normalize_css_text(content):
    return _sanitize_css_stylesheet(_CSS_COMMENT.sub("", content), normalize_only=True)


def sanitize_css_text(content):
    # Always run the full sanitizer so fixed font/length units (px/pt) in
    # stylesheet CSS are converted to `em` (see sanitize_css_declarations),
    # not just inline styles. Comments are stripped first; the sanitizer drops
    # risky declarations and re-emits the rest, which is the intended cleaning.
    candidate = _CSS_COMMENT.sub("", str(content or ""))
    return _sanitize_css_stylesheet(candidate)


def sanitize_svg_content(content):
    try:
        source_root = parse_xml_bytes(content)
    except EPUBParseError as error:
        raise ValueError("Unsafe or malformed SVG resource") from error
    if local_name(source_root.tag) != "svg":
        raise ValueError("Unsafe SVG resource root")

    def clean(source):
        name = local_name(source.tag)
        if name not in _SAFE_SVG_TAGS:
            return None
        target = etree.Element("{{{}}}{}".format(_SVG_NAMESPACE, name))
        for raw_name, raw_value in source.attrib.items():
            attribute = local_name(raw_name)
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

    cleaned_root = clean(source_root)
    if cleaned_root is None:
        raise ValueError("Unsafe SVG resource root")
    etree.cleanup_namespaces(cleaned_root, top_nsmap={None: _SVG_NAMESPACE})
    return etree.tostring(cleaned_root, encoding="unicode")
