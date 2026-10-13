"""Run the whole AnalystOS backend on Modal's free CPU credits: API, Postgres (pgvector), Redis and data in one
container that scales to zero.

    modal secret create analystos-app SECRET_KEY=... ENCRYPTION_KEY=... LLM_API_KEY=...   # see docs/deployment.md
    modal deploy deploy/modal/app_server.py
    -> https://<workspace>--analystos-app-web.modal.run  (API under /api)

Design notes:
* One container at most (`max_containers=1`): Postgres and the DuckDB dataset files live with the API.
* Postgres runs on the container's local disk (databases do not belong on network volumes). The database is dumped
  to a Modal Volume when the container stops and every few minutes while it runs, and restored on the next start.
  Uploaded files and DuckDB datasets are written to the Volume directly.
* Analyses run in a background thread of the API process (RUN_ANALYSES_INLINE), generated Python runs in Modal
  Sandboxes, and the model is the CPU llama.cpp deployment (`llm_cpu.py`) or any OpenAI-compatible endpoint.
* Scheduled analyses need an always-on worker; a scale-to-zero container has none, so schedules only run while the
  container is up.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import modal

_here = Path(__file__).resolve()
ROOT = _here.parents[2] if len(_here.parents) > 2 else Path("/")  # repo root locally; unused inside the container
VOL = "/vol"
PG_DATA = "/var/lib/analystos-pg"
DUMP = f"{VOL}/analystos.dump"
DB_URL = "postgresql+psycopg://analystos:analystos@127.0.0.1:5432/analystos"
LLM_URL = os.environ.get("ANALYSTOS_LLM_URL", "https://laibakhawar--analystos-llm-cpu-serve.modal.run/v1")
PG_BIN = "/usr/lib/postgresql/16/bin"

image = (
    modal.Image.debian_slim(python_version="3.11")
    # pgvector comes from the PostgreSQL project's apt repository (PGDG), not Debian's.
    .apt_install("postgresql-common", "gnupg", "curl", "ca-certificates")
    .run_commands("/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y")
    .apt_install(
        "postgresql-16",
        "postgresql-16-pgvector",
        "redis-server",
        "libpango-1.0-0",
        "libpangoft2-1.0-0",
        "libharfbuzz0b",
        "libharfbuzz-subset0",
        "libffi8",
        "fonts-dejavu-core",
    )
    .pip_install_from_requirements(str(ROOT / "backend" / "requirements.lock"))
    .pip_install("modal>=1.0")
    .env(
        {
            "PYTHONPATH": "/app",
            "ENVIRONMENT": "production",
            "DATABASE_URL": DB_URL,
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "DATA_DIR": f"{VOL}/data",
            "RUN_ANALYSES_INLINE": "true",
            "SANDBOX_BACKEND": "modal",
            "LLM_BASE_URL": LLM_URL,
            "LLM_MODEL": "qwen3",
            "LLM_TIMEOUT_SECONDS": "600",
            "EMBEDDING_BASE_URL": "",
            "QUESTIONS_PER_HOUR": "20",
            "LOG_JSON": "true",
            "METRICS_ENABLED": "false",
        }
    )
    .add_local_dir(
        str(ROOT / "backend"),
        "/app",
        ignore=[".venv", "var", "**/__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".env", "tests"],
    )
)
volume = modal.Volume.from_name("analystos-app-data", create_if_missing=True)
app = modal.App("analystos-app")


def _sh(cmd: str, **kwargs: object) -> None:
    subprocess.run(cmd, shell=True, check=True, **kwargs)  # noqa: S602 - fixed commands


def _as_postgres(cmd: str) -> None:
    _sh(f"su postgres -c '{cmd}'")


@app.cls(
    image=image,
    cpu=4,
    memory=4096,
    volumes={VOL: volume},
    secrets=[modal.Secret.from_name("analystos-app")],
    scaledown_window=15 * 60,
    timeout=24 * 60 * 60,
    max_containers=1,
)
@modal.concurrent(max_inputs=50)
class Backend:
    @modal.enter()
    def start(self) -> None:
        os.makedirs(f"{VOL}/data", exist_ok=True)
        _sh(f"mkdir -p {PG_DATA} && chown -R postgres:postgres {PG_DATA}")
        _as_postgres(f"{PG_BIN}/initdb -D {PG_DATA} -U postgres --auth=trust >/dev/null")
        _as_postgres(f'{PG_BIN}/pg_ctl -D {PG_DATA} -o "-c listen_addresses=127.0.0.1" -w start >/dev/null')
        _sh("psql -U postgres -h 127.0.0.1 -c \"CREATE ROLE analystos LOGIN PASSWORD 'analystos'\"")
        _sh("psql -U postgres -h 127.0.0.1 -c 'CREATE DATABASE analystos OWNER analystos'")
        _sh("psql -U postgres -h 127.0.0.1 -d analystos -c 'CREATE EXTENSION IF NOT EXISTS vector'")
        if os.path.exists(DUMP):
            # --no-owner: objects are recreated as the connecting role; errors on the extension are harmless.
            restore = f"pg_restore -U analystos -h 127.0.0.1 -d analystos --no-owner {DUMP}"
            subprocess.run(restore, shell=True, check=False)  # noqa: S602 - fixed command
        _sh("redis-server --daemonize yes --save '' --appendonly no >/dev/null")
        _sh("alembic upgrade head", cwd="/app")
        _sh("python scripts/seed_demo.py --role analyst", cwd="/app")
        volume.commit()
        threading.Thread(target=self._periodic_dump, daemon=True).start()

    def _dump(self) -> None:
        tmp = f"{DUMP}.tmp"
        result = subprocess.run(f"pg_dump -U analystos -h 127.0.0.1 -Fc -f {tmp} analystos", shell=True)  # noqa: S602
        if result.returncode == 0:
            os.replace(tmp, DUMP)
            volume.commit()

    def _periodic_dump(self) -> None:
        while True:
            time.sleep(300)
            self._dump()

    @modal.exit()
    def stop(self) -> None:
        self._dump()

    @modal.web_server(port=8000, startup_timeout=5 * 60)
    def web(self) -> None:
        # Inside the container: Modal routes the public URL to this port.
        cmd = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]  # noqa: S104
        subprocess.Popen([*cmd, "--proxy-headers", "--forwarded-allow-ips", "*"], cwd="/app")
