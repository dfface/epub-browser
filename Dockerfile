FROM python:3.14-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir build setuptools wheel

WORKDIR /build/epub-browser
# Keep the build input limited to the files that contribute to the wheel.  This
# also prevents documentation and local development state from invalidating
# the wheel build cache.
COPY setup.py MANIFEST.in README.md README.zh-CN.md License.txt ./
COPY THIRD_PARTY_NOTICES.md ./
COPY third_party ./third_party
COPY tools/sync_vendor_assets.py tools/verify_release_artifacts.py ./tools/
COPY epub_browser ./epub_browser
RUN python tools/sync_vendor_assets.py fetch \
    && python tools/sync_vendor_assets.py verify \
    && python -m build --wheel \
    && python tools/verify_release_artifacts.py --wheel dist/*.whl \
    && python -m pip install --no-cache-dir --no-compile --ignore-installed \
        --prefix=/runtime dist/*.whl


FROM python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=2

WORKDIR /app
COPY --from=builder /runtime/ /usr/local/

# /app/Library is EPUB input. The Docker default stores book IDs in the EPUB,
# so the mount must be writable when an ID needs to be embedded or refreshed.
# /app/EpubBrowserFiles is durable Server data and must be writable/persistent.
# /app/SyncData is optional, read-only legacy bookshelf import data.
# Interactive first start uses the one-time /setup page. Keep the published
# port private until it is complete. For unattended setup, provide
# EPUB_BROWSER_ADMIN_USERNAME and mount a read-only
# EPUB_BROWSER_ADMIN_PASSWORD_FILE under /run/secrets.
RUN mkdir -p /app/Library /app/EpubBrowserFiles /app/SyncData /run/secrets
VOLUME ["/app/EpubBrowserFiles"]

EXPOSE 80

CMD ["epub-browser", "server", "/app/Library", "--book-id-storage=embedded", "--server-dir=/app/EpubBrowserFiles", "--legacy-sync-dir=/app/SyncData", "--watch", "--host=0.0.0.0", "--no-browser", "--port=80"]
