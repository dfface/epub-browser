# Third-party browser assets

The browser assets below are generated from the exact immutable npm tarballs
recorded in `third_party/assets.lock.json`. Their complete upstream license
files are installed beside the runtime files under
`epub_browser/assets/vendor/` by `tools/sync_vendor_assets.py`.

| Package | Version | License | Source | Installed license |
| --- | --- | --- | --- | --- |
| Fancyapps UI (Fancybox) | 6.1.14 | `LicenseRef-Fancyapps-UI` | `https://registry.npmjs.org/@fancyapps/ui/-/ui-6.1.14.tgz` | `vendor/fancybox/LICENSE.md` |
| Font Awesome Free | 7.1.0 | `CC-BY-4.0 AND OFL-1.1 AND MIT` | `https://registry.npmjs.org/@fortawesome/fontawesome-free/-/fontawesome-free-7.1.0.tgz` | `vendor/fontawesome/LICENSE.txt` |
| Highlight.js CDN assets | 11.11.1 | `BSD-3-Clause` | `https://registry.npmjs.org/@highlightjs/cdn-assets/-/cdn-assets-11.11.1.tgz` | `vendor/highlight/LICENSE` |
| KaTeX | 0.16.47 | `MIT` | `https://registry.npmjs.org/katex/-/katex-0.16.47.tgz` | `vendor/katex/LICENSE` |
| markdown-it | 15.0.0 | `MIT` | `https://registry.npmjs.org/markdown-it/-/markdown-it-15.0.0.tgz` | `vendor/markdown-it/LICENSE` |
| Mermaid | 11.12.0 | `MIT` | `https://registry.npmjs.org/mermaid/-/mermaid-11.12.0.tgz` | `vendor/mermaid/LICENSE` |
| PDF.js (`pdfjs-dist`) | 6.2.108 | `Apache-2.0` | `https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.2.108.tgz` | `vendor/pdfjs/LICENSE` |
| pinyin-pro | 3.28.0 | `MIT` | `https://registry.npmjs.org/pinyin-pro/-/pinyin-pro-3.28.0.tgz` | `vendor/pinyin-pro/LICENSE` |
| SortableJS | 1.15.6 | `MIT` | `https://registry.npmjs.org/sortablejs/-/sortablejs-1.15.6.tgz` | `vendor/sortablejs/LICENSE` |
| web-highlighter | 0.7.4 | `MIT` | `https://registry.npmjs.org/web-highlighter/-/web-highlighter-0.7.4.tgz` | `vendor/web-highlighter/LICENSE` |

## Fancyapps UI licensing

Fancybox remains governed by the upstream Fancyapps UI license, which is not
an SPDX-listed open-source license. The upstream notice states that use of the
software requires agreement to the Fancyapps UI License Agreement and directs
users to Fancyapps licensing and pricing. Distributors must confirm that their
use is covered by an appropriate Fancyapps license; consult the installed
`vendor/fancybox/LICENSE.md` for the complete upstream notice.

## Font Awesome licensing

Font Awesome's CSS code is MIT-licensed, its webfonts are licensed under
`OFL-1.1`, and its icons are licensed under `CC-BY-4.0`. The installed
`vendor/fontawesome/LICENSE.txt` contains the complete terms and attribution.
