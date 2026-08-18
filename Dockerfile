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

# /app/Library is EPUB input. Mount it read-only when possible.
# /app/EpubBrowserFiles is durable Server data and must be writable/persistent.
# /app/SyncData is optional, read-only legacy bookshelf import data.
RUN mkdir -p /app/Library /app/EpubBrowserFiles /app/SyncData
VOLUME ["/app/EpubBrowserFiles"]

EXPOSE 80

CMD ["epub-browser", "server", "/app/Library", "--server-dir=/app/EpubBrowserFiles", "--legacy-sync-dir=/app/SyncData", "--watch", "--host=0.0.0.0", "--no-browser", "--port=80"]
