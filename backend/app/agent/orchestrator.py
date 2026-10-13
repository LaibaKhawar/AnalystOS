"""The analysis loop: context -> plan -> execute (with bounded repair) -> observe/revise -> synthesize -> verify.

Only structured artifacts are stored and streamed (plan, step status, tool summaries, verified claims).
Model reasoning is never persisted or shown.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent import fastpath
from app.agent.context import EventEmitter, ToolContext, column_guide, render_metrics, render_schema
from app.agent.llm.base import LLMProvider
from app.agent.llm.pricing import estimate_cost
from app.agent.llm.structured import CallLog
from app.agent.persistence import (
    persist_claims,
    store_memory,
    tool_stats,
    update_conversation_state,
    verify_charts,
)
from app.agent.planner import Planner
from app.agent.schemas import Plan, PlanStep
from app.agent.scope import ScopeContext, check_plan_scope
from app.agent.scope import describe as scope_describe
from app.agent.synthesizer import draft_answer, rewrite_unsupported
from app.agent.tools.base import ToolError, ToolOutcome, ToolRunner
from app.agent.tools.registry import build_registry, tool_catalog
from app.agent.verifier import verify_answer, verify_sentence
from app.core.config import get_settings
from app.core.errors import AnalystError, LLMError
from app.core.logging import analysis_id_var, get_logger
from app.core.metrics import ANALYSIS_LATENCY, TOOL_RETRIES
from app.core.tracing import span
from app.db.base import utcnow
from app.db.models import Analysis, AnalysisStep, Chart, Conversation, DataSource, Message, MetricDefinition
from app.services.datasources.factory import catalog_for, engine_for
from app.services.sandbox.factory import get_sandbox
from app.services.viz.charts import recommend_type

log = get_logger(__name__)


class AnalysisCancelled(Exception):
    pass


@dataclass
class StepState:
    plan: PlanStep
    record: AnalysisStep
    outcome: ToolOutcome | None = None
    reviewed: bool = False  # already shown to the reviser


def render_conversation(conversation: Conversation, current_analysis_id: str) -> str:
    state = conversation.state or {}
    lines = []
    for turn in state.get("history", [])[-4:]:
        if turn.get("analysis_id") == current_analysis_id:
            continue
        lines.append(f"Earlier question: {turn.get('question')}\nEarlier answer headline: {turn.get('headline')}")
    if state.get("filters"):
        lines.append(f"Active filters from the conversation: {json.dumps(state['filters'], default=str)}")
    for key in ("metric", "dimension", "period"):
        if state.get(key):
            lines.append(f"Current {key}: {state[key]}")
    return "\n".join(lines)


class AnalysisRunner:
    def __init__(self, db: Session, llm: LLMProvider, *, sandbox: Any = None, emit_events: bool = True) -> None:
        self.db = db
        self.llm = llm
        self.settings = get_settings()
        self.sandbox = sandbox or get_sandbox()
        self.emit_events = emit_events
        self.tools = build_registry(python=self.settings.sandbox_enabled)
        self.catalog_text = tool_catalog(self.tools)

    # ------------------------------------------------------------------------------------------------
    def run(self, analysis_id: str) -> Analysis:
        with span("analysis", **{"analysis.id": analysis_id}) as current:
            result = self._run(analysis_id)
            current.set_attribute("analysis.status", result.status)
            current.set_attribute("llm.calls", result.llm_calls)
            current.set_attribute("llm.input_tokens", result.input_tokens)
            current.set_attribute("llm.output_tokens", result.output_tokens)
            return result

    def _run(self, analysis_id: str) -> Analysis:
        analysis = self.db.get(Analysis, analysis_id)
        if analysis is None:
            raise AnalystError(f"Analysis {analysis_id} not found")
        analysis_id_var.set(analysis.id)
        events = EventEmitter(analysis.id, enabled=self.emit_events)
        started = time.perf_counter()
        call_log = CallLog()
        analysis.status, analysis.started_at = "running", utcnow()
        self.db.commit()
        engine = None
        try:
            source = self.db.get(DataSource, analysis.data_source_id)
            conversation = self.db.get(Conversation, analysis.conversation_id)
            assert source is not None
            assert conversation is not None
            events.emit("status", "Inspecting dataset", phase="context")
            engine = engine_for(self.db, source)
            ctx = ToolContext(
                db=self.db,
                analysis_id=analysis.id,
                user_id=analysis.user_id,
                source=source,
                engine=engine,
                catalog=catalog_for(source),
                sandbox=self.sandbox,
                events=events,
            )
            ctx.metrics = self.db.query(MetricDefinition).filter(MetricDefinition.data_source_id == source.id).all()
            schema_text = render_schema(source) + render_metrics(ctx.metrics)
            conversation_text = render_conversation(conversation, analysis.id)
            planner = Planner(self.llm, self.tools, call_log, self.settings.agent_max_steps)

            fast = fastpath.match(analysis.question, source) if not conversation_text else None
            if fast is not None:
                events.emit("status", "Answering from the precomputed dataset profile", phase="planning")
                plan = fast.plan()
            else:
                events.emit("status", "Planning the analysis", phase="planning")
                plan = planner.plan(
                    analysis.question,
                    schema_text,
                    self.catalog_text,
                    conversation_text,
                    engine.dialect,
                    column_guide(source),
                )
            analysis.plan = {**plan.model_dump(), "fast_path": fast is not None}
            self.db.commit()
            events.emit("plan", f"Plan with {len(plan.steps)} steps", plan=analysis.plan)

            if plan.needs_clarification and plan.clarification_question:
                return self._clarify(analysis, conversation, plan, call_log, started, events)

            if fast is None:
                plan, scope_report = self._check_scope(
                    analysis, conversation, plan, planner, schema_text, engine.dialect, events, ctx
                )
            else:
                scope_report = {"issues_found": 0, "fixed": 0, "remaining": []}
            analysis.plan = {**plan.model_dump(), "fast_path": fast is not None}
            self.db.commit()

            states = [self._add_step(analysis, step, i) for i, step in enumerate(plan.steps)]
            runner = ToolRunner(ctx, self.tools)
            self._execute_steps(states, ctx, runner, planner, schema_text, analysis)

            # Observe -> revise (bounded).
            replans = 0
            while (
                fast is None
                and replans < self.settings.agent_max_replans
                and len(states) < self.settings.agent_max_steps
                and self._needs_revision(states)
            ):
                budget = min(3, self.settings.agent_max_steps - len(states))
                events.emit("status", "Reviewing intermediate results", phase="revising")
                revision = planner.revise(
                    analysis.question,
                    plan.goal,
                    schema_text,
                    self.catalog_text,
                    self._observations(states),
                    [s.plan for s in states],
                    budget,
                )
                if not revision.additional_steps:
                    break
                replans += 1
                analysis.replans = replans
                events.emit(
                    "replan",
                    f"Plan revised: {len(revision.additional_steps)} step(s) added",
                    reason=revision.reason[:300],
                    steps=[s.model_dump() for s in revision.additional_steps],
                )
                new_states = [
                    self._add_step(analysis, step, len(states) + i, replan=True)
                    for i, step in enumerate(revision.additional_steps)
                ]
                states.extend(new_states)
                plan.steps.extend(revision.additional_steps)
                analysis.plan = plan.model_dump()
                self.db.commit()
                self._execute_steps(new_states, ctx, runner, planner, schema_text, analysis)

            if fast is None:
                self._ensure_chart(ctx, runner, states)

            charts = self.db.query(Chart).filter(Chart.analysis_id == analysis.id).all()
            numeric = len(ctx.findings)
            events.emit("status", f"Drafting answer from {numeric} computed findings", phase="synthesis")
            failures = [
                f"{s.plan.title}: {s.outcome.error.message[:200]}"
                for s in states
                if s.outcome and not s.outcome.ok and s.outcome.error
            ]
            fast_ok = fast is not None and all(s.outcome and s.outcome.ok for s in states)
            draft = (
                fastpath.draft_from_profile(fast, ctx.findings)
                if fast is not None and fast_ok
                else draft_answer(
                    self.llm,
                    call_log,
                    question=analysis.question,
                    goal=plan.goal,
                    assumptions=plan.assumptions,
                    findings=ctx.findings,
                    charts=charts,
                    failures=failures,
                    conversation=conversation_text,
                )
            )
            draft_dict = draft.model_dump()
            sentence_count = sum(len(draft_dict[k]) for k in ("summary", "facts", "interpretations", "recommendations"))
            events.emit("status", f"Verifying {sentence_count} claims against computed results", phase="verification")
            exempt = self._exempt_phrases(analysis.question, ctx)
            report = verify_answer(
                draft_dict,
                ctx.findings,
                exempt_phrases=exempt,
                known_entities=self._known_entities(ctx),
                data_years=self._data_years(ctx),
            )
            self._repair_unsupported(report, ctx, call_log, exempt, events)
            persist_claims(self.db, analysis, report, ctx.findings)
            charts_ok, charts_total = verify_charts(self.db, analysis.id)
            verification = {**report.stats(), "charts_verified": charts_ok, "charts_total": charts_total}
            events.emit(
                "verification",
                f"{verification['verified']} claims verified, {verification['removed']} "
                f"unsupported removed, {charts_ok}/{charts_total} charts verified",
                **verification,
            )

            kept = [c for c in report.claims if c.status != "removed"]
            analysis.answer = {
                "headline": report.headline,
                "summary": [c.text for c in kept if c.section == "summary"],
                "caveats": report.caveats,
                "assumptions": plan.assumptions,
                "follow_up_questions": report.follow_ups,
                "chart_ids": [c.id for c in charts],
                "verification": verification,
                "scope": scope_report,
                "failed_steps": failures,
            }
            analysis.summary = report.headline
            update_conversation_state(conversation, analysis, plan.context_update.model_dump(), report.headline)
            store_memory(self.db, analysis, report, self.llm.embed)
            self.db.add(
                Message(
                    conversation_id=conversation.id, role="assistant", content=report.headline, analysis_id=analysis.id
                )
            )
            if ctx.report_requested:
                from app.services.reports.builder import build_report

                events.emit("status", "Generating report", phase="report")
                build_report(self.db, analysis, title=ctx.report_title)
            self._finish(analysis, "completed", call_log, started)
            analysis.answer = {**analysis.answer, "tool_stats": tool_stats(self.db, analysis.id)}
            self.db.commit()
            events.emit("completed", "Analysis complete", analysis_id=analysis.id)
            return analysis
        except AnalysisCancelled:
            self.db.rollback()
            analysis = self.db.get(Analysis, analysis_id) or analysis
            analysis.error = "Cancelled by user"
            self._finish(analysis, "cancelled", call_log, started)
            self.db.commit()
            events.emit("cancelled", "Analysis cancelled")
            return analysis
        except Exception as exc:
            self.db.rollback()
            analysis = self.db.get(Analysis, analysis_id) or analysis
            message = (
                exc.message
                if isinstance(exc, AnalystError)
                else f"The analysis failed unexpectedly ({exc.__class__.__name__})"
            )
            if isinstance(exc, LLMError):
                message = f"The language model could not complete the analysis: {exc.message}"
            if not isinstance(exc, AnalystError):
                log.exception("analysis_failed")
            analysis.error = message
            self._finish(analysis, "failed", call_log, started)
            self.db.commit()
            events.emit("failed", message)
            return analysis
        finally:
            if engine is not None:
                engine.close()

    # ------------------------------------------------------------------------------------------------
    def _add_step(self, analysis: Analysis, step: PlanStep, ordinal: int, replan: bool = False) -> StepState:
        record = AnalysisStep(
            analysis_id=analysis.id,
            ordinal=ordinal,
            title=step.title[:300],
            tool=step.tool,
            purpose=step.expected_output,
            depends_on=step.depends_on,
            added_by_replan=replan,
        )
        self.db.add(record)
        self.db.flush()
        return StepState(plan=step, record=record)

    def _check_cancel(self, analysis: Analysis) -> None:
        self.db.refresh(analysis, attribute_names=["cancel_requested"])
        if analysis.cancel_requested:
            raise AnalysisCancelled()

    def _execute_steps(
        self,
        states: list[StepState],
        ctx: ToolContext,
        runner: ToolRunner,
        planner: Planner,
        schema_text: str,
        analysis: Analysis,
    ) -> None:
        failed_ids = {s.plan.id for s in states if s.outcome and not s.outcome.ok}
        for state in states:
            self._check_cancel(analysis)
            step, record = state.plan, state.record
            blocked_by = [d for d in step.depends_on if d in failed_ids]
            unresolved = _missing_refs(step.args, ctx.step_results)
            if blocked_by or unresolved:
                record.status = "skipped"
                record.result_summary = f"Skipped: depends on failed step(s) {', '.join(blocked_by or unresolved)}"
                failed_ids.add(step.id)
                self.db.commit()
                ctx.events.emit("step_skipped", f"Skipped: {step.title}", step_id=step.id, step_record_id=record.id)
                continue
            record.status, record.started_at = "running", utcnow()
            self.db.commit()
            ctx.events.emit("step_started", step.title, step_id=step.id, step_record_id=record.id, tool=step.tool)
            outcome = self._run_with_retries(step, record, ctx, runner, planner, schema_text)
            state.outcome = outcome
            record.completed_at = utcnow()
            if outcome.ok and outcome.result:
                record.status = "done"
                record.result_summary = outcome.result.summary[:4000]
                if outcome.result.result_table_id:
                    ctx.step_results[step.id] = outcome.result.result_table_id
                ctx.events.emit(
                    "step_completed",
                    step.title,
                    step_id=step.id,
                    step_record_id=record.id,
                    tool=record.tool,
                    execution_id=outcome.execution_id,
                    findings=outcome.finding_labels[:20],
                    chart_ids=outcome.result.chart_ids,
                    result_id=outcome.result.result_table_id,
                )
            else:
                record.status = "failed"
                record.result_summary = (outcome.error.message if outcome.error else "failed")[:2000]
                failed_ids.add(step.id)
                ctx.events.emit(
                    "step_failed",
                    f"{step.title}: {record.result_summary[:200]}",
                    step_id=step.id,
                    step_record_id=record.id,
                    tool=record.tool,
                    error_kind=outcome.error.kind if outcome.error else None,
                )
            self.db.commit()

    def _run_with_retries(
        self,
        step: PlanStep,
        record: AnalysisStep,
        ctx: ToolContext,
        runner: ToolRunner,
        planner: Planner,
        schema_text: str,
    ) -> ToolOutcome:
        tool, args = step.tool, _resolve_refs(step.args, ctx.step_results)
        history: list[str] = []
        previous_id: str | None = None
        reason: str | None = None
        seen_calls: set[str] = set()
        # Charts are presentation, not analysis: one repair attempt is enough.
        retries = 1 if step.tool == "create_chart" else self.settings.agent_max_retries_per_step
        max_attempts = 1 + retries
        outcome: ToolOutcome | None = None
        for attempt in range(1, max_attempts + 1):
            signature = tool + json.dumps(args, sort_keys=True, default=str)
            if signature in seen_calls:  # the repair produced an identical call: stop instead of looping
                break
            seen_calls.add(signature)
            outcome = runner.execute(
                tool, args, step_id=record.id, attempt=attempt, retry_of=previous_id, retry_reason=reason
            )
            if outcome.ok:
                record.tool = tool
                return outcome
            error = outcome.error or ToolError("internal_error", "unknown failure")
            history.append(f"{tool}: {error.kind}: {error.message[:200]}")
            if not error.recoverable or attempt == max_attempts:
                break
            TOOL_RETRIES.labels(tool=tool).inc()
            ctx.events.emit(
                "retry",
                f"Retrying {step.title} after {error.kind.replace('_', ' ')}",
                step_id=step.id,
                step_record_id=record.id,
                attempt=attempt + 1,
                error_kind=error.kind,
            )
            corrected = _auto_correct(args, error)
            if corrected is not None and tool + json.dumps(corrected, sort_keys=True, default=str) not in seen_calls:
                previous_id = outcome.execution_id
                reason = f"{error.kind}: {error.message[:200]} (auto-corrected to closest schema match)"
                args = corrected
                continue
            try:
                repair = planner.repair(step, tool, args, error, schema_text, self.catalog_text, history)
            except LLMError:
                break
            previous_id, reason = outcome.execution_id, f"{error.kind}: {error.message[:300]}"
            tool, args = repair.tool, _resolve_refs(repair.args, ctx.step_results)
        assert outcome is not None
        return outcome

    def _repair_unsupported(
        self, report: Any, ctx: ToolContext, call_log: CallLog, exempt: list[str], events: EventEmitter
    ) -> None:
        """Give the model one chance to restate rejected sentences from the findings; re-verify the result."""
        numeric = report.numeric_claims
        report.draft_numeric = len(numeric)
        rejected = [c for c in report.claims if c.status == "removed"]
        report.draft_removed = len(rejected)
        if not rejected:
            return
        events.emit("status", f"Re-checking {len(rejected)} unsupported statement(s)", phase="verification")
        try:
            rewrite = rewrite_unsupported(
                self.llm, call_log, sentences=[(c.text, c.unsupported) for c in rejected[:10]], findings=ctx.findings
            )
        except LLMError:
            return
        by_label = {f.label.upper(): f for f in ctx.findings}
        for item in rewrite.items:
            if not (0 <= item.index < len(rejected)) or not item.text.strip():
                continue
            original = rejected[item.index]
            check = verify_sentence(
                item.text,
                item.citations,
                by_label,
                section=original.section,
                kind=original.kind,
                exempt_phrases=exempt,
                known_entities=self._known_entities(ctx),
                data_years=self._data_years(ctx),
            )
            if check.status in {"verified", "qualified"}:
                check.notes.append(f"rewritten after verification rejected: {original.text[:200]}")
                check.original_text = check.original_text or original.text
                report.claims.insert(report.claims.index(original) + 1, check)
                report.repaired += 1

    def _check_scope(
        self,
        analysis: Analysis,
        conversation: Conversation,
        plan: Plan,
        planner: Planner,
        schema_text: str,
        dialect: str,
        events: EventEmitter,
        tool_ctx: ToolContext,
    ) -> tuple[Plan, dict[str, Any]]:
        """Remove restrictions the question did not ask for (one rescope attempt), report what remains."""
        state = conversation.state or {}
        history = " ".join(str(turn.get("question", "")) for turn in state.get("history", []))
        active = {str(f.get("column", "")).lower() for f in state.get("filters", []) if isinstance(f, dict)}
        ctx = ScopeContext(
            question=analysis.question,
            allowed_text=history,
            active_columns=active,
            data_years=self._data_years(tool_ctx),
        )
        issues = check_plan_scope(plan, ctx, dialect)
        report: dict[str, Any] = {"issues_found": len(issues), "fixed": 0, "remaining": []}
        if not issues:
            return plan, report
        events.emit(
            "scope_check",
            f"Plan scope differs from the question in {len(issues)} place(s); correcting it",
            issues=[i.as_dict() for i in issues],
        )
        try:
            corrected = planner.rescope(analysis.question, plan, scope_describe(issues), schema_text, self.catalog_text)
            remaining = check_plan_scope(corrected, ctx, dialect)
            if corrected.steps and len(remaining) < len(issues):
                corrected.assumptions = list(dict.fromkeys(plan.assumptions + corrected.assumptions))
                plan = corrected
                issues = remaining
        except LLMError:
            pass
        report["fixed"] = report["issues_found"] - len(issues)
        report["remaining"] = [i.as_dict() for i in issues]
        for issue in issues:
            plan.assumptions.append(f"Scope: {issue.detail}")
        return plan, report

    @staticmethod
    def _needs_revision(states: list[StepState]) -> bool:
        """Revise only when results give a reason: a failed/skipped step, or a notable result (large change,
        high-severity anomaly) that has not been followed by a driver/segment breakdown yet."""
        unreviewed_failure = any(s.record.status in {"failed", "skipped"} and not s.reviewed for s in states)
        for state in states:
            state.reviewed = True
        if unreviewed_failure:
            return True
        investigated = {s.outcome.tool for s in states if s.outcome and s.outcome.ok}
        notable = any(s.outcome and s.outcome.ok and s.outcome.result and s.outcome.result.notable for s in states)
        return notable and not ({"identify_drivers", "analyze_segments"} & investigated)

    def _observations(self, states: list[StepState]) -> str:
        lines = []
        for state in states:
            outcome = state.outcome
            if outcome is None:
                lines.append(f"{state.plan.id} ({state.plan.tool}): {state.record.status}")
            elif outcome.ok and outcome.result:
                flag = " [NOTABLE]" if outcome.result.notable else ""
                lines.append(f"{state.plan.id} ({outcome.tool}){flag}: {outcome.result.summary[:900]}")
            else:
                lines.append(
                    f"{state.plan.id} ({outcome.tool}) FAILED: {outcome.error.message[:300] if outcome.error else ''}"
                )
        return "\n".join(lines)[:12000]

    def _ensure_chart(self, ctx: ToolContext, runner: ToolRunner, states: list[StepState]) -> None:
        if self.db.query(Chart).filter(Chart.analysis_id == ctx.analysis_id).count():
            return
        from app.db.models import ResultTable

        for state in reversed(states):
            result_id = state.outcome.result.result_table_id if state.outcome and state.outcome.result else None
            if not result_id:
                continue
            table = self.db.get(ResultTable, result_id)
            if table is None or table.row_count < 2:
                continue
            choice = recommend_type(table.columns, table.rows)
            if not choice:
                continue
            chart_type, x, y = choice
            outcome = runner.execute(
                "create_chart",
                {"result_id": result_id, "chart_type": chart_type, "x": x, "y": y, "title": table.name[:120]},
            )
            if outcome.ok:
                ctx.events.emit(
                    "step_completed",
                    f"Created chart: {table.name[:80]}",
                    tool="create_chart",
                    chart_ids=outcome.result.chart_ids if outcome.result else [],
                )
                return

    @staticmethod
    def _known_entities(ctx: ToolContext) -> set[str]:
        """Category values of the data source (top values of dimension columns) for the verifier's entity check."""
        values: set[str] = set()
        for table in ctx.tables:
            for column in table.columns:
                if column.role == "dimension" and not column.is_pii:
                    values.update(str(v["value"]) for v in (column.stats or {}).get("top_values", []) if v.get("value"))
        return values

    @staticmethod
    def _data_years(ctx: ToolContext) -> set[str] | None:
        """Calendar years spanned by the source's date columns (None when there are none or their range is unknown)."""
        years: set[str] = set()
        for table in ctx.tables:
            for column in table.columns:
                stats = column.stats or {}
                if column.role != "time" or not stats.get("min") or not stats.get("max"):
                    continue
                low, high = str(stats["min"])[:4], str(stats["max"])[:4]
                if low.isdigit() and high.isdigit() and int(low) <= int(high):
                    years.update(str(y) for y in range(int(low), int(high) + 1))
        return years or None

    def _exempt_phrases(self, question: str, ctx: ToolContext) -> list[str]:
        phrases: list[str] = []
        for finding in ctx.findings:
            phrases.extend(
                str(e) for e in (finding.payload or {}).get("entities", []) if any(ch.isdigit() for ch in str(e))
            )
        for table in ctx.tables:
            phrases.extend(c.original_name for c in table.columns if any(ch.isdigit() for ch in c.original_name))
            phrases.extend(c.name for c in table.columns if any(ch.isdigit() for ch in c.name))
        # Numbers from the user's question are NOT exempt: echoing "fell 20%?" back as fact must be verified.
        return [p for p in phrases if p]

    def _clarify(
        self,
        analysis: Analysis,
        conversation: Conversation,
        plan: Plan,
        call_log: CallLog,
        started: float,
        events: EventEmitter,
    ) -> Analysis:
        question = plan.clarification_question or "Could you clarify the question?"
        analysis.answer = {"headline": question, "clarification": True, "assumptions": plan.assumptions}
        analysis.summary = question
        self.db.add(
            Message(conversation_id=conversation.id, role="assistant", content=question, analysis_id=analysis.id)
        )
        self._finish(analysis, "needs_clarification", call_log, started)
        self.db.commit()
        events.emit("clarification", question)
        return analysis

    def _finish(self, analysis: Analysis, status: str, call_log: CallLog, started: float) -> None:
        analysis.status = status
        analysis.completed_at = utcnow()
        analysis.latency_ms = int((time.perf_counter() - started) * 1000)
        analysis.model = call_log.model or getattr(self.llm, "model", None)
        analysis.input_tokens = call_log.usage.input_tokens
        analysis.output_tokens = call_log.usage.output_tokens
        analysis.llm_calls = call_log.calls
        try:
            analysis.cost_usd = estimate_cost(
                analysis.model or "", call_log.usage.input_tokens, call_log.usage.output_tokens
            )
            if self.settings.llm_cost_per_gpu_second > 0:
                analysis.cost_usd = round(call_log.latency_ms / 1000 * self.settings.llm_cost_per_gpu_second, 6)
        except Exception:  # cost accounting must never break finishing an analysis
            log.warning("cost_estimation_failed", model=analysis.model)
            analysis.cost_usd = 0.0
        ANALYSIS_LATENCY.labels(status=status).observe(analysis.latency_ms / 1000)


