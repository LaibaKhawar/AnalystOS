# AnalystOS backend for Render's free plan: the API with PostgreSQL 16 (pgvector) and Redis in one container,
# so it needs no separate (expiring) free database. The disk is ephemeral: every start re-creates the database
# with the demo account and sample datasets. Build context: the repository root.

FROM python:3.11-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-common gnupg curl ca-certificates \
 && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
 && apt-get install -y --no-install-recommends postgresql-16 postgresql-16-pgvector redis-server \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 libffi8 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.lock backend/pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini backend/requirements.lock ./
COPY backend/scripts ./scripts
COPY backend/evals/data ./evals/data
COPY deploy/render/start.sh /start.sh
RUN chmod +x /start.sh && mkdir -p /data /pg && chown postgres:postgres /pg

ENV PYTHONPATH=/app \
    MALLOC_ARENA_MAX=2 \
    DATA_DIR=/data \
    DATABASE_URL=postgresql+psycopg://analystos:analystos@127.0.0.1:5432/analystos \
    REDIS_URL=redis://127.0.0.1:6379/0
CMD ["/start.sh"]
