# syntax=docker/dockerfile:1
# Base images are pinned by digest (M-02); bump tag and digest together.
ARG PYTHON_IMAGE=python:3.13-slim-trixie@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21

FROM ${UV_IMAGE} AS uv

# Tailwind standalone CLI, no Node.js; pinned by version and checksum (M-02). The binary is
# dynamically linked, so it must match the target architecture. An ADD cannot be conditional:
# one stage per architecture, selected by TARGETARCH; BuildKit fetches only the one it needs.
FROM scratch AS tailwind-amd64
ADD --checksum=sha256:dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a --chmod=755 \
    https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/tailwindcss-linux-x64 /tailwindcss

FROM scratch AS tailwind-arm64
ADD --checksum=sha256:55fd0b241214eff3de1e8ee4f22796662f2d2e7a49bcfca7477cfd0bac398195 --chmod=755 \
    https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/tailwindcss-linux-arm64 /tailwindcss

FROM tailwind-${TARGETARCH} AS tailwind

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONPATH=/app/src:/app \
    PATH="/opt/venv/bin:${PATH}"
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid app --home-dir /home/app --create-home --shell /usr/sbin/nologin app
WORKDIR /app

# Runtime dependencies only, resolved strictly from uv.lock
FROM base AS deps
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Minified stylesheet for the runtime image
FROM base AS assets
COPY --from=tailwind /tailwindcss /usr/local/bin/tailwindcss
COPY src ./src
RUN tailwindcss --input=src/assets/app.css --output=src/static/css/build/app.css --minify

# Runtime image: gunicorn, no dev tools, source owned by root and read-only for the app user
FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
COPY src ./src
COPY --from=assets /app/src/static/css/build ./src/static/css/build
ENV DJANGO_DEBUG=false \
    STATIC_MANIFEST=true
RUN DJANGO_SECRET_KEY=collectstatic-only POSTGRES_DB=- POSTGRES_USER=- POSTGRES_PASSWORD=- \
    OIDC_RP_CLIENT_SECRET=- python src/manage.py collectstatic --noinput --verbosity 0
USER app
EXPOSE 8000
CMD ["gunicorn", "--chdir", "src", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--access-logfile", "-"]

# Development image: adds test and lint tooling; source is bind-mounted by compose
FROM deps AS dev
# GNU gettext for makemessages/compilemessages; development only, the runtime image ships the
# compiled catalogues from the repository
RUN apt-get update \
 && apt-get install --yes --no-install-recommends gettext \
 && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project
ENV UV_CACHE_DIR=/tmp/uv-cache
COPY --from=tailwind /tailwindcss /usr/local/bin/tailwindcss
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["python", "src/manage.py", "runserver", "0.0.0.0:8000"]
