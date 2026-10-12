from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from app.core.errors import ValidationFailed
from app.services.analytics import anomaly, stats
from app.services.analytics.querybuilder import Filter, MetricSpec, QueryBuilder, parse_period


def test_pct_change_and_undefined() -> None:
    assert stats.pct_change(820000, 678140) == pytest.approx(-17.3, abs=1e-9)
    assert stats.pct_change(0, 5) is None
    assert stats.pct_change(None, 5) is None


def test_describe_with_confidence_interval() -> None:
    out = stats.describe([1, 2, 3, 4, 5, None])
    assert out["count"] == 5 and out["mean"] == 3 and out["median"] == 3
    assert out["variance"] == pytest.approx(2.5)
    assert out["ci_low"] < 3 < out["ci_high"]


def test_trend_detects_increase_and_noise() -> None:
    assert stats.trend([1, 2, 3, 4, 5, 6, 7, 8]).direction == "increasing"
    rng = np.random.default_rng(1)
    assert stats.trend(rng.normal(10, 1, 30)).direction in {"no_significant_trend", "increasing", "decreasing"}
    assert stats.trend([1, 2]).direction == "insufficient_data"


def test_correlation_never_claims_causation() -> None:
    x = pd.Series(range(50))
    result = stats.correlation(x, x * 2 + 1)
    assert result["coefficient"] == pytest.approx(1.0)
    assert "not establish causation" in result["note"]
    assert stats.correlation(pd.Series([1, 1, 1]), pd.Series([1, 2, 3]))["coefficient"] is None


def test_contribution_sums_to_100() -> None:
    rows = stats.contribution({"A": 100, "B": 100, "C": 50}, {"A": 60, "B": 90, "C": 60})
    total = sum(r["contribution_pct"] for r in rows)
    assert total == pytest.approx(100.0)
    assert rows[0]["segment"] == "A"  # largest contributor to the decline first


def test_price_volume_decomposition_is_additive() -> None:
    dec = stats.price_volume_decomposition(q0=100, p0=10, q1=80, p1=11)
    assert dec["volume_effect"] + dec["price_effect"] == pytest.approx(dec["change"])


def test_compare_groups_detects_difference() -> None:
    rng = np.random.default_rng(0)
    res = stats.compare_groups(pd.Series(rng.normal(10, 1, 200)), pd.Series(rng.normal(12, 1, 200)))
    assert res["significant"] and res["welch_p"] < 0.001


def _daily(values: list[float]) -> pd.Series:
    return pd.Series(values, index=[str(dt.date(2026, 1, 1) + dt.timedelta(days=i)) for i in range(len(values))])


def test_rolling_detects_planted_drop_not_weekend_pattern() -> None:
    rng = np.random.default_rng(3)
    values = [100 + (30 if i % 7 in (5, 6) else 0) + rng.normal(0, 3) for i in range(84)]
    values[70] = 20.0
    found = anomaly.detect_rolling(_daily(values), "revenue", seasonal_period=7, threshold=3.5)
    keys = {a.key for a in found}
    assert str(dt.date(2026, 1, 1) + dt.timedelta(days=70)) in keys
    assert len(found) <= 3  # weekends are not flagged
    drop = next(a for a in found if a.observed == 20.0)
    assert drop.direction == "drop" and drop.severity == "high" and drop.deviation_pct < -50


def test_zscore_iqr_isolation_forest() -> None:
    values = [10.0] * 40 + [100.0]
    series = _daily(values)
    assert anomaly.detect_zscore(series, "m", threshold=3)[0].observed == 100.0
    assert anomaly.detect_iqr(series, "m")[0].method == "iqr"
    frame = pd.DataFrame({"v": [10.0 + (i % 3) for i in range(60)] + [90.0], "k": range(61)})
    found = anomaly.detect_isolation_forest(frame, "v", key_column="k", contamination=0.02)
    assert any(a.observed == 90.0 for a in found)
    required = {"metric", "dimension", "key", "observed", "baseline", "deviation_pct", "method", "severity"}
    assert required <= set(found[0].as_dict())


@pytest.mark.parametrize(("spec", "start", "end"), [
    ("2026-Q3", "2026-07-01", "2026-09-30"), ("Q1 2026", "2026-01-01", "2026-03-31"),
    ("2026-02", "2026-02-01", "2026-02-28"), ("March 2026", "2026-03-01", "2026-03-31"),
    ("2026", "2026-01-01", "2026-12-31"), ("H2 2026", "2026-07-01", "2026-12-31"),
    ("2026-Q2..2026-Q3", "2026-04-01", "2026-09-30"), ("2026-01-05..2026-01-09", "2026-01-05", "2026-01-09"),
])
def test_parse_period(spec: str, start: str, end: str) -> None:
    period = parse_period(spec)
    assert (period.start.isoformat(), period.end.isoformat()) == (start, end)


def test_relative_periods() -> None:
    ref = dt.date(2026, 1, 15)
    assert parse_period("previous_quarter", ref).label == "2025-Q4"
    assert parse_period("latest_month", ref).label == "2026-01"
    with pytest.raises(ValidationFailed):
        parse_period("someday")


def test_query_builder_escapes_and_checks_columns() -> None:
    qb = QueryBuilder("sales", {"region": "VARCHAR", "revenue": "DOUBLE", "date": "DATE"}, "duckdb")
    sql = qb.select([qb.col("region"), qb.metric_expr(MetricSpec(column="revenue")).as_("revenue")],
                    filters=[Filter(column="region", op="in", value=["North", "O'Brien'; DROP TABLE x;--"])],
                    group_by=[qb.col("region")])
    assert "'O''Brien''; DROP TABLE x;--'" in sql
    with pytest.raises(ValidationFailed) as err:
        qb.col("regions")
    assert err.value.details["suggestions"] == ["region"]
    with pytest.raises(ValidationFailed):
        qb.metric_expr(MetricSpec(column="region", agg="sum"))
