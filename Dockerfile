# Daily Scholar backend — Python 3.13-slim, multi-stage.
#
# Stage 1 (builder): install deps into a private venv.
# Stage 2 (runtime): copy venv + app, run uvicorn as a non-root user.
#
# Alembic migrations apply automatically on startup via create_tables().
# Build context = repo root; .dockerignore keeps it small.

# ============================================================
# Stage 1: builder
# ============================================================
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-time deps for any wheels that need to compile (cryptography, pillow-like)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# private venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# ============================================================
# Stage 2: runtime
# ============================================================
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
# the container honors $PORT — set by Railway (and Heroku-style PaaS) at
# runtime, by docker-compose, or defaults to 8000 here. BACKEND_PORT is a
# local-dev / .env name only (avoids Next.js PORT collision in `make start`);
# inside the container we stay on the Railway-canonical $PORT.

# minimal runtime deps; libffi for cryptography, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        libffi8 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 1001 app

# bring in the prebuilt venv
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app backend ./backend
COPY --chown=app:app config ./config
COPY --chown=app:app scripts ./scripts

# writable dirs for SQLite fallback + local-storage backend
RUN mkdir -p /app/data /app/uploads \
    && chown -R app:app /app/data /app/uploads

USER app

EXPOSE 8000

# uvicorn binds 0.0.0.0 inside the container; Railway / docker-compose maps it
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

# light shell-based healthcheck — hits /health (the lightweight one)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1
