"""Reusable statistical primitives. All numbers in reports originate from functions like these."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps


def _f(value: Any, digits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def pct_change(previous: float | None, current: float | None) -> float | None:
    """Percentage change from previous to current. None when undefined (previous is 0 or missing)."""
    if previous is None or current is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


def describe(values: pd.Series | list[float], confidence: float = 0.95) -> dict[str, Any]:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    n = int(series.size)
    if n == 0:
        return {"count": 0}
    mean = float(series.mean())
    std = float(series.std(ddof=1)) if n > 1 else 0.0
    out: dict[str, Any] = {
        "count": n,
        "sum": _f(series.sum()),
        "mean": _f(mean),
        "median": _f(series.median()),
        "variance": _f(series.var(ddof=1)) if n > 1 else 0.0,
        "std": _f(std),
        "min": _f(series.min()),
        "max": _f(series.max()),
        "q1": _f(series.quantile(0.25)),
        "q3": _f(series.quantile(0.75)),
        "p05": _f(series.quantile(0.05)),
        "p95": _f(series.quantile(0.95)),
        "skew": _f(series.skew()) if n > 2 else None,
    }
    if n > 1:
        sem = std / math.sqrt(n)
        margin = float(sps.t.ppf((1 + confidence) / 2, n - 1)) * sem
        out["ci_level"] = confidence
        out["ci_low"], out["ci_high"] = _f(mean - margin), _f(mean + margin)
    return out


def zscores(values: pd.Series) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce")
    std = series.std(ddof=0)
    if not std or math.isnan(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def iqr_bounds(values: pd.Series, k: float = 1.5) -> tuple[float, float]:
    series = pd.to_numeric(values, errors="coerce").dropna()
    q1, q3 = float(series.quantile(0.25)), float(series.quantile(0.75))
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


def rolling_mean(values: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").rolling(window=window, min_periods=max(2, window // 2)).mean()


@dataclass
class Trend:
    slope_per_period: float | None
    intercept: float | None
    r_squared: float | None
    p_value: float | None
    n: int
    direction: str
    pct_change_first_last: float | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def trend(values: pd.Series | list[float]) -> Trend:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna().reset_index(drop=True)
    n = int(series.size)
    if n < 3:
        return Trend(None, None, None, None, n, "insufficient_data", None)
    x = np.arange(n, dtype=float)
    fit = sps.linregress(x, series.to_numpy(dtype=float))
    significant = fit.pvalue is not None and fit.pvalue < 0.05
    direction = ("increasing" if fit.slope > 0 else "decreasing") if significant else "no_significant_trend"
    return Trend(
        _f(fit.slope),
        _f(fit.intercept),
        _f(fit.rvalue**2),
        _f(fit.pvalue),
        n,
        direction,
        _f(pct_change(float(series.iloc[0]), float(series.iloc[-1]))),
    )


def correlation(x: pd.Series, y: pd.Series, method: str = "pearson") -> dict[str, Any]:
    frame = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    n = len(frame)
    if n < 3 or frame["x"].nunique() < 2 or frame["y"].nunique() < 2:
        return {"method": method, "n": n, "coefficient": None, "p_value": None, "strength": "undefined"}
    if method == "spearman":
        res = sps.spearmanr(frame["x"], frame["y"])
        coef, p = float(res.statistic), float(res.pvalue)
    else:
        res = sps.pearsonr(frame["x"], frame["y"])
        coef, p = float(res.statistic), float(res.pvalue)
    magnitude = abs(coef)
    strength = (
        "very weak"
        if magnitude < 0.2
        else "weak"
        if magnitude < 0.4
        else "moderate"
        if magnitude < 0.6
        else "strong"
        if magnitude < 0.8
        else "very strong"
    )
    return {
        "method": method,
        "n": n,
        "coefficient": _f(coef, 4),
        "p_value": _f(p, 6),
        "strength": strength,
        "significant": p < 0.05,
        "note": "Correlation does not establish causation.",
    }


def compare_groups(a: pd.Series, b: pd.Series) -> dict[str, Any]:
    """Welch's t-test and Mann-Whitney U for two independent samples."""
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    out: dict[str, Any] = {
        "n_a": int(a.size),
        "n_b": int(b.size),
        "mean_a": _f(a.mean()),
        "mean_b": _f(b.mean()),
        "median_a": _f(a.median()),
        "median_b": _f(b.median()),
    }
    out["mean_diff"] = _f(a.mean() - b.mean()) if a.size and b.size else None
    if a.size >= 2 and b.size >= 2:
        t = sps.ttest_ind(a, b, equal_var=False)
        out["welch_t"], out["welch_p"] = _f(t.statistic), _f(t.pvalue)
        u = sps.mannwhitneyu(a, b, alternative="two-sided")
        out["mann_whitney_u"], out["mann_whitney_p"] = _f(u.statistic), _f(u.pvalue)
        pooled = math.sqrt(((a.size - 1) * a.var() + (b.size - 1) * b.var()) / (a.size + b.size - 2))
        out["cohens_d"] = _f((a.mean() - b.mean()) / pooled) if pooled else None
        out["significant"] = bool(t.pvalue < 0.05)
    return out


def contribution(previous: dict[str, float], current: dict[str, float]) -> list[dict[str, Any]]:
    """Additive decomposition of a total change into per-segment contributions.

    contribution_pct is the segment's share of the total change (sums to 100 across segments). Segments
    moving against the overall direction have negative shares.
    """
    keys = sorted(set(previous) | set(current), key=str)
    total_prev = sum(previous.get(k, 0.0) or 0.0 for k in keys)
    total_curr = sum(current.get(k, 0.0) or 0.0 for k in keys)
    total_change = total_curr - total_prev
    rows = []
    for key in keys:
        p = float(previous.get(key, 0.0) or 0.0)
        c = float(current.get(key, 0.0) or 0.0)
        change = c - p
        rows.append(
            {
                "segment": key,
                "previous": _f(p),
                "current": _f(c),
                "change": _f(change),
                "pct_change": _f(pct_change(p, c)),
                "contribution_pct": _f(change / total_change * 100) if total_change else None,
                "share_of_previous_pct": _f(p / total_prev * 100) if total_prev else None,
            }
        )
    direction = 1.0 if total_change >= 0 else -1.0
    rows.sort(key=lambda r: direction * float(r["change"] or 0), reverse=True)
    return rows


def price_volume_decomposition(q0: float, p0: float, q1: float, p1: float) -> dict[str, Any]:
    """Revenue change = volume effect + price/mix effect (exact, additive)."""
    r0, r1 = q0 * p0, q1 * p1
    volume = (q1 - q0) * p0
    price = (p1 - p0) * q1
    return {
        "previous_revenue": _f(r0),
        "current_revenue": _f(r1),
        "change": _f(r1 - r0),
        "volume_effect": _f(volume),
        "price_effect": _f(price),
        "previous_volume": _f(q0),
        "current_volume": _f(q1),
        "previous_avg_price": _f(p0),
        "current_avg_price": _f(p1),
        "volume_pct_change": _f(pct_change(q0, q1)),
        "avg_price_pct_change": _f(pct_change(p0, p1)),
    }
