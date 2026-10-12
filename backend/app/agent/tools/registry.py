"""Tool registry. Adding a tool = implement Tool and list it here."""

from __future__ import annotations

from app.agent.tools.base import Tool
from app.agent.tools.investigation_tools import DetectAnomalies, IdentifyDrivers
from app.agent.tools.metric_tools import (
    AggregateMetric,
    AnalyzeSegments,
    CalculateCorrelation,
    ComparePeriods,
    ComputeStatistics,
)
from app.agent.tools.output_tools import (
    CreateChart,
    GenerateReport,
    RetrieveEvidence,
    RetrievePreviousAnalysis,
)
from app.agent.tools.python_tool import ExecutePython
from app.agent.tools.schema_tools import DescribeTable, InspectSchema, ListTables, ProfileDataset
from app.agent.tools.sql_tool import ExecuteSQL

ALL_TOOLS: list[type[Tool]] = [
    ListTables,
    DescribeTable,
    InspectSchema,
    ProfileDataset,
    AggregateMetric,
    ComparePeriods,
    AnalyzeSegments,
    ComputeStatistics,
    CalculateCorrelation,
    DetectAnomalies,
    IdentifyDrivers,
    ExecuteSQL,
    ExecutePython,
    CreateChart,
    RetrieveEvidence,
    RetrievePreviousAnalysis,
    GenerateReport,
]


def build_registry() -> dict[str, Tool]:
    return {tool.name: tool() for tool in ALL_TOOLS}


def tool_catalog(tools: dict[str, Tool]) -> str:
    lines = []
    for tool in tools.values():
        if not tool.planner_visible:
            continue
        args = ", ".join(f"{k}: {v}" for k, v in tool.schema_hint().items())
        lines.append(f"- {tool.name}: {tool.description}\n    args: {{{args}}}")
    return "\n".join(lines)
