"""Manual smoke run: ingest a CSV and run one analysis through the real agent loop.

Usage: python scripts/smoke_analysis.py <csv/xlsx> "<question>"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from app.agent.llm.openai_compat import get_provider
from app.agent.orchestrator import AnalysisRunner
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.models import Analysis, AnalysisStep, Claim, Conversation, DataSource, Dataset, ToolExecution, User
from app.db.session import get_session_factory
from app.services.ingestion.service import ingest_upload


def main() -> None:
    configure_logging("WARNING", json_output=False)
    path, question = Path(sys.argv[1]), sys.argv[2]
    db = get_session_factory()()
    user = db.query(User).filter(User.email == "smoke@analystos.local").first()
    if user is None:
        user = User(email="smoke@analystos.local", name="Smoke", password_hash=hash_password("smoke-password"))
        db.add(user)
        db.commit()
    dataset = db.query(Dataset).filter(Dataset.user_id == user.id, Dataset.original_filename == path.name).first()
    if dataset is None:
        with path.open("rb") as handle:
            dataset = ingest_upload(db, user_id=user.id, stream=handle, filename=path.name)
    source = db.get(DataSource, dataset.data_source_id)
    conversation = Conversation(user_id=user.id, data_source_id=source.id, title=question[:100], state={})
    db.add(conversation)
    db.flush()
    analysis = Analysis(conversation_id=conversation.id, user_id=user.id, data_source_id=source.id, question=question)
    db.add(analysis)
    db.commit()
    started = time.time()
    AnalysisRunner(db, get_provider(), emit_events=True).run(analysis.id)
    db.expire_all()
    analysis = db.get(Analysis, analysis.id)
    print(f"\nstatus={analysis.status} latency={time.time() - started:.1f}s calls={analysis.llm_calls} "
          f"tokens={analysis.input_tokens}+{analysis.output_tokens} replans={analysis.replans} error={analysis.error}")
    print("PLAN:", json.dumps([{"id": s["id"], "tool": s["tool"], "args": s["args"]} for s in
                               analysis.plan.get("steps", [])], default=str)[:3000])
    for step in db.query(AnalysisStep).filter(AnalysisStep.analysis_id == analysis.id).order_by(AnalysisStep.ordinal):
        print(f"  [{step.status}] {step.tool}: {step.title} :: {(step.result_summary or '')[:160]!r}")
    for ex in db.query(ToolExecution).filter(ToolExecution.analysis_id == analysis.id).order_by(ToolExecution.created_at):
        if ex.status != "success":
            print(f"  FAIL {ex.tool} attempt={ex.attempt} {ex.error_kind}: {(ex.error or '')[:200]}")
    print("ANSWER:", json.dumps(analysis.answer, indent=1, default=str)[:2500])
    for claim in db.query(Claim).filter(Claim.analysis_id == analysis.id).order_by(Claim.ordinal):
        print(f"  {claim.status:10s} {claim.kind:14s} {claim.text[:150]} {claim.verification.get('unsupported')}")
    db.close()


if __name__ == "__main__":
    main()
