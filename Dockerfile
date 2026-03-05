# 选择轻量级的Python基础镜像（slim版本体积小，仅包含运行时依赖）
FROM python:3.14-slim

# 设置环境变量，避免Python产生.pyc文件，减少磁盘占用
ENV PYTHONDONTWRITEBYTECODE=1
# 禁用Python缓冲，确保日志能实时输出
ENV PYTHONUNBUFFERED=1

# 安装构建依赖（容器内构建需要pip、build等工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir build setuptools wheel

# 创建并设置工作目录（统一管理文件）
WORKDIR /app

# ===================== 核心修改：直接复制源码到容器 =====================
# 复制本地epub-browser源码到容器内（需保证本地Dockerfile同级有源码目录）
COPY . /app/epub-browser/

# 进入源码目录，在容器内构建并安装epub-browser
RUN cd /app/epub-browser \
    && python -m build --wheel \
    && pip3 install --no-cache-dir dist/*.whl \
    # 清理构建产物，减小镜像体积
    && rm -rf /app/epub-browser

# =====================================================================

# 创建必要的目录（Library用于存放epub文件，EpubBrowserFiles用于输出）
RUN mkdir -p /app/Library /app/EpubBrowserFiles

# 暴露80端口（与运行命令中的port一致）
EXPOSE 80

# 启动命令（严格按照要求执行，使用exec形式保证信号传递）
CMD ["epub-browser", "/app/Library", "--watch", "--no-browser", "--output-dir=/app/EpubBrowserFiles",  "--port=80"]