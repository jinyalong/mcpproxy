# 使用官方Python镜像作为基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 配置pip和uv使用阿里云源
RUN mkdir -p /root/.pip && \
    echo "[global]" > /root/.pip/pip.conf && \
    echo "index-url = https://mirrors.aliyun.com/pypi/simple/" >> /root/.pip/pip.conf && \
    echo "trusted-host = mirrors.aliyun.com" >> /root/.pip/pip.conf && \
    mkdir -p /root/.uv && \
    echo '{"index-url": "https://mirrors.aliyun.com/pypi/simple", "trusted-host": ["mirrors.aliyun.com"]}' > /root/.uv/config.toml

# 配置apt使用阿里云源
RUN echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-backports main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

# 安装Node.js和其他依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    ca-certificates \
    gnupg && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    npm config set registry https://registry.npmmirror.com && \
    npm install -g npm@10.2.4 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 验证安装
RUN node --version && npm --version && npx --version

# 首先复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -r requirements.txt

# 复制源代码和其他文件
COPY src/ ./src/
COPY assets/ ./assets/

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV UV_TRUSTED_HOST=mirrors.aliyun.com

# 启动命令
CMD ["python", "src/main.py"]