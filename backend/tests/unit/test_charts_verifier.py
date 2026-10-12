from __future__ import annotations

import pytest

from app.agent.verifier import extract_numbers, verify_answer
from app.db.models import Finding
from app.services.viz.charts import ChartSpecError, build_chart, data_hash, recommend_type

COLUMNS = [{"name": "region", "type": "VARCHAR"}, {"name": "revenue", "type": "DOUBLE"}]
ROWS = [["North", 120.0], ["South", 80.0], ["East", 100.0]]


def test_bar_chart_from_result_starts_at_zero() -> None:
    spec, data = build_chart("bar", COLUMNS, ROWS, x="region", y=["revenue"], title="Revenue")
    assert spec["y_zero"] is True
    assert data == [
        {"region": "North", "revenue": 120.0},
        {"region": "South", "revenue": 80.0},
        {"region": "East", "revenue": 100.0},
    ]
    assert data_hash(data) == data_hash(list(data))


def test_chart_rejects_unknown_columns_and_empty() -> None:
    with pytest.raises(ChartSpecError, match="not in the result"):
        build_chart("bar", COLUMNS, ROWS, x="city", y=["revenue"], title="x")
    with pytest.raises(ChartSpecError):
        build_chart("bar", COLUMNS, [], x="region", y=["revenue"], title="x")


def test_histogram_and_box_are_computed_from_values() -> None:
    cols = [{"name": "g", "type": "VARCHAR"}, {"name": "v", "type": "DOUBLE"}]
    rows = [["a", float(i)] for i in range(100)] + [["b", float(i) * 2] for i in range(100)]
    _, hist = build_chart("histogram", cols, rows, x="v", y=[], title="h")
    assert sum(b["count"] for b in hist) == 200
    _, box = build_chart("box", cols, rows, x="g", y=["v"], series="g", title="b")
    assert {b["group"] for b in box} == {"a", "b"}
    assert box[0]["q1"] <= box[0]["median"] <= box[0]["q3"]


def test_recommend_type() -> None:
    assert recommend_type(COLUMNS, ROWS)[0] == "bar"
    ts = [{"name": "period", "type": "DATE"}, {"name": "revenue", "type": "DOUBLE"}]
    assert recommend_type(ts, [["2026-01-01", 1.0], ["2026-02-01", 2.0]])[0] == "line"


def _finding(label: str, values: dict, entities=(), periods=()) -> Finding:  # type: ignore[no-untyped-def]
    return Finding(
        id=f"id_{label}",
        label=label,
        kind="comparison",
        statement="",
        values=values,
        payload={"entities": list(entities), "periods": list(periods)},
    )


F1 = _finding(
    "F1",
    {"previous": 820000, "current": 678140, "change": -141860, "pct_change": -17.3},
    ["Lahore"],
    ["2026-Q2", "2026-Q3"],
)
F2 = _finding("F2", {"value": 1234567.89, "share_pct": 41.2}, ["North"])


def _verify(text: str, citations: list[str], kind: str = "facts"):  # type: ignore[no-untyped-def]
    draft = {"summary": [], "facts": [], "interpretations": [], "recommendations": []}
    draft[kind] = [{"text": text, "citations": citations}]
    known = {"Lahore", "Karachi", "North", "South"}  # category values of the dataset
    return verify_answer(draft, [F1, F2], exempt_phrases=[], known_entities=known).claims[0]


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("Lahore revenue declined by 17.3% between Q2 and Q3.", "verified"),
        ("Lahore revenue fell from 820K to 678.1K.", "verified"),
        ("North generated $1.23M, 41.2% of revenue.", "verified"),
        ("Lahore's Q3 revenue was 82.7% of its Q2 revenue.", "verified"),  # derived share
        ("North generated $1.5M in revenue.", "removed"),  # wrong value
        ("Lahore declined 17.3% in Q1.", "removed"),  # wrong period
        ("Karachi declined by 17.3%.", "removed"),  # wrong entity
        ("Review the top 3 stores in Lahore.", "no_numbers"),
        ("The revenue change was -141,860 between Q2 and Q3.", "verified"),  # filter-scoped finding, no entity named
        ("South generated $1.23M.", "removed"),  # North's number attached to another known region
        ("The rate is conversions / clicks * 100% for the channel.", "no_numbers"),  # formula constant
    ],
)
def test_claim_verification(text: str, status: str) -> None:
    assert _verify(text, ["F1", "F2"]).status == status


def test_causal_language_is_qualified() -> None:
    claim = _verify("The Lahore decline was driven by fewer laptop orders.", ["F1"])
    assert claim.status == "qualified" and claim.kind == "interpretation"
    assert claim.text.startswith("Hypothesis (not causally verified)")


def test_unsupported_claims_never_reach_final_output() -> None:
    draft = {
        "headline": "Revenue jumped 99.9%",
        "summary": [{"text": "North made 777 units.", "citations": []}],
        "facts": [],
        "interpretations": [],
        "recommendations": [],
        "caveats": ["Margin was 12.34%."],
    }
    report = verify_answer(draft, [F1, F2], exempt_phrases=[])
    assert report.headline == "Analysis complete"
    assert all(c.status == "removed" for c in report.claims)
    assert report.caveats == []
    assert report.stats()["final_unsupported_rate"] == 0.0


def test_number_extraction_skips_years_dates_and_labels() -> None:
    tokens = [
        t.raw for t in extract_numbers("In 2026-Q3 (2026-07-01 to 2026-09-30) F12 shows 3 stores at -3.4M and 12.7%")
    ]
    assert tokens == ["-3.4M", "12.7%"]
    assert extract_numbers("Store 104 sold 5,200 units", exempt_phrases=["Store 104"])[0].value == 5200


def test_bare_citation_sentences_are_dropped() -> None:
    draft = {"summary": [{"text": "F1", "citations": ["F1"]}], "facts": [{"text": "[F1, F2]."}]}
    assert verify_answer(draft, [F1, F2], exempt_phrases=[]).claims == []
