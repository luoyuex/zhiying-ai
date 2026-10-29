# 智盈 AI 后端镜像：API、worker、一次性迁移共用
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# 先建用户与目录，后续 COPY 直接带属主，避免 chown 把 .venv 复制成新层
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/backend/logs \
    && chown -R app:app /app

WORKDIR /app/backend
USER app

# 先装依赖，源码改动不会让依赖层失效
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=app:app . .

EXPOSE 8010

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
