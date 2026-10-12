"""Uploaded datasets and external database connections (both are data sources)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user, owned_source
from app.api.schemas import ColumnOut, ColumnPatch, ConnectionIn, SourceOut, TableOut
from app.core.config import get_settings
from app.core.errors import ConnectionFailed, NotFoundError, ValidationFailed
from app.core.security import encrypt_secret
from app.db.base import utcnow
from app.db.models import ColumnMetadata, DataSource, Dataset, DatasetVersion, TableMetadata, User
from app.db.session import get_db
from app.services.datasources.base import QueryFailed
from app.services.datasources.factory import engine_for
from app.services.datasources.introspect import introspect_source
from app.services.datasources.sql_engine import DEFAULT_PORTS, SQLAlchemyEngine
from app.services.ingestion.naming import quote_ident
from app.services.ingestion.service import ingest_upload

router = APIRouter(prefix="/api/sources", tags=["data sources"])


def _source_out(db: Session, source: DataSource) -> SourceOut:
    out = SourceOut.model_validate(source)
    out.has_password = bool(source.password_encrypted)
    out.table_count = len(source.tables)
    out.row_count = sum(t.row_count for t in source.tables)
    dataset = db.query(Dataset).filter(Dataset.data_source_id == source.id).first()
    if dataset:
        out.dataset_id, out.file_type, out.size_bytes = dataset.id, dataset.file_type, dataset.size_bytes
        version = db.get(DatasetVersion, dataset.current_version_id) if dataset.current_version_id else None
        out.ingestion_report = version.ingestion_report if version else None
    return out


@router.get("", response_model=list[SourceOut])
def list_sources(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[SourceOut]:
    sources = (db.query(DataSource).options(selectinload(DataSource.tables)).filter(DataSource.user_id == user.id)
               .order_by(DataSource.created_at.desc()).all())
    return [_source_out(db, s) for s in sources]


@router.post("/upload", response_model=SourceOut, status_code=201)
def upload(file: UploadFile = File(...), name: str | None = Form(None), sheets: str | None = Form(None),
           user: User = Depends(current_user), db: Session = Depends(get_db)) -> SourceOut:
    sheet_list = [s.strip() for s in sheets.split(",") if s.strip()] if sheets else None
    dataset = ingest_upload(db, user_id=user.id, stream=file.file, filename=file.filename or "upload.csv", name=name,
                            sheets=sheet_list)
    source = db.get(DataSource, dataset.data_source_id)
    assert source is not None
    return _source_out(db, source)


@router.post("/connections", response_model=SourceOut, status_code=201)
def create_connection(body: ConnectionIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SourceOut:
    if body.kind != "sqlite" and not body.host:
        raise ValidationFailed("Host is required")
    source = DataSource(
        user_id=user.id, kind=body.kind, name=body.name, status="pending", host=body.host,
        port=body.port or DEFAULT_PORTS.get(body.kind), database=body.database, username=body.username,
        password_encrypted=encrypt_secret(body.password) if body.password else None, db_schema=body.db_schema,
        allowed_tables=body.allowed_tables or None, restricted_columns=body.restricted_columns,
    )
    db.add(source)
    db.flush()
    _refresh(db, source)
    db.commit()
    return _source_out(db, source)


def _refresh(db: Session, source: DataSource) -> None:
    try:
        engine = engine_for(db, source)
    except ConnectionFailed:
        db.rollback()
        raise
    assert isinstance(engine, SQLAlchemyEngine)
    try:
        engine.test()
        introspect_source(db, source, engine)
        source.status, source.error = "ready", None
    except QueryFailed as exc:
        db.rollback()
        raise ConnectionFailed(f"Could not connect: {exc}") from exc
    finally:
        engine.close()
    source.last_checked_at = utcnow()


@router.post("/{source_id}/refresh", response_model=SourceOut)
def refresh_connection(source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SourceOut:
    source = owned_source(db, user, source_id)
    if source.kind == "file":
        raise ValidationFailed("Uploaded datasets are profiled at upload time")
    _refresh(db, source)
    db.commit()
    return _source_out(db, source)


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SourceOut:
    return _source_out(db, owned_source(db, user, source_id))


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    source = owned_source(db, user, source_id)
    dataset = db.query(Dataset).filter(Dataset.data_source_id == source.id).first()
    if dataset:
        import shutil

        shutil.rmtree(get_settings().datasets_dir / dataset.id, ignore_errors=True)
    db.delete(source)
    db.commit()


@router.get("/{source_id}/tables", response_model=list[TableOut])
def tables(source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[TableMetadata]:
    return list(owned_source(db, user, source_id).tables)


@router.get("/{source_id}/tables/{table_id}/preview")
def preview(source_id: str, table_id: str, user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> dict[str, object]:
    source = owned_source(db, user, source_id)
    table = next((t for t in source.tables if t.id == table_id), None)
    if table is None:
        raise NotFoundError("Table not found")
    engine = engine_for(db, source)
    try:
        hidden = {c.name for c in table.columns if c.is_pii}
        cols = ", ".join(quote_ident(c.name) if c.name not in hidden else f"'***' AS {quote_ident(c.name)}"
                         for c in table.columns)
        qualified = quote_ident(table.name)
        if source.db_schema:
            qualified = f"{quote_ident(source.db_schema)}.{qualified}"
        if engine.dialect == "mysql":
            cols = cols.replace('"', "`")
            qualified = qualified.replace('"', "`")
        result = engine.execute(f"SELECT {cols} FROM {qualified} LIMIT {get_settings().preview_rows}",  # noqa: S608
                                max_rows=get_settings().preview_rows, timeout_seconds=15)
    finally:
        engine.close()
    return {"columns": result.columns, "rows": result.rows, "masked_columns": sorted(hidden)}


@router.patch("/{source_id}/columns/{column_id}", response_model=ColumnOut)
def patch_column(source_id: str, column_id: str, body: ColumnPatch, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> ColumnMetadata:
    source = owned_source(db, user, source_id)
    column = db.get(ColumnMetadata, column_id)
    if column is None or column.table.data_source_id != source.id:
        raise NotFoundError("Column not found")
    if body.semantic_type is not None:
        column.semantic_type, column.semantic_confidence, column.semantic_source = body.semantic_type, 1.0, "user"
    if body.role is not None:
        column.role = body.role
        column.semantic_source = "user"
    if body.is_pii is not None:
        column.is_pii = body.is_pii
    db.commit()
    return column


@router.get("/{source_id}/tables/{table_id}/columns.csv", response_class=PlainTextResponse)
def schema_csv(source_id: str, table_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> str:
    source = owned_source(db, user, source_id)
    table = next((t for t in source.tables if t.id == table_id), None)
    if table is None:
        raise NotFoundError("Table not found")
    lines = ["name,original_name,type,role,semantic_type,confidence,missing_pct,distinct"]
    for c in table.columns:
        lines.append(f'{c.name},"{c.original_name}",{c.inferred_type},{c.role},{c.semantic_type},'
                     f"{c.semantic_confidence},{c.stats.get('missing_pct')},{c.stats.get('distinct_count')}")
    return "\n".join(lines)
