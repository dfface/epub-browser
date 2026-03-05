# 选择轻量级的Python基础镜像（slim版本体积小，仅包含运行时依赖）
FROM python:3.11-slim

# 设置环境变量，避免Python产生.pyc文件，减少磁盘占用
ENV PYTHONDONTWRITEBYTECODE=1
# 禁用Python缓冲，确保日志能实时输出
ENV PYTHONUNBUFFERED=1

# 创建并设置工作目录（统一管理文件）
WORKDIR /app

# 安装epub-browser依赖（--no-cache-dir避免缓存，减小镜像体积）
RUN pip3 install --no-cache-dir epub-browser

# 创建必要的目录（Library用于存放epub文件，EpubBrowserFiles用于输出）
RUN mkdir -p /app/Library /app/EpubBrowserFiles

# 暴露80端口（与运行命令中的port一致）
EXPOSE 80

# 启动命令（严格按照要求执行，使用exec形式保证信号传递）
CMD ["epub-browser", "/app/Library", "--watch", "--no-browser", "--output-dir=/app/EpubBrowserFiles",  "--port=80"]