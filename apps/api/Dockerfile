FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Build context is the repository root (see render.yaml / docker-compose.yml) so
# the replay fixtures can be copied alongside the API.
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/ ./
COPY fixtures /app/fixtures

# Non-root runtime. Evidence storage is intentionally ephemeral on Render.
RUN useradd --create-home --shell /usr/sbin/nologin resolveai \
    && mkdir -p /app/var/evidence \
    && chown -R resolveai:resolveai /app
USER resolveai

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Migrations run on every boot, so a fresh Render Postgres always has the schema.
# Render injects PORT; the 8000 fallback keeps docker-compose working unchanged.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
