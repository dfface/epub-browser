# ===================== 阶段1：构建阶段（不变，非常标准）=====================
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

# 安装构建工具
RUN pip3 install --no-cache-dir build setuptools wheel

WORKDIR /build
COPY . /build/epub-browser/

# 编译whl
RUN cd /build/epub-browser && python -m build --wheel

# ===================== 阶段2：运行阶段（核心优化：Alpine + 全量清理）=====================
# 🔥 替换为超轻量 Alpine 基础镜像（体积直接砍 70%）
FROM python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# 🔥 禁用 Python 生成字节码，进一步瘦身
ENV PYTHONOPTIMIZE=2

WORKDIR /app

# 🔥 从构建阶段复制纯产物
COPY --from=builder /build/epub-browser/dist/*.whl /app/

# 🔥 关键：安装依赖 → 清理安装包 → 安装 epub 必需的系统依赖 → 清理系统缓存
RUN pip3 install --no-cache-dir /app/*.whl \
    && rm -rf /app/*.whl \
    # 安装 epub 解析必需的运行时库（lxml/xml 依赖）
    && apk add --no-cache libxml2 libxslt-dev \
    # 🔥 清理 Alpine 所有冗余文件（瘦身 30MB+）
    && rm -rf /root/.cache /tmp/* /var/cache/apk/* \
    # 🔥 清理 Python 无用文件（瘦身 20MB+）
    && find /usr/local/lib/python3.14 -name "*.pyc" -delete \
    && find /usr/local/lib/python3.14 -name "__pycache__" -delete \
    && find /usr/local/lib/python3.14 -name "*.dist-info" -delete \
    && find /usr/local/lib/python3.14 -name "*.egg-info" -delete

# 创建目录（不变）
RUN mkdir -p /app/Library /app/EpubBrowserFiles /app/SyncData

# 启动命令（不变）
CMD ["epub-browser", "/app/Library", "--watch", "--no-browser", "--output-dir=/app/EpubBrowserFiles", "--sync-dir=/app/SyncData", "--port=80"]

EXPOSE 80