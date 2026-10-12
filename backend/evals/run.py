"""Evaluation runner.

Runs every benchmark case through the real agent (same orchestrator, tools, sandbox and verifier as the app),
scores it against computed ground truth, stores EvaluationRun/EvaluationCase rows (shown in the UI's evaluation
dashboard) and writes evals/results/<run_id>.json plus evals/results/<run_id>.md.

Usage:
  python -m evals.run                      # full suite with the configured LLM
  python -m evals.run --cases sales_q2_revenue,saas_churned_count
  python -m evals.run --categories numeric,entity --notes "baseline"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

import yaml

from app.agent.llm.openai_compat import OpenAICompatibleProvider
from app.agent.orchestrator import AnalysisRunner
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.models import Analysis, Conversation, Dataset, DataSource, EvaluationCase, EvaluationRun, Message, User
from app.db.session import get_session_factory
from app.services.ingestion.service import ingest_upload
from evals.scoring import aggregate, process_metrics, score_case

ROOT = Path(__file__).resolve().parent
DATASETS = {
    "sales": "sales.csv",
    "saas": "saas_subscriptions.csv",
    "marketing": "marketing_performance.csv",
    "adversarial": "adversarial_accounts.csv",
    "sales_xlsx": "sales_2026.xlsx",
}
EVAL_EMAIL = "eval@analystos.local"


def resolve(value: Any, truth: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$gt."):
        return truth[value[4:]]
    if isinstance(value, dict):
        return {k: resolve(v, truth) for k, v in value.items()}
    return value


def ensure_sources(db: Any, user: User) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key, filename in DATASETS.items():
        path = ROOT / "data" / filename
        existing = db.query(Dataset).filter(Dataset.user_id == user.id, Dataset.original_filename == filename).first()
        digest_ok = False
        if existing:
            from app.db.models import DatasetVersion

            version = db.get(DatasetVersion, existing.current_version_id)
            import hashlib

            digest_ok = version is not None and version.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
            if not digest_ok:
                db.delete(db.get(DataSource, existing.data_source_id))
                db.commit()
        if existing and digest_ok:
            sources[key] = existing.data_source_id
            continue
        with path.open("rb") as handle:
            dataset = ingest_upload(db, user_id=user.id, stream=handle, filename=filename, name=key)
        sources[key] = dataset.data_source_id
    return sources


def run(args: argparse.Namespace) -> str:
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

    settings = get_settings()
    llm = OpenAICompatibleProvider(model=args.model or settings.llm_model)
    db = get_session_factory()()
    user = db.query(User).filter(User.email == EVAL_EMAIL).first()
    if user is None:
        user = User(email=EVAL_EMAIL, name="Evaluation", password_hash=hash_password(secrets.token_hex(16)))
        db.add(user)
        db.commit()
    sources = ensure_sources(db, user)
    evaluation = EvaluationRun(
        suite=spec.get("suite", "core"),
        model=llm.model,
        status="running",
        config={
            "cases": [c["id"] for c in cases],
            "llm_base_url": _host(settings.llm_base_url),
            "agent_max_steps": settings.agent_max_steps,
            "max_retries": settings.agent_max_retries_per_step,
            "temperature": settings.llm_temperature,
        },
        notes=args.notes,
    )
    db.add(evaluation)
    db.commit()
    print(f"evaluation run {evaluation.id}: {len(cases)} cases with {llm.model}", flush=True)

    conversations: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        expected = resolve(case.get("expected", {}), truth)
        source_id = sources[case["dataset"]]
        group = case.get("conversation")
        if group and group in conversations:
            conversation_id = conversations[group]
        else:
            conversation = Conversation(user_id=user.id, data_source_id=source_id, title=f"eval {case['id']}", state={})
            db.add(conversation)
            db.flush()
            conversation_id = conversation.id
            if group:
                conversations[group] = conversation_id
        analysis = Analysis(
            conversation_id=conversation_id, user_id=user.id, data_source_id=source_id, question=case["question"]
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
        latency = int((time.perf_counter() - started) * 1000)
        scored = score_case(db, case, analysis, expected)
        record = {
            "case_id": case["id"],
            "category": case["category"],
            "dataset": case["dataset"],
            "question": case["question"],
            "expected": expected,
            "passed": scored.passed,
            "scores": scored.scores,
            "answer": scored.answer,
            "latency_ms": analysis.latency_ms or latency,
            "cost_usd": analysis.cost_usd,
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "llm_calls": analysis.llm_calls,
            "error": error or analysis.error,
            "analysis_id": analysis.id,
            "process": process_metrics(db, analysis),
        }
        results.append(record)
        db.add(
            EvaluationCase(
                run_id=evaluation.id,
                case_id=case["id"],
                category=case["category"],
                dataset=case["dataset"],
                question=case["question"],
                expected=expected,
                answer=scored.answer,
                passed=scored.passed,
                scores={**scored.scores, "process": record["process"]},
                latency_ms=record["latency_ms"],
                input_tokens=analysis.input_tokens,
                output_tokens=analysis.output_tokens,
                cost_usd=analysis.cost_usd,
                error=record["error"],
                analysis_id=analysis.id,
            )
        )
        evaluation.metrics = aggregate(results)
        db.commit()
        mark = "PASS" if scored.passed else "FAIL"
        print(
            f"[{index}/{len(cases)}] {mark} {case['id']:32s} {record['latency_ms'] / 1000:6.1f}s "
            f"{json.dumps({k: v for k, v in scored.scores.items() if k != 'safety_details'}, default=str)[:160]}",
            flush=True,
        )

    evaluation.metrics = aggregate(results)
    evaluation.status, evaluation.completed_at = "completed", utcnow()
    db.commit()
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    payload = {
        "run_id": evaluation.id,
        "model": llm.model,
        "suite": evaluation.suite,
        "notes": args.notes,
        "created_at": evaluation.created_at.isoformat(),
        "metrics": evaluation.metrics,
        "cases": results,
    }
    (out_dir / f"{evaluation.id}.json").write_text(json.dumps(payload, indent=2, default=str))
    (out_dir / f"{evaluation.id}.md").write_text(markdown(payload))
    print(json.dumps(evaluation.metrics, indent=2, default=str))
    db.close()
    return evaluation.id


def _host(url: str) -> str:
    return re.sub(r"//[^@/]*@", "//", url)


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
        f"| Latency p50 / p95 | {m['latency_p50_ms'] / 1000 if m['latency_p50_ms'] else 0:.1f}s / "
        f"{m['latency_p95_ms'] / 1000 if m['latency_p95_ms'] else 0:.1f}s |",
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
    parser.add_argument("--notes", help="free-text notes stored with the run")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
