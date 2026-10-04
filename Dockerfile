# syntax=docker/dockerfile:1
# One image with the built web app and the Python backend.
#   docker compose up -d        (see docker-compose.yml)
# or
#   docker build -t custom-stock-analysis .
#   docker run -p 8000:8000 --env-file .env -v ./data:/app/data custom-stock-analysis

# ---- stage 1: build the web app into static/ ----
FROM node:22-alpine AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# vite writes to ../static (see web/vite.config.ts)
RUN npm run build

# ---- stage 2: the server ----
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Run as an unprivileged user from the start, so nothing needs re-owning.
RUN useradd --uid 1000 --create-home app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app
WORKDIR /app

# Dependencies first so code edits do not reinstall them.
COPY --chown=app:app pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=1000,gid=1000 \
    uv sync --locked --no-dev

COPY --chown=app:app server.py ./
COPY --chown=app:app api ./api
COPY --chown=app:app src ./src
COPY --chown=app:app data_provider ./data_provider
COPY --chown=app:app --from=web /build/static ./static

# The database lives in /app/data (mount it to keep history across upgrades).
ENV PATH="/app/.venv/bin:$PATH" \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8000 \
    DATABASE_PATH=/app/data/stock_analysis.db
VOLUME ["/app/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/tiered/status', timeout=4)" || exit 1
CMD ["python", "server.py"]
