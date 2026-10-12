"""Scheduled analyses and anomaly alerts.

A beat task calls `dispatch_due()` every minute: each due schedule gets a new analysis in its conversation (so
follow-up context carries over between runs), and its next run time advances. After the analysis finishes,
`create_alerts()` turns anomaly findings at or above the schedule's severity threshold (or a failed run) into an
Alert and, if configured, POSTs it to a webhook. Webhook URLs are validated against SSRF: HTTPS only (HTTP only
when explicitly allowed for local development) and the host must not resolve to a private, loopback, link-local
or reserved address.
"""

from __future__ import annotations

import ipaddress
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.logging import get_logger
from app.db.models import Alert, Analysis, Finding, Message, Schedule

log = get_logger(__name__)
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def validate_webhook(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    allow_http = get_settings().allow_insecure_webhooks
    if parsed.scheme not in ({"https", "http"} if allow_http else {"https"}) or not parsed.hostname:
        raise ValidationFailed("Webhook URLs must use https://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValidationFailed("The webhook host does not resolve") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not allow_http and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValidationFailed(
                "Webhook hosts must be public (private, loopback and metadata addresses are blocked)"
            )
    return url.strip()


def dispatch_due(db: Session, now: datetime | None = None) -> list[str]:
    """Create analyses for due schedules; returns their ids (the caller enqueues them)."""
    now = now or datetime.now(UTC)
    due = (
        db.query(Schedule)
        .filter(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
        .order_by(Schedule.next_run_at)
        .with_for_update(skip_locked=True)
        .limit(50)
        .all()
    )
    created: list[str] = []
    for schedule in due:
        analysis = start_run(db, schedule, now)
        created.append(analysis.id)
    db.commit()
    return created


def start_run(db: Session, schedule: Schedule, now: datetime | None = None) -> Analysis:
    now = now or datetime.now(UTC)
    analysis = Analysis(
        conversation_id=schedule.conversation_id,
        user_id=schedule.user_id,
        data_source_id=schedule.data_source_id,
        question=schedule.question,
        status="queued",
    )
    db.add(analysis)
    db.flush()
    db.add(
        Message(
            conversation_id=schedule.conversation_id, role="user", content=schedule.question, analysis_id=analysis.id
        )
    )
    schedule.last_run_at = now
    schedule.last_analysis_id = analysis.id
    schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
    return analysis


def create_alerts(db: Session, schedule: Schedule, analysis: Analysis) -> Alert | None:
    threshold = SEVERITY_ORDER.get(schedule.alert_min_severity, 1)
    alert: Alert | None = None
    if analysis.status == "failed":
        alert = Alert(
            user_id=schedule.user_id,
            schedule_id=schedule.id,
            analysis_id=analysis.id,
            severity="high",
            title=f"Scheduled analysis failed: {schedule.name}",
            message=analysis.error or "Unknown error",
            payload={"status": analysis.status},
        )
    else:
        anomalies = [
            f
            for f in db.query(Finding).filter(Finding.analysis_id == analysis.id, Finding.kind == "anomaly").all()
            if SEVERITY_ORDER.get(str((f.payload or {}).get("severity")), -1) >= threshold
        ]
        if anomalies:
            worst = max(anomalies, key=lambda f: SEVERITY_ORDER.get(str(f.payload.get("severity")), 0))
            alert = Alert(
                user_id=schedule.user_id,
                schedule_id=schedule.id,
                analysis_id=analysis.id,
                severity=str(worst.payload.get("severity")),
                title=f"{len(anomalies)} anomal{'y' if len(anomalies) == 1 else 'ies'} detected: {schedule.name}",
                message="\n".join(f.statement for f in anomalies[:5]),
                payload={"finding_ids": [f.id for f in anomalies], "headline": (analysis.answer or {}).get("headline")},
            )
    if alert is None:
        return None
    db.add(alert)
    db.flush()
    alert.delivery_status = deliver(schedule.webhook_url, alert)
    db.commit()
    return alert


def deliver(url: str | None, alert: Alert) -> str:
    if not url:
        return "not_configured"
    body: dict[str, Any] = {
        "id": alert.id,
        "severity": alert.severity,
        "title": alert.title,
        "message": alert.message,
        "analysis_id": alert.analysis_id,
        "schedule_id": alert.schedule_id,
        "source": "AnalystOS",
    }
    try:
        validate_webhook(url)  # re-check at send time (DNS may have changed since the schedule was saved)
        response = httpx.post(url, json=body, timeout=5.0, follow_redirects=False)
        return "sent" if response.status_code < 400 else f"failed: HTTP {response.status_code}"
    except ValidationFailed as exc:
        return f"blocked: {exc.message}"[:32]
    except httpx.HTTPError as exc:
        log.warning("webhook_failed", error=exc.__class__.__name__)
        return f"failed: {exc.__class__.__name__}"[:32]
