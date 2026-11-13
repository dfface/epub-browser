import os
import ntpath
import posixpath
import zipfile
import tempfile
import shutil
import re
import hashlib
import base64
import html
import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

from .asset_publisher import (
    AssetPublisher,
    SERVER_ONLY_ASSET_PATHS,
    SERVER_ONLY_ASSET_PREFIXES,
)
from .epub_parsing import (
    EPUBParseError,
    decode_html_bytes,
    find_descendant_local,
    find_local,
    findall_local,
    iter_local,
    local_name,
    parse_xhtml_document,
    parse_xml_document,
    require_single_rootfile,
    validate_manifest_ids,
    validate_spine_references,
)
from .epub_sanitization import (
    SERVER_PASSIVE_RESOURCE_SUFFIXES,
    _convert_inline_styles,
    _normalize_font_unit_to_em,
    _safe_html_url,
    metadata_text,
    normalize_css_text,
    sanitize_css_declarations,
    sanitize_css_text,
    sanitize_html_fragment,
    sanitize_svg_content,
    server_book_public_path_allowed,
)
from .models import ConvertedBook
from .reader_pages import ReaderPageRenderer
from .reporting import Reporter
from .source_format import EPUB_FORMAT, PDF_FORMAT
from .urls import SiteURLs


# Server mode stores only EPUB-derived content. Reader HTML is rendered from
# that cache for each request, so changes to UI, i18n, permissions, or hashed
# assets never require reconverting unchanged EPUB files.
SERVER_OUTPUT_REVISION_FILE = ".server-content-revision"
# Bump whenever the EPUB-derived server cache schema or chapter semantics change.
# Server reader chrome and assets are deliberately outside this revision.
# v10: chapters are parsed and sanitized through the unified lxml pipeline, so
# stored chapter HTML differs from earlier revisions and must be regenerated.
# v11: book CSS font/length fixed units (px/pt) in font-size-relevant
# properties are converted to `em` so the reader font-size control affects every
# EPUB; stored chapter CSS therefore differs and must be regenerated.
SERVER_OUTPUT_REVISION = "server-content-v11"


