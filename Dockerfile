FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim

ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN echo "deb https://mirrors.aliyun.com/debian/ bookworm main" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security bookworm-security main" >> /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/* || true

RUN apt-get update && apt-get install -y \
    curl \
    tar \
    xz-utils \
    ca-certificates \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    fontconfig \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN NODE_VERSION=18.20.4 && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then NODE_ARCH="x64"; \
    elif [ "$ARCH" = "arm64" ]; then NODE_ARCH="arm64"; \
    else NODE_ARCH="$ARCH"; fi && \
    curl -fsSL https://registry.npmmirror.com/-/binary/node/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.gz -o /tmp/node.tar.gz && \
    tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 && \
    rm /tmp/node.tar.gz && \
    ln -s /usr/local/bin/node /usr/local/bin/nodejs

RUN node --version && npm --version && npm config set registry https://registry.npmmirror.com/

COPY requirements.txt .
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/ && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn && \
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install

COPY . .
RUN cd frontend && npm run build

RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 8503

HEALTHCHECK CMD curl --fail http://localhost:8503/api/health || exit 1

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8503"]
