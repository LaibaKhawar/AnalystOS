from __future__ import annotations

import pytest

from app.agent.fastpath import match
from app.db.models import ColumnMetadata, DataSource, TableMetadata


def _source(sampled: bool = False) -> DataSource:
    table = TableMetadata(name="sales", display_name="sales", row_count=100, profile={"sampled": sampled})
    table.columns = [
        ColumnMetadata(
            name="revenue",
            original_name="revenue",
            ordinal=0,
            physical_type="DOUBLE",
            inferred_type="float",
            role="metric",
            stats={},
        ),
        ColumnMetadata(
            name="units",
            original_name="units",
            ordinal=1,
            physical_type="BIGINT",
            inferred_type="integer",
            role="metric",
            stats={},
        ),
        ColumnMetadata(
            name="region",
            original_name="region",
            ordinal=2,
            physical_type="VARCHAR",
            inferred_type="string",
            role="dimension",
            stats={"top_values": [{"value": "Lahore", "count": 5}, {"value": "Karachi", "count": 4}]},
        ),
        ColumnMetadata(
            name="order_id",
            original_name="order_id",
            ordinal=3,
            physical_type="VARCHAR",
            inferred_type="string",
            role="identifier",
            stats={},
        ),
    ]
    source = DataSource(name="s", kind="file")
    source.tables = [table]
    return source


@pytest.mark.parametrize(
    ("question", "column", "stat"),
    [
        ("What is the average revenue?", "revenue", "mean"),
        ("total units", "units", "sum"),
        ("Median revenue?", "revenue", "median"),
        ("How many rows are there?", None, "rows"),
        ("What share of region values is missing?", "region", "missing_pct"),
        ("How many distinct regions are there?", "region", "distinct"),
    ],
)
def test_simple_statistics_match(question: str, column: str | None, stat: str) -> None:
    found = match(question, _source())
    assert found is not None and (found.column, found.stat) == (column, stat)


@pytest.mark.parametrize(
    "question",
    [
        "Which region has the highest revenue?",  # ranking
        "Average revenue by region",  # grouping
        "Average revenue in Lahore",  # filter value
        "Average revenue in 2026",  # time
        "Average revenue and units",  # two columns
        "What is the average region?",  # not numeric
        "Why did revenue fall?",
        "Compare revenue with units",
    ],
)
def test_anything_else_goes_to_the_agent(question: str) -> None:
    assert match(question, _source()) is None


def test_sampled_profiles_are_not_used() -> None:
    assert match("What is the average revenue?", _source(sampled=True)) is None
