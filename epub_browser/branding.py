"""Deployment identity and normalization for operator-supplied images."""

from dataclasses import dataclass
from html import escape
from io import BytesIO
import unicodedata

from PIL import Image


DEFAULT_SITE_NAME = 'EPUB Browser'
DEFAULT_LOGO = '/assets/logo-mark-color.png'
DEFAULT_FAVICON = '/assets/favicon.png'
MAX_BRAND_IMAGE_BYTES = 1024 * 1024


def validate_site_name(value):
    if not isinstance(value, str):
        raise ValueError('Invalid site name')
    value = value.strip()
    if len(value) > 80 or any(unicodedata.category(char) in {'Cc', 'Cs'} for char in value):
        raise ValueError('Site name must contain up to 80 printable characters')
    return value


def normalize_brand_image(contents, kind):
    """Decode and re-encode a bounded raster, discarding metadata and animation."""
    if not contents or len(contents) > MAX_BRAND_IMAGE_BYTES:
        raise ValueError('Brand image must be at most 1 MiB')
    try:
        with Image.open(BytesIO(contents), formats=['PNG', 'JPEG', 'WEBP']) as source:
            if max(source.size) > 2048 or getattr(source, 'is_animated', False):
                raise ValueError('Use a still image up to 2048 pixels per side')
            image = source.convert('RGBA')
            image.thumbnail((512, 512) if kind == 'logo' else (192, 192))
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError('Use a valid PNG, JPEG or WebP image') from error


@dataclass(frozen=True)
class Branding:
    name: str = ''
    logo: str = ''
    favicon: str = ''
    hide_version_info: bool = False

    @property
    def name_text(self):
        return escape(self.name or DEFAULT_SITE_NAME, quote=True).replace("/", "&#47;").replace("{", "&#123;")

    @property
    def brand_text(self):
        attribute = '' if self.name else ' data-i18n="common.brand"'
        return f'<span{attribute}>{self.name_text}</span>'

    def mark(self, css_class):
        return (f'<img class="{css_class}" src="{escape(self.logo or DEFAULT_LOGO)}" '
                'width="32" height="32" alt="" aria-hidden="true">')

    def nav(self):
        i18n = '' if self.name else ' data-i18n-aria-label="common.brand"'
        return (f'<a class="app-nav-brand" href="/" aria-label="{self.name_text}"{i18n}>'
                f'{self.mark("app-nav-brand-mark")}{self.brand_text}</a>')

    def title(self, page_text, i18n_key=''):
        suffix = f' · {self.name_text}' if self.name else ''
        attributes = f' data-i18n="{i18n_key}"' if i18n_key else ''
        if i18n_key and suffix:
            attributes += f' data-i18n-title-suffix="{suffix}"'
        return f'<title{attributes}>{page_text}{suffix}</title>'

    def icon(self, *, optional=False):
        if optional and not self.favicon:
            return ''
        return f'<link rel="icon" type="image/png" href="{escape(self.favicon or DEFAULT_FAVICON)}">'

    @property
    def touch_icon(self):
        return escape(self.favicon or '/assets/icon-192.png')
