# EPUB Browser

> **A personal EPUB reader and static-site generator. Read privately. Publish anywhere.**

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](License.txt)
[![GitHub stars](https://img.shields.io/github/stars/dfface/epub-browser)](https://github.com/dfface/epub-browser)

EPUB Browser turns an EPUB collection into a polished reading library for any modern browser. Use it in two equally first-class ways: run a private library for yourself, or generate a complete static reading site and deploy it directly to Pages and other static hosts. Keep your books where you choose, read on the devices you already own, and shape the experience around your habits.

[Try the demo](https://epub-browser-test.yuhan.tech) · [Install from PyPI](https://pypi.org/project/epub-browser/) · [Report an issue](https://github.com/dfface/epub-browser/issues)

## Read privately. Publish simply.

Most reading tools ask you to adapt to their library, account, and interface. EPUB Browser takes the opposite view: your collection is the center of the product.

- **Your library stays yours.** Run it locally or on your own server. No account is required to start reading.
- **Your library is ready to publish.** Generate a self-contained static site, then deploy it directly to Cloudflare Pages, GitHub Pages, or any static host.
- **Your reading can be personal.** Choose a theme, font, font size, page-turning or scrolling, and optional custom styles.
- **Your attention stays with the book.** Use pure reading mode, resume where you left off, and keep notes close to the passage that matters.

It is designed as both a dependable reading companion and a practical publishing tool: quiet when you are immersed, capable when you need to organise, annotate, or turn a collection into a shareable website.

## What you can do

### Build a library that feels familiar

- Import one EPUB, a folder, or an entire Calibre library.
- Search titles, authors, and tags — including pinyin search for Chinese metadata.
- Read Calibre tags and descriptions directly from EPUB metadata.
- Sort library surfaces and organise a personal bookshelf with nested groups, tags, import/export, and optional sync.
- Keep the library current with `--watch` when files are added or updated.

### Settle into the page

- Switch between scrolling and page-turning reading modes.
- Resume the last chapter and reading location.
- Adjust font family and size, use one of several themes, or add per-book custom CSS.
- Use continuous scroll for books with many short sections.
- Enter pure reading mode when you want the interface to disappear.
- Zoom images, highlight code, and use keyboard navigation.
- Read comfortably on phones, tablets, desktops, and Kindle/Silk browsers.

### Keep what you notice

- Highlight selected text, add notes, and copy the original selected passage.
- Choose highlight colours and manage them in Settings.
- Store annotations locally or use a compatible cloud API; export annotations as JSON whenever you need them.

### Take it where you read

- Install the generated library as a Progressive Web App on supported browsers.
- Run the included local server, or generate static files for Cloudflare Pages, GitHub Pages, Apache, Nginx, and similar hosts.
- Use the cache update control when you deploy a refreshed library.

## Start reading in two minutes

### Install

```bash
pip install epub-browser
```

### Open a book or library

```bash
# One book
epub-browser path/to/book.epub

# A few books
epub-browser book1.epub book2.epub book3.epub

# Every EPUB in a folder (including a Calibre library)
epub-browser /path/to/books
```

EPUB Browser creates a library and opens it in your browser. By default, the local server listens on port `8000` and is available to devices on your local network.

## Common workflows

### Keep a local library running

Use a fixed output directory when you want generated files and bookshelf data to persist between runs:

```bash
epub-browser /path/to/books \
  --output-dir /path/to/epub-browser-library \
  --sync-dir /path/to/epub-browser-sync \
  --keep-files \
  --no-browser
```

Add `--watch` to monitor the source folder and add or update books automatically:

```bash
epub-browser /path/to/books --watch --output-dir /path/to/epub-browser-library --keep-files
```

### Generate a static site for Pages

Use `--no-server` when the output will be served by your own web server or static host:

```bash
epub-browser /path/to/books \
  --output-dir /path/to/public-library \
  --no-server
```

Upload the contents of `/path/to/public-library` to your preferred static host. This is the direct deployment path for Cloudflare Pages, GitHub Pages, Apache, Nginx, and similar platforms—no application server is required.

### Useful options

```bash
# Choose a port and do not launch a browser
epub-browser book.epub --port 8080 --no-browser

# Keep generated files after a temporary local reading session
epub-browser book.epub --keep-files

# See every available option
epub-browser --help
```

| Option | Purpose |
| --- | --- |
| `--output-dir`, `-o` | Directory for generated library files. |
| `--no-server` | Generate deployable static files without starting the local server. |
| `--keep-files` | Preserve generated files after the local server stops. |
| `--watch`, `-w` | Watch the input directory for EPUB additions and changes. |
| `--sync-dir` | Directory used by the optional bookshelf sync data. |
| `--port`, `-p` | Local server port; defaults to `8000`. |
| `--no-browser` | Do not open a browser automatically. |

## Reading controls

| Need | Where to find it |
| --- | --- |
| Change font, size, or reading mode | **Settings** in a chapter |
| Add custom styles | **Settings → Reading → Custom styles** |
| Turn pages | Left/Right Arrow or Space; use the page controls in page-turning mode |
| Read continuously | **Settings → Reading**; scrolling mode only |
| Focus on the book | **Pure** in the navigation controls, or click the page centre on supported devices |
| Highlight, annotate, or copy | Select original text in the reading area |
| Update an installed library | **Update** on the library page |

Kindle/Silk browsers are detected automatically and receive an e-reader-friendly mode. Some browser-heavy features, such as code highlighting and the bookshelf, are intentionally reduced there.

## Deploy as a static site or run continuously

The `--no-server` output is a complete static reading site, ready to deploy wherever static files are hosted. For a self-hosted always-on library, run the command above with a persistent output directory and supervise it with your platform's service manager.

### Docker

```bash
docker run -d \
  --name epub-browser \
  -p 8080:80 \
  -v /path/to/your-books:/app/Library \
  -v /path/to/generated-library:/app/EpubBrowserFiles \
  -v /path/to/sync-data:/app/SyncData \
  epub-browser:latest
```

Mount paths and ownership should match the user running the container.

## A note on EPUB metadata

EPUB Browser reads standard EPUB metadata, including title, author, `dc:subject` tags, and descriptions. For Calibre-managed libraries, edit metadata in Calibre and save the book after editing so the EPUB file itself is updated.

If a book has a broken table of contents or malformed markup, opening and reconverting it with [Calibre](https://calibre-ebook.com/) often produces a standards-compliant EPUB that reads correctly.

## Contributing

Issues, bug reports, and pull requests are welcome at [dfface/epub-browser](https://github.com/dfface/epub-browser). A useful report includes the EPUB source when it can be shared, the browser/device, the reading mode, and clear reproduction steps.

## License

[MIT](License.txt)
