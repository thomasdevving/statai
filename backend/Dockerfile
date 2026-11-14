# Ghost Chef backend image (BE-04).
#
# The build context is the REPOSITORY ROOT, because the image needs backend/, ai/ and web/:
#
#     docker build -f backend/Dockerfile -t ghostchef-backend .
#     docker run -p 8000:8000 -e DEMO_API_KEY=dev-key ghostchef-backend
#
# Defaults: STORAGE=memory, GHOSTCHEF_AI_FAKE=1. Production sets both through Railway variables.
# Exclusions for a local build: backend/Dockerfile.dockerignore (BuildKit reads it automatically).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg is used from BE-06 on; installed now so the image does not change later.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /srv --no-create-home app

WORKDIR /srv

# ghostchef_ai: a regular (non-editable) install, so the fixture is located by env var.
COPY ai/pyproject.toml /srv/ai/pyproject.toml
COPY ai/src /srv/ai/src
COPY ai/fixtures /srv/ai/fixtures
RUN pip install /srv/ai

# Backend: only the files the server and its scripts need (never .env, .data or .venv).
# Editable install so app/config.py resolves relative paths against /srv/backend.
COPY backend/pyproject.toml /srv/backend/pyproject.toml
COPY backend/app /srv/backend/app
COPY backend/scripts /srv/backend/scripts
COPY backend/migrations /srv/backend/migrations
RUN pip install -e /srv/backend

# Static web app, served at /app/.
COPY web /srv/web

RUN mkdir -p /srv/data && chown app:app /srv/data

ENV GHOSTCHEF_FIXTURE_DIR=/srv/ai/fixtures \
    WEB_DIR=/srv/web \
    DATA_DIR=/srv/data \
    STORAGE=memory \
    GHOSTCHEF_AI_FAKE=1

USER app
WORKDIR /srv/backend
EXPOSE 8000

# ONE worker: session state (latest frame, /watch in-flight guard, metrics) is in-process memory.
# --proxy-headers: behind Railway's TLS proxy, so generated URLs (monitor frame URL, memory-mode
# file URLs) use https and the public host. No auth decision depends on the client address.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
