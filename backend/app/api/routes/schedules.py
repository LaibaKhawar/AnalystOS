"""Scheduled analyses and alerts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, owned_source, require_role
from app.api.schemas import AlertOut, ScheduleIn, ScheduleOut
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailed
from app.db.models import Alert, Analysis, Conversation, Schedule, User
from app.db.session import get_db
from app.services.schedules import start_run, validate_webhook
from app.workers.dispatch import enqueue_scheduled

router = APIRouter(prefix="/api", tags=["schedules"])


def _owned(db: Session, user: User, schedule_id: str) -> Schedule:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None or schedule.user_id != user.id:
        raise NotFoundError("Schedule not found")
    return schedule


def _check_interval(minutes: int) -> None:
    minimum = get_settings().schedule_min_interval_minutes
    if minutes < minimum:
        raise ValidationFailed(f"Schedules can run at most every {minimum} minutes")


def _out(db: Session, schedule: Schedule) -> ScheduleOut:
    out = ScheduleOut.model_validate(schedule)
    if schedule.last_analysis_id:
        out.last_status = db.query(Analysis.status).filter(Analysis.id == schedule.last_analysis_id).scalar()
    return out


@router.get("/schedules", response_model=list[ScheduleOut])
def list_schedules(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ScheduleOut]:
    rows = db.query(Schedule).filter(Schedule.user_id == user.id).order_by(Schedule.created_at.desc()).all()
    return [_out(db, s) for s in rows]


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Schedule:
    require_role(user, "analyst", "admin")
    source = owned_source(db, user, body.data_source_id, need="ask")
    _check_interval(body.interval_minutes)
    conversation = Conversation(
        user_id=user.id, data_source_id=source.id, title=f"Scheduled: {body.name}"[:300], state={}
    )
    db.add(conversation)
    db.flush()
    schedule = Schedule(
        user_id=user.id,
        data_source_id=source.id,
        conversation_id=conversation.id,
        name=body.name,
        question=body.question,
        interval_minutes=body.interval_minutes,
        enabled=body.enabled,
        alert_min_severity=body.alert_min_severity,
        webhook_url=validate_webhook(body.webhook_url),
        next_run_at=datetime.now(UTC) + timedelta(minutes=body.interval_minutes),
    )
    db.add(schedule)
    db.commit()
    return schedule


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: str, body: ScheduleIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Schedule:
    require_role(user, "analyst", "admin")
    schedule = _owned(db, user, schedule_id)
    owned_source(db, user, schedule.data_source_id, need="ask")
    if body.data_source_id != schedule.data_source_id:
        raise ValidationFailed("A schedule's data source cannot be changed; create a new schedule instead")
    _check_interval(body.interval_minutes)
    if body.interval_minutes != schedule.interval_minutes:
        schedule.next_run_at = datetime.now(UTC) + timedelta(minutes=body.interval_minutes)
    schedule.name, schedule.question, schedule.interval_minutes = body.name, body.question, body.interval_minutes
    schedule.enabled, schedule.alert_min_severity = body.enabled, body.alert_min_severity
    schedule.webhook_url = validate_webhook(body.webhook_url)
    db.commit()
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    schedule = _owned(db, user, schedule_id)
    conversation = db.get(Conversation, schedule.conversation_id)
    db.delete(schedule)
    if conversation is not None:
        db.delete(conversation)  # the schedule's own conversation and its runs go with it
    db.commit()


@router.post("/schedules/{schedule_id}/run", response_model=ScheduleOut, status_code=202)
def run_now(schedule_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Schedule:
    require_role(user, "analyst", "admin")
    schedule = _owned(db, user, schedule_id)
    owned_source(db, user, schedule.data_source_id, need="ask")
    analysis = start_run(db, schedule)
    db.commit()
    enqueue_scheduled(analysis.id, schedule.id)
    return schedule


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    unread_only: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[Alert]:
    query = db.query(Alert).filter(Alert.user_id == user.id)
    if unread_only:
        query = query.filter(Alert.read_at.is_(None))
    return query.order_by(Alert.created_at.desc()).limit(100).all()


@router.get("/alerts/unread-count")
def unread_count(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, int]:
    count = db.query(Alert).filter(Alert.user_id == user.id, Alert.read_at.is_(None)).count()
    return {"unread": count}


@router.post("/alerts/{alert_id}/read", response_model=AlertOut)
def mark_read(alert_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise NotFoundError("Alert not found")
    alert.read_at = alert.read_at or datetime.now(UTC)
    db.commit()
    return alert
