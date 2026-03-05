# ===================== 阶段1：构建阶段（Builder）=====================
# 用带构建依赖的基础镜像（仅用于编译whl，最终不会包含在产物镜像中）
FROM python:3.14-slim AS builder

# 禁用pyc文件生成、关闭缓冲，减少冗余
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装构建必需的依赖（编译whl需要的gcc、build工具等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*  # 清理apt缓存，减小builder镜像体积

# 安装python构建工具
RUN pip3 install --no-cache-dir build setuptools wheel

# 设置构建工作目录
WORKDIR /build

# 仅复制源码（核心：只传需要构建的文件，避免冗余）
COPY . /build/epub-browser/

# 编译生成whl包（产物会在 /build/epub-browser/dist/ 下）
RUN cd /build/epub-browser \
    && python -m build --wheel

# ===================== 阶段2：最终运行阶段（Runtime）=====================
# 用极简的python镜像（无构建依赖，体积更小），甚至可以用 alpine 镜像
FROM python:3.14-slim

# 同样禁用冗余配置
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 设置运行工作目录
WORKDIR /app

# 从builder阶段复制仅有的whl产物（核心：只拿最终需要的文件）
COPY --from=builder /build/epub-browser/dist/*.whl /app/

# 安装whl包（安装后删除whl文件，进一步减小体积）
RUN pip3 install --no-cache-dir /app/*.whl \
    && rm -rf /app/*.whl

# 创建必要的目录（Library用于存放epub文件，EpubBrowserFiles用于输出）
RUN mkdir -p /app/Library /app/EpubBrowserFiles

# 启动命令（严格按照要求执行，使用exec形式保证信号传递）
CMD ["epub-browser", "/app/Library", "--watch", "--no-browser", "--output-dir=/app/EpubBrowserFiles",  "--port=80"]

# 暴露端口（如果epub-browser需要）
EXPOSE 80