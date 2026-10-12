"""LLM-backed planning, argument repair, and plan revision."""

from __future__ import annotations

import json
from typing import Any

from app.agent.llm.base import LLMProvider
from app.agent.llm.structured import CallLog, generate_structured
from app.agent.prompts import PLANNER_SYSTEM, REPAIR_SYSTEM, RESCOPE_SYSTEM, REVISER_SYSTEM
from app.agent.schemas import Plan, PlanStep, Repair, Revision
from app.agent.tools.base import Tool, ToolError
from app.core.tracing import span


class Planner:
    def __init__(self, llm: LLMProvider, tools: dict[str, Tool], log: CallLog, max_steps: int) -> None:
        self.llm = llm
        self.tools = tools
        self.log = log
        self.max_steps = max_steps

    def plan(
        self, question: str, schema_text: str, catalog: str, conversation: str, dialect: str, column_guide: str = ""
    ) -> Plan:
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM + "\n\nTOOLS:\n" + catalog},
            {
                "role": "user",
                "content": (
                    f"SQL dialect for execute_sql: {dialect}\n\n<data>\n{schema_text}\n</data>\n\n"
                    f"Conversation context:\n<data>\n{conversation or 'none (first question)'}\n</data>\n\n"
                    f"{column_guide}\n\nQUESTION: {question}\n\nReturn the plan JSON."
                ),
            },
        ]
        with span("plan"):
            plan = generate_structured(self.llm, messages, Plan, purpose="plan", log=self.log, max_tokens=3000)
            return self.sanitize(plan)

    def sanitize(self, plan: Plan) -> Plan:
        seen: set[str] = set()
        steps: list[PlanStep] = []
        for index, step in enumerate(plan.steps):
            if step.tool not in self.tools:
                continue
            step_id = step.id if step.id and step.id not in seen else f"s{index + 1}"
            while step_id in seen:
                step_id += "x"
            step.id = step_id
            seen.add(step_id)
            step.depends_on = [d for d in step.depends_on if d in seen and d != step_id]
            steps.append(step)
        plan.steps = steps[: self.max_steps]
        if not plan.steps and not plan.needs_clarification:
            plan.steps = [PlanStep(id="s1", title="Inspect the schema", tool="inspect_schema")]
        return plan

    def rescope(self, question: str, plan: Plan, issues_text: str, schema_text: str, catalog: str) -> Plan:
        messages = [
            {"role": "system", "content": RESCOPE_SYSTEM + "\n\nTOOLS:\n" + catalog},
            {
                "role": "user",
                "content": (
                    f"<data>\n{schema_text}\n</data>\n\nQUESTION: {question}\n\n"
                    f"CURRENT PLAN:\n{json.dumps(plan.model_dump(), default=str)[:6000]}\n\n"
                    f"SCOPE ISSUES:\n{issues_text}\n\nReturn the corrected plan JSON."
                ),
            },
        ]
        return self.sanitize(generate_structured(self.llm, messages, Plan, purpose="rescope", log=self.log))

    def repair(
        self,
        step: PlanStep,
        tool: str,
        args: dict[str, Any],
        error: ToolError,
        schema_text: str,
        catalog: str,
        history: list[str],
    ) -> Repair:
        hints = json.dumps(error.hints, default=str)[:3000]
        messages = [
            {"role": "system", "content": REPAIR_SYSTEM + "\n\nTOOLS:\n" + catalog},
            {
                "role": "user",
                "content": (
                    f"<data>\n{schema_text}\n</data>\n\nStep: {step.title}\nTool: {tool}\n"
                    f"Failed args: {json.dumps(args, default=str)[:2000]}\n"
                    f"Error ({error.kind}): {error.message[:800]}\nHints: <data>{hints}</data>\n"
                    f"Earlier failed attempts: {history[-3:]}\nReturn the corrected call JSON."
                ),
            },
        ]
        repair = generate_structured(self.llm, messages, Repair, purpose="repair", log=self.log)
        if repair.tool not in self.tools:
            repair.tool = tool
        return repair

    def revise(
        self,
        question: str,
        goal: str,
        schema_text: str,
        catalog: str,
        observations: str,
        existing: list[PlanStep],
        budget: int,
    ) -> Revision:
        steps_text = "\n".join(f"- {s.id}: {s.tool} {json.dumps(s.args, default=str)[:200]}" for s in existing)
        messages = [
            {"role": "system", "content": REVISER_SYSTEM + "\n\nTOOLS:\n" + catalog},
            {
                "role": "user",
                "content": (
                    f"QUESTION: {question}\nGOAL: {goal}\n\n<data>\n{schema_text}\n</data>\n\n"
                    f"Executed steps:\n{steps_text}\n\nObservations:\n<data>\n{observations}\n</data>\n\n"
                    f"You may add at most {budget} steps. Return the revision JSON."
                ),
            },
        ]
        revision = generate_structured(self.llm, messages, Revision, purpose="revise", log=self.log, max_tokens=2000)
        existing_ids = {s.id for s in existing}
        accepted: list[PlanStep] = []
        signatures = {(s.tool, json.dumps(s.args, sort_keys=True, default=str)) for s in existing}
        for step in revision.additional_steps:
            sig = (step.tool, json.dumps(step.args, sort_keys=True, default=str))
            if step.tool not in self.tools or sig in signatures:
                continue
            base = step.id or "r"
            new_id = base if base not in existing_ids else f"r{len(existing_ids) + 1}"
            while new_id in existing_ids:
                new_id += "x"
            step.id = new_id
            existing_ids.add(new_id)
            signatures.add(sig)
            step.depends_on = [d for d in step.depends_on if d in existing_ids]
            accepted.append(step)
        revision.additional_steps = accepted[:budget]
        revision.complete = revision.complete and not revision.additional_steps
        return revision
