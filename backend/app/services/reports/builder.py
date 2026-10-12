"""Business report assembly: verified claims + charts + evidence appendix -> HTML (and PDF when available).

Only claims that passed verification (verified, qualified, or qualitative) are included; removed claims
never reach a report. Facts, interpretations and recommendations are rendered as separate sections.
"""

from __future__ import annotations

import base64
import csv
import io
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models import (  # noqa: E402
    Analysis,
    Chart,
    Claim,
    DataSource,
    Evidence,
    Finding,
    Report,
    ResultTable,
    SQLExecution,
    ToolExecution,
)

_TEMPLATES = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                         autoescape=select_autoescape(["html"]))
SECTION_TITLES = {
    "trend": "Trends", "anomaly": "Anomalies", "segment": "Segment analysis", "driver": "Important drivers",
    "finding": "Key findings",
}
ACCENT = "#0f766e"


def _chart_png(chart: Chart) -> str | None:
    data = chart.data or []
    spec = chart.spec or {}
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=110)
    try:
        palette = [ACCENT, "#64748b", "#b45309", "#1d4ed8", "#be123c", "#4d7c0f"]
        x = spec.get("x")
        ys = spec.get("y") or []
        if chart.chart_type in {"line", "area"}:
            labels = [str(d.get(x)) for d in data]
            for i, y in enumerate(ys):
                ax.plot(labels, [d.get(y) for d in data], color=palette[i % len(palette)], linewidth=1.8, label=y)
            ax.tick_params(axis="x", labelrotation=45, labelsize=7)
            if len(labels) > 14:
                ax.set_xticks(labels[:: max(1, len(labels) // 12)])
        elif chart.chart_type in {"bar", "stacked_bar", "histogram"}:
            labels = [str(d.get(x)) for d in data]
            bottom = [0.0] * len(data)
            for i, y in enumerate(ys):
                values = [float(d.get(y) or 0) for d in data]
                if chart.chart_type == "stacked_bar":
                    ax.bar(labels, values, bottom=bottom, color=palette[i % len(palette)], label=y)
                    bottom = [b + v for b, v in zip(bottom, values, strict=True)]
                else:
                    width = 0.8 / max(1, len(ys))
                    positions = [j + i * width for j in range(len(labels))]
                    ax.bar(positions, values, width=width, color=palette[i % len(palette)], label=y)
                    ax.set_xticks([j + 0.4 - width / 2 for j in range(len(labels))], labels)
            ax.set_ylim(bottom=0)
            ax.tick_params(axis="x", labelrotation=45, labelsize=7)
        elif chart.chart_type == "scatter":
            y = ys[0] if ys else None
            ax.scatter([d.get(x) for d in data], [d.get(y) for d in data], s=12, color=ACCENT)
            ax.set_xlabel(str(x))
            ax.set_ylabel(str(y))
        elif chart.chart_type == "box":
            stats = [{"label": d["group"], "whislo": d["min"], "q1": d["q1"], "med": d["median"], "q3": d["q3"],
                      "whishi": d["max"], "fliers": []} for d in data]
            ax.bxp(stats, showfliers=False)
        else:
            plt.close(fig)
            return None
        if len(ys) > 1:
            ax.legend(fontsize=7, frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_title(chart.title, fontsize=10, loc="left")
        buffer = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buffer, format="png")
        return base64.b64encode(buffer.getvalue()).decode()
    finally:
        plt.close(fig)


def report_content(db: Session, analysis: Analysis) -> dict[str, Any]:
    source = db.get(DataSource, analysis.data_source_id)
    claims = db.query(Claim).filter(Claim.analysis_id == analysis.id, Claim.status != "removed").order_by(
        Claim.ordinal).all()
    charts = db.query(Chart).filter(Chart.analysis_id == analysis.id).all()
    answer = analysis.answer or {}
    facts = [c for c in claims if c.kind == "fact" and c.section != "summary"]
    sections: dict[str, list[Claim]] = {}
    for claim in facts:
        sections.setdefault(SECTION_TITLES.get(claim.section, "Key findings"), []).append(claim)
    evidence_rows = []
    for claim in claims:
        for evidence in claim.evidence:
            evidence_rows.append(_evidence_row(db, claim, evidence))
    tables = source.tables if source else []
    return {
        "title": analysis.question[:140],
        "headline": answer.get("headline") or analysis.summary,
        "question": analysis.question,
        "generated_at": (analysis.completed_at or analysis.created_at).strftime("%Y-%m-%d %H:%M UTC"),
        "dataset": {
            "name": source.name if source else "",
            "kind": source.kind if source else "",
            "tables": [{"name": t.name, "display": t.display_name, "rows": t.row_count, "columns": t.column_count,
                        "warnings": (t.profile or {}).get("warnings", [])} for t in tables],
        },
        "summary": [c for c in claims if c.section == "summary"],
        "sections": sections,
        "interpretations": [c for c in claims if c.kind == "interpretation"],
        "recommendations": [c for c in claims if c.kind == "recommendation"],
        "caveats": answer.get("caveats", []) + [f"Assumption: {a}" for a in answer.get("assumptions", [])]
                   + [f"Step not completed: {f}" for f in answer.get("failed_steps", [])],
        "follow_ups": answer.get("follow_up_questions", []),
        "charts": [{"title": c.title, "type": c.chart_type, "png": _chart_png(c), "interpretation": c.interpretation,
                    "verified": c.verified, "source": (c.spec or {}).get("source", {})} for c in charts],
        "evidence": evidence_rows,
        "verification": answer.get("verification", {}),
        "model": analysis.model,
        "cost_usd": analysis.cost_usd,
    }


def _evidence_row(db: Session, claim: Claim, evidence: Evidence) -> dict[str, Any]:
    finding = db.get(Finding, evidence.finding_id) if evidence.finding_id else None
    sql = None
    if evidence.result_table_id:
        table = db.get(ResultTable, evidence.result_table_id)
        sql = table.source.get("sql") if table else None
    if sql is None and evidence.tool_execution_id:
        record = db.query(SQLExecution).filter(SQLExecution.tool_execution_id == evidence.tool_execution_id).first()
        sql = record.sql_executed if record else None
    tool = db.get(ToolExecution, evidence.tool_execution_id) if evidence.tool_execution_id else None
    return {"claim": claim.text, "finding": finding.label if finding else "", "statement": evidence.description,
            "formula": evidence.formula, "source_type": evidence.source_type, "sql": sql,
            "tool": tool.tool if tool else None, "execution_id": evidence.tool_execution_id}


def render_html(content: dict[str, Any]) -> str:
    return _TEMPLATES.get_template("report.html").render(**content)


def build_report(db: Session, analysis: Analysis, title: str | None = None) -> Report:
    content = report_content(db, analysis)
    if title:
        content["title"] = title[:200]
    html = render_html(content)
    serialisable = {**content, "summary": [c.text for c in content["summary"]],
                    "sections": {k: [c.text for c in v] for k, v in content["sections"].items()},
                    "interpretations": [c.text for c in content["interpretations"]],
                    "recommendations": [c.text for c in content["recommendations"]],
                    "charts": [{k: v for k, v in c.items() if k != "png"} for c in content["charts"]]}
    existing = db.query(Report).filter(Report.analysis_id == analysis.id).first()
    if existing:
        existing.title, existing.content, existing.html = content["title"], serialisable, html
        db.flush()
        return existing
    report = Report(analysis_id=analysis.id, user_id=analysis.user_id, title=content["title"], content=serialisable,
                    html=html)
    db.add(report)
    db.flush()
    return report


def render_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - depends on system libraries
        raise RuntimeError("PDF export needs WeasyPrint and its system libraries (available in the Docker image)") from exc
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def result_csv(table: ResultTable) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([c["name"] for c in table.columns])
    for row in table.rows:
        writer.writerow(["" if v is None else _csv_safe(v) for v in row])
    return buffer.getvalue()


def _csv_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection in exported cells."""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value
