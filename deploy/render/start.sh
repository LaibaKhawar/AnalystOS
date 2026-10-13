#!/bin/sh
# Start a small local PostgreSQL and Redis, prepare the database, then serve the API on $PORT.
set -eu
PG_BIN=/usr/lib/postgresql/16/bin
as_pg() { su postgres -s /bin/sh -c "$1"; }

if [ ! -s /pg/PG_VERSION ]; then
  as_pg "$PG_BIN/initdb -D /pg -U postgres --auth=trust >/dev/null"
fi
# Sized for a 512 MB instance shared with the API.
as_pg "$PG_BIN/pg_ctl -D /pg -l /tmp/postgres.log -w start -o '-c listen_addresses=127.0.0.1 -c shared_buffers=32MB -c max_connections=30 -c work_mem=4MB -c maintenance_work_mem=16MB'"
psql -h 127.0.0.1 -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='analystos'" | grep -q 1 \
  || psql -h 127.0.0.1 -U postgres -qc "CREATE ROLE analystos LOGIN PASSWORD 'analystos'"
psql -h 127.0.0.1 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='analystos'" | grep -q 1 \
  || psql -h 127.0.0.1 -U postgres -qc "CREATE DATABASE analystos OWNER analystos"
psql -h 127.0.0.1 -U postgres -d analystos -qc "CREATE EXTENSION IF NOT EXISTS vector"
redis-server --daemonize yes --save '' --appendonly no --bind 127.0.0.1 --maxmemory 32mb >/dev/null

cd /app
alembic upgrade head
python scripts/seed_demo.py --role analyst
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips '*'
