"""Upload -> DuckDB dataset version -> profile -> semantic schema -> persisted metadata."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO

import duckdb
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import IngestionError
from app.core.logging import get_logger
from app.db.models import ColumnMetadata, Dataset, DatasetVersion, DataSource, TableMetadata
from app.services.ingestion.coercion import coerce_text_columns, reorder_columns
from app.services.ingestion.csv_reader import load_csv
from app.services.ingestion.excel_reader import load_excel
from app.services.ingestion.naming import quote_ident, sql_string, to_identifier
from app.services.ingestion.types import LoadedTable
from app.services.profiling.profiler import TableProfile, profile_table
from app.services.semantic.interpreter import interpret_table

log = get_logger(__name__)
SUPPORTED = {".csv": "csv", ".tsv": "csv", ".txt": "csv", ".xlsx": "xlsx", ".xlsm": "xlsx"}


def detect_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".xls":
        raise IngestionError("Legacy .xls files are not supported; save the workbook as .xlsx")
    if suffix not in SUPPORTED:
        raise IngestionError(f"Unsupported file type '{suffix or 'none'}'. Upload a .csv or .xlsx file")
    return SUPPORTED[suffix]


def save_upload(stream: BinaryIO, filename: str) -> tuple[Path, int, str]:
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    safe_name = to_identifier(Path(filename).stem, fallback="upload") + Path(filename).suffix.lower()
    target_dir = settings.uploads_dir / uuid.uuid4().hex  # unique per upload; never derived from user input
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    size = 0
    with target.open("wb") as out:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                shutil.rmtree(target_dir, ignore_errors=True)
                raise IngestionError(f"File exceeds the {settings.max_upload_mb} MB upload limit")
            digest.update(chunk)
            out.write(chunk)
    if size == 0:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise IngestionError("The uploaded file is empty")
    return target, size, digest.hexdigest()


def build_dataset_files(
    upload_path: Path, file_type: str, base_name: str, out_dir: Path, sheets: list[str] | None = None
) -> tuple[list[LoadedTable], list[TableProfile], dict[str, object]]:
    """Create the DuckDB file + parquet exports for an upload. Pure function of its inputs (testable)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "data.duckdb"
    parquet_dir = out_dir / "parquet"
    parquet_dir.mkdir(exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        if file_type == "csv":
            tables = [load_csv(con, upload_path, to_identifier(base_name, fallback="data"), out_dir)]
        else:
            tables = load_excel(con, upload_path, sheets)
        profiles: list[TableProfile] = []
        for table in tables:
            coercions = coerce_text_columns(con, table.name)
            reorder_columns(con, table.name, table.columns)
            for coercion in coercions:
                if coercion.ambiguous:
                    table.warnings.append(
                        f"Dates in '{coercion.column}' are ambiguous between day/month order; "
                        f"interpreted as {coercion.date_format}"
                    )
            table.details["coercions"] = [asdict(c) for c in coercions]
            profile = profile_table(con, table.name)
            units = {c.column: c.unit for c in coercions if c.unit}
            for column in profile.columns:
                if column.name in units:
                    column.stats["unit"] = units[column.name]
            profiles.append(profile)
            con.execute(
                f"COPY {quote_ident(table.name)} TO {sql_string(str(parquet_dir / (table.name + '.parquet')))} "
                "(FORMAT parquet)"
            )
        con.execute("CHECKPOINT")
    finally:
        con.close()
    report: dict[str, object] = {
        "tables": [
            {
                "name": t.name,
                "display_name": t.display_name,
                "rows": t.row_count,
                "warnings": t.warnings,
                "details": t.details,
            }
            for t in tables
        ]
    }
    return tables, profiles, report


def ingest_upload(
    db: Session,
    *,
    user_id: str,
    stream: BinaryIO,
    filename: str,
    name: str | None = None,
    sheets: list[str] | None = None,
) -> Dataset:
    file_type = detect_file_type(filename)
    upload_path, size, sha = save_upload(stream, filename)
    display = (name or Path(filename).stem).strip()[:200] or "Dataset"

    source = DataSource(user_id=user_id, kind="file", name=display, status="pending")
    db.add(source)
    db.flush()
    dataset = Dataset(
        user_id=user_id,
        data_source_id=source.id,
        name=display,
        original_filename=filename[:400],
        file_type=file_type,
        size_bytes=size,
    )
    db.add(dataset)
    db.flush()
    settings = get_settings()
    out_dir = settings.datasets_dir / dataset.id / "v1"
    try:
        tables, profiles, report = build_dataset_files(upload_path, file_type, display, out_dir, sheets)
    except IngestionError:
        db.rollback()
        shutil.rmtree(settings.datasets_dir / dataset.id, ignore_errors=True)
        raise
    except Exception as exc:
        db.rollback()
        shutil.rmtree(settings.datasets_dir / dataset.id, ignore_errors=True)
        log.exception("ingestion_failed", filename=filename)
        raise IngestionError("The file could not be processed. Check that it is a valid CSV/XLSX file") from exc
    finally:
        shutil.rmtree(upload_path.parent, ignore_errors=True)

    version = DatasetVersion(
        dataset_id=dataset.id,
        version=1,
        storage_path=str(out_dir / "data.duckdb"),
        parquet_dir=str(out_dir / "parquet"),
        sha256=sha,
        ingestion_report=report,
    )
    db.add(version)
    db.flush()
    dataset.current_version_id = version.id
    persist_tables(db, source, tables, profiles, version.id)
    source.status = "ready"
    db.commit()
    db.refresh(dataset)
    log.info("dataset_ingested", dataset=dataset.id, tables=len(tables), bytes=size)
    return dataset


def persist_tables(
    db: Session,
    source: DataSource,
    tables: list[LoadedTable],
    profiles: list[TableProfile],
    version_id: str | None,
) -> list[TableMetadata]:
    created: list[TableMetadata] = []
    for loaded, profile in zip(tables, profiles, strict=True):
        semantic = interpret_table(profile)
        profile.table["warnings"] = loaded.warnings + profile.table["warnings"]
        table = TableMetadata(
            data_source_id=source.id,
            dataset_version_id=version_id,
            name=loaded.name,
            display_name=loaded.display_name,
            row_count=profile.row_count,
            column_count=len(profile.columns),
            profile=profile.table,
            semantic={k: v for k, v in semantic.items() if k != "columns"},
        )
        sem_by_col = {c["column"]: c for c in semantic["columns"]}
        original = dict(zip(loaded.columns, loaded.original_columns, strict=False))
        for ordinal, column in enumerate(profile.columns):
            sem = sem_by_col[column.name]
            table.columns.append(
                ColumnMetadata(
                    name=column.name,
                    original_name=original.get(column.name, column.name),
                    ordinal=ordinal,
                    physical_type=column.physical_type,
                    inferred_type=column.inferred_type,
                    role=column.role,
                    semantic_type=sem["semantic_type"],
                    semantic_confidence=sem["confidence"],
                    is_pii=sem["is_pii"],
                    stats={
                        **column.stats,
                        "flags": column.flags,
                        "concept": sem["concept"],
                        "semantic_alternatives": sem["alternatives"],
                    },
                )
            )
        db.add(table)
        created.append(table)
    db.flush()
    return created
