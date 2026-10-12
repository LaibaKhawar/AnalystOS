"""Anomaly detection: z-score, IQR, rolling-baseline (seasonality-aware) and Isolation Forest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.services.analytics.stats import _f, iqr_bounds

METHODS = ("zscore", "iqr", "rolling", "isolation_forest")


@dataclass
class Anomaly:
    metric: str
    dimension: str | None
    key: str  # timestamp or category value
    observed: float
    baseline: float | None
    deviation: float | None
    deviation_pct: float | None
    score: float | None
    method: str
    severity: str
    direction: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _severity(score: float, thresholds: tuple[float, float, float]) -> str:
    low, medium, high = thresholds
    magnitude = abs(score)
    if magnitude >= high:
        return "high"
    if magnitude >= medium:
        return "medium"
    return "low" if magnitude >= low else "none"


def _make(metric: str, dimension: str | None, key: Any, observed: float, baseline: float | None, score: float | None,
          method: str, severity: str) -> Anomaly:
    deviation = observed - baseline if baseline is not None else None
    deviation_pct = (deviation / abs(baseline) * 100) if baseline not in (None, 0) and deviation is not None else None
    return Anomaly(
        metric=metric, dimension=dimension, key=str(key), observed=_f(observed) or 0.0, baseline=_f(baseline),
        deviation=_f(deviation), deviation_pct=_f(deviation_pct, 2), score=_f(score, 3), method=method,
        severity=severity, direction="spike" if (deviation or 0) > 0 else "drop",
    )


def detect_zscore(series: pd.Series, metric: str, dimension: str | None = None, threshold: float = 3.0) -> list[Anomaly]:
    values = pd.to_numeric(series, errors="coerce")
    mean, std = values.mean(), values.std(ddof=0)
    if not std or np.isnan(std):
        return []
    out = []
    for key, value in values.items():
        if pd.isna(value):
            continue
        z = (value - mean) / std
        if abs(z) >= threshold:
            out.append(_make(metric, dimension, key, float(value), float(mean), float(z), "zscore",
                             _severity(z, (threshold, threshold + 1, threshold + 2))))
    return out


def detect_iqr(series: pd.Series, metric: str, dimension: str | None = None, k: float = 1.5) -> list[Anomaly]:
    values = pd.to_numeric(series, errors="coerce")
    if values.dropna().size < 4:
        return []
    low, high = iqr_bounds(values, k)
    median = float(values.median())
    iqr = (high - low) / (1 + 2 * k) if high > low else 0
    out = []
    for key, value in values.items():
        if pd.isna(value) or low <= value <= high:
            continue
        distance = (value - high) / iqr if value > high and iqr else (low - value) / iqr if iqr else 0
        out.append(_make(metric, dimension, key, float(value), median, float(distance), "iqr",
                         _severity(distance, (0.0, 1.5, 3.0))))
    return out


def detect_rolling(
    series: pd.Series, metric: str, dimension: str | None = None, window: int = 7, threshold: float = 3.0,
    seasonal_period: int | None = None, log_scale: bool | None = None,
) -> list[Anomaly]:
    """Compare each point to a trailing baseline (excluding the point itself).

    With seasonal_period (e.g. 7 for daily data) the baseline uses the same position in previous
    cycles, so routine weekday/weekend patterns are not flagged.
    """
    raw = pd.to_numeric(series, errors="coerce").astype(float)
    if raw.dropna().size < window + 2:
        return []
    if log_scale is None:
        # Sales-like metrics are non-negative with multiplicative noise; compare on a log scale so a collapse
        # to near zero is not hidden by large day-to-day swings.
        mean = float(raw.mean() or 0)
        log_scale = bool(raw.min() >= 0 and mean > 0 and float(raw.std(ddof=0)) / mean > 0.3)
    values = np.log1p(raw) if log_scale else raw
    if seasonal_period and values.size >= seasonal_period * 4:
        shifted = pd.concat([values.shift(seasonal_period * i) for i in range(1, 5)], axis=1)
        baseline = shifted.median(axis=1)
        # Noise scale: rolling std of past residuals (observed - seasonal baseline), excluding the current point.
        residual = values - baseline
        spread = residual.shift(1).rolling(window=seasonal_period * 4, min_periods=seasonal_period * 2).std(ddof=0)
        method = "seasonal_rolling"
    else:
        trailing = values.shift(1).rolling(window=window, min_periods=max(3, window // 2))
        baseline = trailing.mean()
        spread = trailing.std(ddof=0)
        method = "rolling_zscore"
    if log_scale:
        method += "_log"
    global_spread = float(values.std(ddof=0) or 0)
    out = []
    for key in values.index:
        observed, base, sd = values[key], baseline[key], spread[key]
        if pd.isna(observed) or pd.isna(base):
            continue
        sd = sd if sd and not pd.isna(sd) and sd > 0.05 * global_spread else max(global_spread, 1e-9)
        z = (observed - base) / sd
        if abs(z) >= threshold:
            shown_base = float(np.expm1(base)) if log_scale else float(base)
            out.append(_make(metric, dimension, key, float(raw[key]), shown_base, float(z), method,
                             _severity(z, (threshold, threshold + 1.5, threshold + 3))))
    return out


def detect_isolation_forest(
    frame: pd.DataFrame, metric: str, features: list[str] | None = None, contamination: float = 0.02,
    dimension: str | None = None, key_column: str | None = None, random_state: int = 42,
) -> list[Anomaly]:
    features = features or [metric]
    data = frame[features].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 20:
        return []
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=random_state)
    labels = model.fit_predict(data.to_numpy())
    scores = -model.score_samples(data.to_numpy())
    median = float(data[metric].median())
    cutoff = float(np.quantile(scores, 1 - contamination))
    spread = float(np.std(scores)) or 1.0
    out = []
    for idx, label, score in zip(data.index, labels, scores, strict=True):
        if label != -1:
            continue
        key = frame.loc[idx, key_column] if key_column else idx
        rel = (score - cutoff) / spread
        out.append(_make(metric, dimension, key, float(data.loc[idx, metric]), median, float(score),
                         "isolation_forest", "high" if rel > 2 else "medium" if rel > 0.5 else "low"))
    return out


def rank(anomalies: list[Anomaly], limit: int = 20) -> list[Anomaly]:
    order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    return sorted(anomalies, key=lambda a: (order.get(a.severity, 3), -abs(a.score or 0)))[:limit]
