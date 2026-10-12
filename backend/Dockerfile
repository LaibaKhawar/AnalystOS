# AnalystOS backend image (API, worker and migrations share it).
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg

# WeasyPrint (PDF reports) needs pango; curl for health checks.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 libffi8 \
      fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Exact versions from requirements.lock (the set the test suite runs against).
COPY requirements.lock pyproject.toml ./
RUN pip install -r requirements.lock

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY evals ./evals
COPY scripts ./scripts
RUN pip install --no-deps . \
 && useradd --uid 10001 --create-home analystos \
 && mkdir -p /data && chown analystos:analystos /data

ENV DATA_DIR=/data
EXPOSE 8000
USER analystos
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