class EPUBProcessor(ReaderPageRenderer):
    """Convert EPUB sources and write the requested deployment artifacts."""

    def __init__(
        self,
        epub_path,
        output_dir=None,
        asset_manifest=None,
        book_id=None,
        urls=None,
        reporter=None,
        deployment_mode="ssg",
        kindle_support=False,
    ):
        self.epub_path = os.fspath(epub_path)
        self.output_dir = output_dir
        self.urls = urls or SiteURLs()
        self.reporter = reporter or Reporter(False)
        if deployment_mode not in {"ssg", "server"}:
            raise ValueError(f"Unsupported deployment mode: {deployment_mode}")
        self.deployment_mode = deployment_mode
        self.kindle_support = bool(kindle_support)
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
        self._prepared_opf_path = None
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
        self.ai_reading_enabled = self.deployment_mode != "ssg"

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

    def prepare(self):
        """解压并解析一次，供元数据读取和后续转换共用。"""
        if self._prepared_opf_path is not None:
            return self._prepared_opf_path
        if not self.extract_epub():
            raise ValueError(f"Unable to extract EPUB file: {self.epub_path}")
        opf_path = self.parse_container()
        if not opf_path:
            raise ValueError(f"Unable to parse EPUB container file: {self.epub_path}")
        if not self.parse_opf(opf_path):
            raise ValueError(f"Unable to parse EPUB package file: {self.epub_path}")
        self._prepared_opf_path = opf_path
        return opf_path

    def bind_book_id(self, book_id):
        """在生成页面前绑定 Server 已解析的稳定书籍 ID。"""
        if self._server_chapter_payloads:
            raise RuntimeError("Cannot change the book ID after chapter conversion")
        self.book_hash = book_id
        self._caller_supplied_book_id = True

    def convert(self):
        """Convert one EPUB into its caller-owned staging directory."""
        self.prepare()
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
            root = parse_xml_document(container_path)
        except ValueError:
            raise
        except EPUBParseError as error:
            self.reporter.detail(f"Failed to parse container.xml: {error}")
            return None

        try:
            full_path = require_single_rootfile(root)
        except EPUBParseError as error:
            self.reporter.detail(f"Failed to parse container.xml: {error}")
            return None
        # ``_resolve_internal_path`` raises on an escaping reference, which is
        # the structural "safe path" check for the package document.
        return self._resolve_internal_path(full_path)

    def find_cover_info(self, opf_tree):
        """
        在 OPF 文件中查找封面信息
        """
        # 方法1: 查找 meta 标签中声明的封面
        cover_id = None
        metadata = find_descendant_local(opf_tree, 'metadata')
        if metadata is not None:
            for meta in findall_local(metadata, 'meta'):
                if meta.get('name') in ['cover', 'cover-image']:
                    cover_id = meta.get('content')
                    break

        # 方法2: 查找 manifest 中的封面项
        manifest = find_descendant_local(opf_tree, 'manifest')
        manifest_items = (
            findall_local(manifest, 'item') if manifest is not None else []
        )

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

    def find_ncx_file(self, opf_root, opf_path, manifest):
        """查找NCX文件路径"""
        opf_dir = posixpath.dirname(opf_path)

        # 首先查找OPF中明确指定的toc。  The already-parsed package document is
        # reused instead of re-reading and re-parsing the OPF.
        spine = find_descendant_local(opf_root, 'spine')
        if spine is not None:
            toc_id = spine.get('toc')
            if toc_id and toc_id in manifest:
                ncx_path = manifest[toc_id]['full_path']
                if ncx_path and self._internal_file(ncx_path).is_file():
                    return ncx_path

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
            root = parse_xhtml_document(nav_full_path)
            epub_type = '{http://www.idpf.org/2007/ops}type'

            toc_nav = next(
                (
                    element for element in root.iter()
                    if local_name(element.tag) == 'nav'
                    and 'toc' in element.get(epub_type, element.get('type', '')).split()
                ),
                None,
            )
            if toc_nav is None:
                return []

            def direct_child(element, name):
                return find_local(element, name)

            def item_label(item):
                for child in item:
                    if local_name(child.tag) in {'a', 'span'}:
                        label = ' '.join(''.join(child.itertext()).split())
                        if label:
                            return html.unescape(label), child
                label = ' '.join((item.text or '').split())
                return html.unescape(label), None

            toc = []
            nav_dir = posixpath.dirname(nav_path)

            def process_list(list_element, level=0):
                for item in list_element:
                    if local_name(item.tag) != 'li':
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
            root = parse_xml_document(ncx_full_path)

            # 解析目录
            nav_map = find_descendant_local(root, 'navMap')
            if nav_map is None:
                return []

            toc = []

            ncx_dir = posixpath.dirname(ncx_path)

            def navpoint_target(navpoint):
                """Return a navPoint's *own* NCX target, if it has one.

                A navPoint is allowed to be a structural grouping node.  Do
                not use a descendant ``content`` element here: doing so makes
                a group look like a chapter and consumes a public chapter
                index that belongs to the OPF spine.
                """
                content = find_local(navpoint, 'content')
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
                child_navpoints = findall_local(navpoint, 'navPoint')
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
                nav_label_element = find_local(navpoint, 'navLabel')
                nav_label = (
                    find_local(nav_label_element, 'text')
                    if nav_label_element is not None else None
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
            top_navpoints = findall_local(nav_map, 'navPoint')
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
            root = parse_xml_document(opf_full_path)

            # 获取书名
            title_elem = find_descendant_local(root, 'title')
            if title_elem is not None and title_elem.text:
                self.book_title = title_elem.text

            identifier_elem = find_descendant_local(root, 'identifier')
            if identifier_elem is not None and identifier_elem.text:
                self.epub_identifier = identifier_elem.text.strip() or None

            # 获取作者名
            authors = list(iter_local(root, 'creator'))
            self.authors = [author.text for author in authors] if authors else None

            # 获取标签
            tags = list(iter_local(root, 'subject'))
            self.tags = [tag.text for tag in tags] if tags else None

            # 获取描述
            description = find_descendant_local(root, 'description')
            self.description = description.text if description is not None and description.text else None

            # 获取语言
            lang = find_descendant_local(root, 'language')
            self.lang = lang.text.strip() if lang is not None and lang.text and lang.text.strip() else 'en'

            # 获取manifest（所有资源）
            manifest = {}
            opf_dir = posixpath.dirname(opf_path)
            # 获取封面
            cover_info = self.find_cover_info(root)
            if cover_info:
                href = cover_info["href"]
                cover_info["full_path"] = (
                    self._resolve_internal_path(href, opf_dir) if href else None
                )
            self.cover_info = cover_info
            # Structural validation: manifest items without an id are skipped
            # (nothing can address them), duplicate ids keep their first
            # occurrence (the repeated declaration usually points at the same
            # href), so every manifest entry is uniquely addressable.
            manifest_element = find_descendant_local(root, 'manifest')
            manifest_items = (
                findall_local(manifest_element, 'item')
                if manifest_element is not None
                else list(iter_local(root, 'item'))
            )
            valid_manifest_ids = validate_manifest_ids(manifest_items)
            # 获取其他资源 xhtml、font、css 等
            for item in manifest_items:
                item_id = item.get('id')
                if (
                    item_id not in valid_manifest_ids
                    or item_id in manifest
                ):
                    # Id-less or duplicate declaration: keep the first
                    # occurrence so a spine idref binds deterministically.
                    continue
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
                ncx_path = self.find_ncx_file(root, opf_path, manifest)
                if ncx_path:
                    self.toc = self.parse_ncx(ncx_path)

            # 获取spine（阅读顺序）
            spine = find_descendant_local(root, 'spine')
            if spine is not None:
                itemrefs = findall_local(spine, 'itemref')
                # A spine itemref for an id the manifest never declared cannot
                # bind to any resource.  Real-world EPUBs ship such dangling
                # references (often a leftover "toc" entry); the remaining,
                # resolvable idrefs still form a consistent reading sequence,
                # so they are kept and the dangling ones dropped.
                declared_idrefs = validate_spine_references(
                    [itemref.get('idref') for itemref in itemrefs],
                    set(manifest),
                )
                for itemref in itemrefs:
                    idref = itemref.get('idref')
                    if idref in declared_idrefs:
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
            root = parse_xhtml_document(self._internal_file(chapter_path))
        except (OSError, EPUBParseError):
            return None
        except ValueError:
            raise

        for element in root.iter():
            if local_name(element.tag) not in {"h1", "h2", "h3", "h4", "h5", "h6", "div", "p"}:
                continue
            classes = str(element.get("class") or "").split()
            if "section_index_title" not in classes:
                continue
            title = " ".join(
                metadata_text("".join(element.itertext())).split()
            )
            return title or None
        return None

    def create_web_interface(self):
        """创建网页界面"""
        os.makedirs(self.web_dir, exist_ok=True)

        # Server mode deliberately keeps page chrome out of the conversion
        # cache. The current application code renders it at request time.
        self.create_index_page(write=self.deployment_mode != "server")

        # 创建章节页面
        self.create_chapter_pages(write=self.deployment_mode != "server")

        # SSG 在开启 --kindle 时额外写出独立的 Kindle 极简阅读页面；
        # Server 模式在请求时由 server_pages 用同一模板动态渲染，不写入转换产物。
        if self.deployment_mode != "server" and self.kindle_support:
            self.create_kindle_pages()

        # 复制资源文件（CSS、图片、字体等）并删除 extracted 文件夹
        self.copy_resources()

        if self.deployment_mode == "server":
            self._write_server_content_cache()

        # print(f"Web interface created at: {self.web_dir}")
        return self.web_dir

    def create_index_page(self, write=True, initial_book_review=None):
        index_html = self.render_index(initial_book_review=initial_book_review)
        if write:
            with open(os.path.join(self.web_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(index_html)
            self.create_toc_json()
        return index_html




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
            body_content = ""
            style_links = []
            try:
                # 读取章节内容。  EPUB mandates UTF-8, but sloppy real-world
                # chapters are often GB18030/GBK; decode_html_bytes never fails
                # and keeps the content readable instead of blanking the page.
                with open(chapter_path, 'rb') as f:
                    content = decode_html_bytes(f.read())

                # 处理HTML内容，修复资源链接并提取样式
                body_content, style_links = self.process_html_content(content, chapter['path'])
            except ValueError:
                # A path escaping the archive is a security boundary, not a
                # tolerance question: never silently degrade it.
                raise
            except Exception as e:
                # One broken chapter must not sink the whole book: keep its
                # index (chapters and TOC stay aligned) and render a blank
                # placeholder so the reader still sees a complete sequence.
                self.reporter.detail(
                    f"Failed to process chapter {chapter['path']}; "
                    f"rendering an empty placeholder: {e}"
                )
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


    def create_kindle_pages(self):
        """生成 Kindle 极简阅读页面（SSG 输出）。

        仅针对 EPUB：PDF 阅读页依赖 PDF.js，旧 Kindle 浏览器无法运行，
        因此 PDF 书籍不生成 Kindle 页面。页面刻意自包含：内联 CSS/JS、
        Cookie 存储、ES5 语法，不依赖 /assets/ 下的任何资源。
        Server 模式在请求时用同一组模板动态渲染，不写入这里。
        """
        if getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT:
            return
        toc_data = self._build_toc_data()
        with open(os.path.join(self.web_dir, 'kindle.html'), 'w', encoding='utf-8') as f:
            f.write(self.create_kindle_index_page(toc_data))
        for i, chapter in enumerate(self.chapters):
            chapter_path = self._internal_file(chapter['path'])
            body_content = ""
            style_links = ""
            try:
                with open(chapter_path, 'rb') as f:
                    content = decode_html_bytes(f.read())
                body_content, style_links = self.process_html_content(
                    content, chapter['path']
                )
            except ValueError:
                raise
            except Exception as e:
                # One broken chapter must not sink the whole book: render an
                # empty placeholder so the Kindle sequence stays complete.
                self.reporter.detail(
                    f"Failed to process chapter {chapter['path']} for the "
                    f"Kindle page; rendering an empty placeholder: {e}"
                )
            chapter_html = self.create_kindle_chapter_page(
                body_content, style_links, i, chapter['title']
            )
            with open(
                os.path.join(self.web_dir, f'kindle_chapter_{i}.html'),
                'w',
                encoding='utf-8',
            ) as f:
                f.write(chapter_html)



    def _write_server_book_metadata(self):
        """写入完整缓存与冷缓存共用的书籍元数据和目录。"""
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

    def _copy_shelf_cover(self):
        if not self.cover_info or not self.cover_info.get("full_path"):
            return
        cover = self.get_metadata().cover
        source = self._internal_file(self.cover_info["full_path"])
        if not cover or not source.is_file():
            return
        web_root = Path(self.web_dir).resolve()
        target = web_root.joinpath(*Path(cover).parts).resolve()
        try:
            target.relative_to(web_root)
        except ValueError as error:
            raise ValueError("Unsafe EPUB cover path") from error
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.casefold() == ".svg":
            target.write_text(
                sanitize_svg_content(source.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
        else:
            shutil.copy2(source, target)

    def create_shelf_cache(self):
        """只生成书库元数据、目录与封面，不转换章节正文。"""
        if self.deployment_mode != "server":
            raise ValueError("Shelf-only caches are only available in Server mode")
        self.prepare()
        self.generate_hash()
        Path(self.web_dir).mkdir(parents=True, exist_ok=True)
        self._write_server_book_metadata()
        self._copy_shelf_cover()
        return ConvertedBook(
            book_id=self.book_hash,
            source_path=Path(self.epub_path),
            output_dir=Path(self.web_dir),
            metadata=self.get_metadata(),
            chapter_count=len(self.chapters),
        )

    def _write_server_content_cache(self):
        """Persist only immutable EPUB-derived data for Server mode.

        HTML shells, application navigation, i18n attributes, and app assets
        intentionally stay out of this cache. They are rendered from current
        code for every authenticated reader-page request.
        """
        self._write_server_book_metadata()
        if len(self._server_chapter_payloads) != len(self.chapters):
            raise ValueError("Server content cache is missing one or more chapters")
        content_dir = Path(self.web_dir, "content")
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
        else:
            # The SSG build does not run the full HTML sanitizer; convert fixed
            # font/length units inside inline `style` attributes so the reader
            # font-size control still affects inline-styled text (issue #35).
            body_content = _convert_inline_styles(body_content)

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
                    r'<style[^>]*>(.*?)</style>',
                    head_content,
                    re.DOTALL | re.IGNORECASE,
                )
                for style in styles:
                    safe_style = sanitize_css_text(style)
                    if safe_style:
                        style_links.append(
                            '<style class="eb">{}</style>'.format(safe_style)
                        )
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
                elif suffix.casefold() == "css":
                    normalize_only = self.deployment_mode == "ssg"
                    errors = "surrogateescape" if normalize_only else "replace"
                    source = Path(src_path).read_text(
                        encoding="utf-8",
                        errors=errors,
                    )
                    # SSG keeps publisher stylesheet features such as @import
                    # while sharing the font unit conversion used by Server.
                    css = (
                        normalize_css_text(source)
                        if normalize_only else sanitize_css_text(source)
                    )
                    Path(dst_path).write_text(
                        css,
                        encoding="utf-8",
                        errors=errors,
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


    def cleanup(self):
        """清理临时文件"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            # print(f"Temporary files cleaned up for: {self.book_title}")
