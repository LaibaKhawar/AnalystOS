from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import current_user, owned_analysis
from app.api.schemas import ReportOut
from app.core.errors import AnalystError, NotFoundError, ValidationFailed
from app.db.models import Report, ResultTable, User
from app.db.session import get_db
from app.services.reports.builder import build_report, render_pdf

router = APIRouter(prefix="/api", tags=["reports"])


class PDFUnavailable(AnalystError):
    status_code = 501
    code = "pdf_unavailable"


@router.post("/analyses/{analysis_id}/report", response_model=ReportOut, status_code=201)
def create_report(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Report:
    analysis = owned_analysis(db, user, analysis_id)
    if analysis.status != "completed":
        raise ValidationFailed("Reports can be generated for completed analyses only")
    report = build_report(db, analysis)
    db.commit()
    return report


@router.get("/analyses/{analysis_id}/report", response_model=ReportOut)
def report_for_analysis(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Report:
    owned_analysis(db, user, analysis_id)
    report = db.query(Report).filter(Report.analysis_id == analysis_id).order_by(Report.created_at.desc()).first()
    if report is None:
        raise NotFoundError("No report has been generated for this analysis")
    return report


@router.get("/reports", response_model=list[ReportOut])
def list_reports(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Report]:
    return db.query(Report).filter(Report.user_id == user.id).order_by(Report.created_at.desc()).limit(50).all()


def _owned(db: Session, user: User, report_id: str) -> Report:
    report = db.get(Report, report_id)
    if report is None or report.user_id != user.id:
        raise NotFoundError("Report not found")
    return report


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Report:
    return _owned(db, user, report_id)


@router.get("/reports/{report_id}/html", response_class=HTMLResponse)
def report_html(
    report_id: str, download: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> HTMLResponse:
    report = _owned(db, user, report_id)
    headers = {"Content-Disposition": f'attachment; filename="{report.id}.html"'} if download else {}
    headers["Content-Security-Policy"] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
    return HTMLResponse(report.html, headers=headers)


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    report = _owned(db, user, report_id)
    try:
        pdf = render_pdf(report.html)
    except RuntimeError as exc:
        raise PDFUnavailable(str(exc)) from exc
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{report.id}.pdf"'}
    )


@router.get("/reports/{report_id}/results.xlsx")
def report_results(report_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    report = _owned(db, user, report_id)
    tables = db.query(ResultTable).filter(ResultTable.analysis_id == report.analysis_id).all()
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for index, table in enumerate(tables):
            frame = pd.DataFrame(table.rows, columns=[c["name"] for c in table.columns])
            frame = frame.map(lambda v: "'" + v if isinstance(v, str) and v[:1] in "=+-@" else v)
            sheet = f"{index + 1}_{table.name}"[:31].replace("/", "-").replace(":", "-")
            frame.to_excel(writer, sheet_name=sheet, index=False)
        if not tables:
            pd.DataFrame().to_excel(writer, sheet_name="empty")
    return Response(
        buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{report.id}-results.xlsx"'},
    )
