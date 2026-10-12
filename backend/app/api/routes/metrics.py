"""Saved metric definitions per data source."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, owned_source
from app.api.schemas import MetricIn, MetricOut
from app.core.errors import NotFoundError, ValidationFailed
from app.db.models import DataSource, MetricDefinition, User
from app.db.session import get_db
from app.services.datasources.factory import catalog_for
from app.services.metrics import validate_metric, validate_name

router = APIRouter(prefix="/api/sources/{source_id}/metrics", tags=["metrics"])
_DIALECTS = {"file": "duckdb", "postgresql": "postgres", "mysql": "mysql", "sqlite": "sqlite"}


def _validated(source: DataSource, body: MetricIn) -> tuple[str, str]:
    table = next((t for t in source.tables if t.name.lower() == body.table.lower()), None)
    if table is None:
        raise ValidationFailed(f"Unknown table '{body.table}'")
    metric = validate_metric(
        body.expression,
        table.name,
        {c.name: c.physical_type for c in table.columns},
        _DIALECTS[source.kind],
        catalog_for(source),
    )
    return table.name, metric.expression


@router.get("", response_model=list[MetricOut])
def list_metrics(
    source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[MetricDefinition]:
    source = owned_source(db, user, source_id)
    return (
        db.query(MetricDefinition)
        .filter(MetricDefinition.data_source_id == source.id)
        .order_by(MetricDefinition.name)
        .all()
    )


@router.post("", response_model=MetricOut, status_code=201)
def create_metric(
    source_id: str, body: MetricIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> MetricDefinition:
    source = owned_source(db, user, source_id, need="manage")
    name = validate_name(body.name)
    if (
        db.query(MetricDefinition)
        .filter(MetricDefinition.data_source_id == source.id, MetricDefinition.name == name)
        .first()
    ):
        raise ValidationFailed(f"A metric named '{name}' already exists")
    table, expression = _validated(source, body)
    metric = MetricDefinition(
        data_source_id=source.id,
        table_name=table,
        name=name,
        label=body.label,
        description=body.description,
        expression=expression,
        format=body.format,
        filters=[f.model_dump() for f in body.filters],
        created_by=user.id,
    )
    db.add(metric)
    db.commit()
    return metric


@router.put("/{metric_id}", response_model=MetricOut)
def update_metric(
    source_id: str, metric_id: str, body: MetricIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> MetricDefinition:
    source = owned_source(db, user, source_id, need="manage")
    metric = db.get(MetricDefinition, metric_id)
    if metric is None or metric.data_source_id != source.id:
        raise NotFoundError("Metric not found")
    metric.table_name, metric.expression = _validated(source, body)
    metric.name, metric.label, metric.description = validate_name(body.name), body.label, body.description
    metric.format, metric.filters = body.format, [f.model_dump() for f in body.filters]
    db.commit()
    return metric


@router.delete("/{metric_id}", status_code=204)
def delete_metric(
    source_id: str, metric_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    source = owned_source(db, user, source_id, need="manage")
    metric = db.get(MetricDefinition, metric_id)
    if metric is None or metric.data_source_id != source.id:
        raise NotFoundError("Metric not found")
    db.delete(metric)
    db.commit()
