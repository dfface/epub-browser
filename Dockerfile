FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir build setuptools wheel

WORKDIR /build/epub-browser
COPY . .
RUN python -m build --wheel


FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=2

WORKDIR /app
COPY --from=builder /build/epub-browser/dist/*.whl /tmp/packages/
RUN pip install --no-cache-dir /tmp/packages/*.whl \
    && rm -rf /tmp/packages

# /app/Library is EPUB input. Default sidecar creation/refresh needs a writable mount.
# /app/EpubBrowserFiles is durable Server data and must be writable/persistent.
# /app/SyncData is optional, read-only legacy bookshelf import data.
# Interactive first start uses the one-time /setup page. Keep the published
# port private until it is complete. For unattended setup, provide
# EPUB_BROWSER_ADMIN_USERNAME and mount a read-only
# EPUB_BROWSER_ADMIN_PASSWORD_FILE under /run/secrets.
RUN mkdir -p /app/Library /app/EpubBrowserFiles /app/SyncData /run/secrets
VOLUME ["/app/EpubBrowserFiles"]

EXPOSE 80

CMD ["epub-browser", "server", "/app/Library", "--server-dir=/app/EpubBrowserFiles", "--legacy-sync-dir=/app/SyncData", "--watch", "--host=0.0.0.0", "--no-browser", "--port=80"]