def _auto_correct(args: dict[str, Any], error: ToolError) -> dict[str, Any] | None:
    """Deterministic fix for misspelled identifiers with a single clear schema match (no LLM call needed)."""
    if error.kind not in {"unknown_column", "unknown_table"}:
        return None
    suggestions = error.hints.get("suggestions") or []
    missing = error.hints.get("column") or error.hints.get("table") or error.hints.get("missing_key")
    if not missing or len(suggestions) != 1:
        return None
    replacement = suggestions[0]

    pattern = re.compile(rf"(?<![\w.\"']){re.escape(str(missing))}(?![\w\"'])", re.IGNORECASE)

    def swap(value: Any, key: str = "") -> Any:
        if isinstance(value, str) and value.lower() == str(missing).lower():
            return replacement
        if isinstance(value, str) and key in {"sql", "code"}:
            return pattern.sub(replacement, value)
        if isinstance(value, dict):
            return {k: swap(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [swap(v, key) for v in value]
        return value

    fixed = swap(args)
    return fixed if fixed != args else None


def _resolve_refs(value: Any, results: dict[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("$") and value[1:].lower() in results:
        return results[value[1:].lower()]
    if isinstance(value, dict):
        return {k: _resolve_refs(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(v, results) for v in value]
    return value


def _missing_refs(value: Any, results: dict[str, str]) -> list[str]:
    if isinstance(value, str) and value.startswith("$") and len(value) > 1 and " " not in value:
        return [] if value[1:].lower() in results else [value[1:]]
    if isinstance(value, dict):
        return [m for v in value.values() for m in _missing_refs(v, results)]
    if isinstance(value, list):
        return [m for v in value for m in _missing_refs(v, results)]
    return []
