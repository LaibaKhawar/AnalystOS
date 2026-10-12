"""Evaluation runner.

Runs every benchmark case through the real agent (same orchestrator, tools, sandbox and verifier as the app),
scores it against computed ground truth, stores EvaluationRun/EvaluationCase rows (shown in the UI's evaluation
dashboard) and writes evals/results/<run_id>.json plus evals/results/<run_id>.md.

Usage:
  python -m evals.run                                  # full suite with the configured LLM
  python -m evals.run --repeat 3 --concurrency 2       # three runs, mean/min/max summary
  python -m evals.run --cases sales_q2_revenue,saas_churned_count
  python -m evals.run --categories numeric,entity --model gpt-4o-mini --base-url https://api.openai.com/v1 \
      --api-key-env OPENAI_API_KEY --notes "hosted model"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.agent.llm.openai_compat import OpenAICompatibleProvider
from app.agent.orchestrator import AnalysisRunner
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.models import (
    Analysis,
    Conversation,
    Dataset,
    DatasetVersion,
    DataSource,
    EvaluationCase,
    EvaluationRun,
    Message,
    MetricDefinition,
    User,
)
from app.db.session import get_session_factory
from app.services.datasources.factory import catalog_for, engine_for
from app.services.datasources.introspect import introspect_source
from app.services.ingestion.service import ingest_upload
from app.services.metrics import validate_metric
from evals.scoring import aggregate, process_metrics, score_case

ROOT = Path(__file__).resolve().parent
FILE_DATASETS = {
    "sales": "sales.csv",
    "saas": "saas_subscriptions.csv",
    "marketing": "marketing_performance.csv",
    "adversarial": "adversarial_accounts.csv",
    "sales_xlsx": "sales_2026.xlsx",
    "crm": "crm_workbook.xlsx",
}
EVAL_EMAIL = "eval@analystos.local"
SAVED_METRICS = [  # (dataset, table, name, label, expression)
    ("sales", "sales", "aov", "Average order value", "SUM(revenue) / COUNT(*)"),
]
SUMMARY_METRICS = [
    "pass_rate",
    "numerical_accuracy",
    "entity_accuracy",
    "sql_execution_accuracy",
    "analysis_correctness",
    "unsupported_claim_rate_draft",
    "unsupported_claim_rate_final",
    "tool_success_rate",
    "first_pass_success_rate",
    "retry_recovery_rate",
    "safety_pass_rate",
    "latency_p50_ms",
    "latency_p95_ms",
    "avg_cost_usd",
    "avg_llm_calls",
]


def resolve(value: Any, truth: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$gt."):
        return truth[value[4:]]
    if isinstance(value, dict):
        return {k: resolve(v, truth) for k, v in value.items()}
    return value


def _ensure_file_source(db: Any, user: User, key: str, filename: str) -> str:
    path = ROOT / "data" / filename
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = db.query(Dataset).filter(Dataset.user_id == user.id, Dataset.original_filename == filename).first()
    if existing:
        version = db.get(DatasetVersion, existing.current_version_id)
        if version is not None and version.sha256 == digest:
            return str(existing.data_source_id)
        db.delete(db.get(DataSource, existing.data_source_id))
        db.commit()
    with path.open("rb") as handle:
        dataset = ingest_upload(db, user_id=user.id, stream=handle, filename=filename, name=key)
    return str(dataset.data_source_id)


def _ensure_chinook(db: Any, user: User) -> str:
    """Chinook is evaluated through the database-connection path (SQLite, read-only), not as an upload."""
    root = get_settings().data_dir / "sqlite"
    root.mkdir(parents=True, exist_ok=True)
    target = root / "chinook.sqlite"
    if not target.exists() or target.stat().st_size != (ROOT / "data" / "chinook.sqlite").stat().st_size:
        shutil.copy(ROOT / "data" / "chinook.sqlite", target)
    existing = (
        db.query(DataSource)
        .filter(DataSource.user_id == user.id, DataSource.kind == "sqlite", DataSource.name == "chinook")
        .first()
    )
    if existing and existing.status == "ready":
        return str(existing.id)
    source = DataSource(user_id=user.id, kind="sqlite", name="chinook", database="chinook.sqlite", status="pending")
    db.add(source)
    db.flush()
    engine = engine_for(db, source)
    try:
        introspect_source(db, source, engine)  # type: ignore[arg-type]
    finally:
        engine.close()
    source.status = "ready"
    db.commit()
    return str(source.id)


def ensure_sources(db: Any, user: User) -> dict[str, str]:
    sources = {key: _ensure_file_source(db, user, key, filename) for key, filename in FILE_DATASETS.items()}
    sources["chinook"] = _ensure_chinook(db, user)
    for dataset, table, name, label, expression in SAVED_METRICS:
        source = db.get(DataSource, sources[dataset])
        exists = (
            db.query(MetricDefinition)
            .filter(MetricDefinition.data_source_id == source.id, MetricDefinition.name == name)
            .first()
        )
        if exists:
            continue
        meta = next(t for t in source.tables if t.name == table)
        valid = validate_metric(
            expression, table, {c.name: c.physical_type for c in meta.columns}, "duckdb", catalog_for(source)
        )
        db.add(
            MetricDefinition(
                data_source_id=source.id,
                table_name=table,
                name=name,
                label=label,
                expression=valid.expression,
                created_by=user.id,
            )
        )
    db.commit()
    return sources


def _provider(args: argparse.Namespace) -> OpenAICompatibleProvider:
    settings = get_settings()
    if args.base_url or args.api_key_env:
        settings = settings.model_copy(
            update={
                "llm_base_url": args.base_url or settings.llm_base_url,
                "llm_api_key": os.environ.get(args.api_key_env or "", settings.llm_api_key),
            }
        )
    return OpenAICompatibleProvider(settings, model=args.model or settings.llm_model)


def _run_case(
    case: dict[str, Any],
    truth: dict[str, Any],
    sources: dict[str, str],
    user_id: str,
    run_id: str,
    conversation_id: str | None,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], str]:
    db = get_session_factory()()
    llm = _provider(args)
    try:
        expected = resolve(case.get("expected", {}), truth)
        source_id = sources[case["dataset"]]
        if conversation_id is None:
            conversation = Conversation(user_id=user_id, data_source_id=source_id, title=f"eval {case['id']}", state={})
            db.add(conversation)
            db.flush()
            conversation_id = conversation.id
        analysis = Analysis(
            conversation_id=conversation_id, user_id=user_id, data_source_id=source_id, question=case["question"]
        )
        db.add(analysis)
        db.flush()
        db.add(Message(conversation_id=conversation_id, role="user", content=case["question"], analysis_id=analysis.id))
        db.commit()
        started = time.perf_counter()
        error = None
        try:
            AnalysisRunner(db, llm, emit_events=False).run(analysis.id)
        except Exception as exc:  # the runner records failures itself; this guards harness bugs
            error = f"{exc.__class__.__name__}: {exc}"
        db.expire_all()
        analysis = db.get(Analysis, analysis.id)
        scored = score_case(db, case, analysis, expected)
        if case["category"] == "fast_path":
            scored.scores["llm_calls"] = analysis.llm_calls
        record = {
            "case_id": case["id"],
            "category": case["category"],
            "dataset": case["dataset"],
            "question": case["question"],
            "expected": expected,
            "passed": scored.passed,
            "scores": scored.scores,
            "hard": bool(case.get("hard")),
            "answer": scored.answer,
            "latency_ms": analysis.latency_ms or int((time.perf_counter() - started) * 1000),
            "cost_usd": analysis.cost_usd,
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "llm_calls": analysis.llm_calls,
            "error": error or analysis.error,
            "analysis_id": analysis.id,
            "process": process_metrics(db, analysis),
        }
        db.add(
            EvaluationCase(
                run_id=run_id,
                case_id=case["id"],
                category=case["category"],
                dataset=case["dataset"],
                question=case["question"],
                expected=expected,
                answer=scored.answer,
                passed=scored.passed,
                scores={**scored.scores, "process": record["process"], "hard": record["hard"]},
                latency_ms=record["latency_ms"],
                input_tokens=analysis.input_tokens,
                output_tokens=analysis.output_tokens,
                cost_usd=analysis.cost_usd,
                error=record["error"],
                analysis_id=analysis.id,
            )
        )
        db.commit()
        return record, conversation_id
    finally:
        db.close()


def run_once(
    args: argparse.Namespace,
    cases: list[dict[str, Any]],
    truth: dict[str, Any],
    sources: dict[str, str],
    user_id: str,
    notes: str | None,
    batch: str,
) -> dict[str, Any]:
    llm = _provider(args)
    db = get_session_factory()()
    settings = get_settings()
    evaluation = EvaluationRun(
        suite="core",
        model=llm.model,
        status="running",
        notes=notes,
        config={
            "cases": [c["id"] for c in cases],
            "llm_base_url": re.sub(r"//[^@/]*@", "//", llm.settings.llm_base_url),
            "agent_max_steps": settings.agent_max_steps,
            "max_retries": settings.agent_max_retries_per_step,
            "temperature": settings.llm_temperature,
            "concurrency": args.concurrency,
            "batch": batch,
        },
    )
    db.add(evaluation)
    db.commit()
    run_id = evaluation.id
    print(f"evaluation run {run_id}: {len(cases)} cases with {llm.model} (concurrency {args.concurrency})", flush=True)

    # Cases in the same conversation group run in order inside one unit of work; units run in parallel.
    units: list[list[dict[str, Any]]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        if case.get("conversation"):
            groups.setdefault(case["conversation"], []).append(case)
        else:
            units.append([case])
    units.extend(groups.values())
    results: list[dict[str, Any]] = []
    lock = threading.Lock()
    done = 0

    def work(unit: list[dict[str, Any]]) -> None:
        nonlocal done
        conversation_id = None
        for case in unit:
            record, conversation_id = _run_case(case, truth, sources, user_id, run_id, conversation_id, args)
            with lock:
                results.append(record)
                done += 1
                mark = "PASS" if record["passed"] else "FAIL"
                shown = {k: v for k, v in record["scores"].items() if k not in {"safety_details", "status"}}
                print(
                    f"[{done}/{len(cases)}] {mark} {case['id']:34s} {record['latency_ms'] / 1000:6.1f}s "
                    f"{json.dumps(shown, default=str)[:150]}",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        list(pool.map(work, units))

    order = {c["id"]: i for i, c in enumerate(cases)}
    results.sort(key=lambda r: order[r["case_id"]])
    evaluation = db.get(EvaluationRun, run_id)
    evaluation.metrics = aggregate(results)
    evaluation.status, evaluation.completed_at = "completed", utcnow()
    db.commit()
    payload = {
        "run_id": run_id,
        "model": llm.model,
        "suite": "core",
        "notes": notes,
        "created_at": evaluation.created_at.isoformat(),
        "metrics": evaluation.metrics,
        "cases": results,
    }
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / f"{run_id}.json").write_text(json.dumps(payload, indent=2, default=str))
    (out / f"{run_id}.md").write_text(markdown(payload))
    db.close()
    return payload


def _fmt(key: str, value: float) -> str:
    if key.endswith("_ms"):
        return f"{value / 1000:.1f}s"
    if "cost" in key:
        return f"${value:.4f}"
    if key == "avg_llm_calls":
        return f"{value:.2f}"
    return f"{value * 100:.1f}%"


def summarize(runs: list[dict[str, Any]], batch: str) -> str:
    lines = [
        f"# Repeated evaluation {batch}",
        "",
        f"- Model: `{runs[0]['model']}`",
        f"- Runs: {len(runs)} ({', '.join(r['run_id'] for r in runs)})",
        f"- Cases per run: {runs[0]['metrics']['cases']}",
        "",
        "| Metric | Mean | Std | Min | Max |",
        "|---|---|---|---|---|",
    ]
    stats: dict[str, Any] = {}
    for key in SUMMARY_METRICS:
        values = [r["metrics"].get(key) for r in runs if r["metrics"].get(key) is not None]
        if not values:
            continue
        mean = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        stats[key] = {"mean": mean, "std": std, "min": min(values), "max": max(values), "values": values}
        lines.append(
            f"| {key} | {_fmt(key, mean)} | {_fmt(key, std)} | {_fmt(key, min(values))} | {_fmt(key, max(values))} |"
        )
    outcomes: dict[str, list[bool]] = {}
    for run_payload in runs:
        for case in run_payload["cases"]:
            outcomes.setdefault(case["case_id"], []).append(case["passed"])
    unstable = sorted(k for k, v in outcomes.items() if len(set(v)) > 1)
    always_fail = sorted(k for k, v in outcomes.items() if not any(v))
    lines += [
        "",
        f"Cases that passed in some runs and failed in others: {', '.join(unstable) or 'none'}",
        f"Cases that failed in every run: {', '.join(always_fail) or 'none'}",
    ]
    out = ROOT / "results"
    (out / f"summary_{batch}.json").write_text(
        json.dumps(
            {
                "runs": [r["run_id"] for r in runs],
                "model": runs[0]["model"],
                "stats": stats,
                "unstable": unstable,
                "always_fail": always_fail,
            },
            indent=2,
        )
    )
    text = "\n".join(lines) + "\n"
    (out / f"summary_{batch}.md").write_text(text)
    return text


def run(args: argparse.Namespace) -> list[str]:
    configure_logging("WARNING", json_output=False)
    os.environ["ANALYSTOS_EVAL_CANARY"] = "canary-" + secrets.token_hex(8)
    spec = yaml.safe_load((ROOT / "cases.yaml").read_text())
    truth = json.loads((ROOT / "data" / "ground_truth.json").read_text())
    cases = spec["cases"]
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.categories:
        wanted = set(args.categories.split(","))
        cases = [c for c in cases if c["category"] in wanted]
    db = get_session_factory()()
    user = db.query(User).filter(User.email == EVAL_EMAIL).first()
    if user is None:
        user = User(email=EVAL_EMAIL, name="Evaluation", password_hash=hash_password(secrets.token_hex(16)))
        db.add(user)
        db.commit()
    sources = ensure_sources(db, user)
    user_id = user.id
    db.close()
    batch = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    runs = []
    for index in range(args.repeat):
        notes = args.notes if args.repeat == 1 else f"{args.notes or 'repeat'} ({index + 1}/{args.repeat})"
        runs.append(run_once(args, cases, truth, sources, user_id, notes, batch))
        print(json.dumps({k: runs[-1]["metrics"].get(k) for k in SUMMARY_METRICS}, default=str), flush=True)
    if args.repeat > 1:
        print(summarize(runs, batch))
    return [r["run_id"] for r in runs]


def markdown(payload: dict[str, Any]) -> str:
    m = payload["metrics"]

    def pct(value: Any) -> str:
        return "n/a" if value is None else f"{value * 100:.1f}%"

    lines = [
        f"# Evaluation run {payload['run_id']}",
        "",
        f"- Model: `{payload['model']}`",
        f"- Suite: {payload['suite']} ({m['cases']} cases)",
        f"- Date: {payload['created_at']}",
        f"- Notes: {payload.get('notes') or '-'}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Overall pass rate | {pct(m['pass_rate'])} |",
        f"| Numerical accuracy (answer states the right number) | {pct(m['numerical_accuracy'])} |",
        f"| Entity accuracy | {pct(m['entity_accuracy'])} |",
        f"| SQL / computation accuracy (right value computed) | {pct(m['sql_execution_accuracy'])} |",
        f"| Analysis correctness (expected columns used) | {pct(m['analysis_correctness'])} |",
        f"| Chart correctness | {pct(m['chart_correctness'])} |",
        f"| Unsupported numeric claims in model drafts | {pct(m['unsupported_claim_rate_draft'])} |",
        f"| Unsupported numeric claims in final answers | {pct(m['unsupported_claim_rate_final'])} |",
        f"| Tool success rate | {pct(m['tool_success_rate'])} |",
        f"| First-pass step success | {pct(m['first_pass_success_rate'])} |",
        f"| Retry recovery ({m['recoverable_failures']} recoverable failures) | {pct(m['retry_recovery_rate'])} |",
        f"| Unsafe SQL executed | {m['unsafe_sql_executed']} (blocked attempts: {m['blocked_sql_attempts']}) |",
        f"| Safety pass rate | {pct(m['safety_pass_rate'])} |",
        f"| Latency p50 / p95 | {(m['latency_p50_ms'] or 0) / 1000:.1f}s / {(m['latency_p95_ms'] or 0) / 1000:.1f}s |",
        f"| Avg LLM calls / tokens in / out | {m['avg_llm_calls']} / {m['avg_input_tokens']} / "
        f"{m['avg_output_tokens']} |",
        f"| Avg cost per task | ${m['avg_cost_usd']:.4f} |",
        "",
        "## By category",
        "",
        "| Category | Passed | Cases | Rate |",
        "|---|---|---|---|",
    ]
    for name, bucket in sorted(m["by_category"].items()):
        lines.append(f"| {name} | {bucket['passed']} | {bucket['cases']} | {pct(bucket['pass_rate'])} |")
    lines += ["", "## Cases", "", "| Case | Category | Pass | Latency | Notes |", "|---|---|---|---|---|"]
    for case in payload["cases"]:
        notes = ", ".join(
            f"{k}={v}"
            for k, v in case["scores"].items()
            if k not in {"status", "safety_details"} and not isinstance(v, dict)
        )
        if case.get("hard"):
            notes = "hard; " + notes
        if case.get("error"):
            notes += f"; error: {str(case['error'])[:80]}"
        lines.append(
            f"| {case['case_id']} | {case['category']} | {'yes' if case['passed'] else 'no'} | "
            f"{case['latency_ms'] / 1000:.1f}s | {notes} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AnalystOS evaluation suite")
    parser.add_argument("--cases", help="comma-separated case ids")
    parser.add_argument("--categories", help="comma-separated categories")
    parser.add_argument("--model", help="override LLM_MODEL")
    parser.add_argument("--base-url", help="override LLM_BASE_URL (OpenAI-compatible endpoint)")
    parser.add_argument("--api-key-env", help="name of the environment variable holding the API key")
    parser.add_argument("--repeat", type=int, default=1, help="number of full runs (reports mean/min/max)")
    parser.add_argument("--concurrency", type=int, default=1, help="cases evaluated in parallel")
    parser.add_argument("--notes", help="free-text notes stored with the run")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
