"""Build query engines and validation catalogs from persisted DataSource rows."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConnectionFailed, NotFoundError
from app.core.security import decrypt_secret
from app.db.models import Dataset, DatasetVersion, DataSource
from app.services.datasources.base import QueryEngine
from app.services.datasources.duckdb_engine import DuckDBEngine
from app.services.datasources.sql_engine import SQLAlchemyEngine, build_url
from app.services.sql.validator import Catalog

EXTERNAL_KINDS = {"postgresql", "mysql", "sqlite"}


def sqlite_allowed_root() -> Path:
    root = get_settings().data_dir / "sqlite"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def resolve_sqlite_path(database: str) -> str:
    """SQLite files must live under DATA_DIR/sqlite so a connection cannot open arbitrary host files."""
    root = sqlite_allowed_root()
    candidate = Path(database)
    path = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if root not in path.parents and path != root:
        raise ConnectionFailed(f"SQLite databases must be placed under {root}")
    if not path.exists():
        raise ConnectionFailed(f"SQLite database file not found: {path.name}")
    return str(path)


def engine_for(db: Session, source: DataSource) -> QueryEngine:
    settings = get_settings()
    if source.kind == "file":
        dataset = db.query(Dataset).filter(Dataset.data_source_id == source.id).one_or_none()
        if not dataset or not dataset.current_version_id:
            raise NotFoundError("Dataset has no ready version")
        version = db.get(DatasetVersion, dataset.current_version_id)
        if version is None:
            raise NotFoundError("Dataset version not found")
        return DuckDBEngine(version.storage_path, version.parquet_dir)
    if source.kind in EXTERNAL_KINDS:
        password = decrypt_secret(source.password_encrypted) if source.password_encrypted else None
        database = resolve_sqlite_path(source.database or "") if source.kind == "sqlite" else source.database
        url = build_url(
            source.kind,
            host=source.host,
            port=source.port,
            database=database,
            username=source.username,
            password=password,
        )
        return SQLAlchemyEngine(source.kind, url, schema=source.db_schema, timeout_seconds=settings.sql_timeout_seconds)
    raise ConnectionFailed(f"Unsupported data source kind: {source.kind}")


def catalog_for(source: DataSource) -> Catalog:
    tables = {t.name.lower(): {c.name.lower(): c.physical_type for c in t.columns} for t in source.tables}
    restricted: set[tuple[str, str]] = set()
    for table in source.tables:
        for column in table.columns:
            if column.is_pii:
                restricted.add((table.name.lower(), column.name.lower()))
    for entry in source.restricted_columns or []:
        if isinstance(entry, str) and "." in entry:
            t, c = entry.lower().split(".", 1)
            restricted.add((t, c))
    allowed = {t.lower() for t in source.allowed_tables} if source.allowed_tables else None
    return Catalog(tables=tables, allowed_tables=allowed, restricted_columns=restricted)
