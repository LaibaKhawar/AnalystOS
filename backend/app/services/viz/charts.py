"""Chart specs built only from stored result tables. The front end renders them (Recharts).

Rules that prevent misleading charts: bar/stacked-bar value axes start at zero; histograms and box plots
are binned/summarised server-side from the real values; the chart stores a hash of its data so the
verifier can prove the chart matches its source result.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

CHART_TYPES = ("line", "bar", "stacked_bar", "scatter", "histogram", "box", "heatmap", "area")


class ChartSpecError(ValueError):
    pass


def data_hash(data: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def recommend_type(columns: list[dict[str, str]], rows: list[list[Any]]) -> tuple[str, str, list[str]] | None:
    """Heuristic chart choice for a result table: (type, x, [y...]) or None if nothing sensible."""
    if not rows or len(columns) < 2:
        return None
    names = [c["name"] for c in columns]
    frame = pd.DataFrame(rows, columns=names)
    numeric = [n for n in names if pd.to_numeric(frame[n], errors="coerce").notna().mean() > 0.9]
    temporal = [n for n in names if n not in numeric and _is_dateish(frame[n])]
    categorical = [n for n in names if n not in numeric and n not in temporal]
    if temporal and numeric:
        return "line", temporal[0], numeric[:3]
    if categorical and numeric:
        return "bar", categorical[0], numeric[:1]
    if len(numeric) >= 2:
        return "scatter", numeric[0], [numeric[1]]
    return None


def _is_dateish(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).head(20)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return bool(parsed.notna().mean() > 0.9) and sample.str.len().min() >= 7


def build_chart(
    chart_type: str,
    columns: list[dict[str, str]],
    rows: list[list[Any]],
    *,
    x: str,
    y: list[str],
    series: str | None = None,
    title: str,
    bins: int = 20,
    max_points: int = 2000,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if chart_type not in CHART_TYPES:
        raise ChartSpecError(f"chart_type must be one of {', '.join(CHART_TYPES)}")
    names = [c["name"] for c in columns]
    frame = pd.DataFrame(rows, columns=names)
    missing = [c for c in [x, *y, *([series] if series else [])] if c and c not in names]
    if missing:
        raise ChartSpecError(f"Columns {missing} are not in the result. Available: {names}")
    if frame.empty:
        raise ChartSpecError("The result has no rows to chart")
    spec: dict[str, Any] = {
        "type": chart_type,
        "title": title,
        "x": x,
        "y": y,
        "series": series,
        "x_label": x,
        "y_label": ", ".join(y),
    }
    if chart_type == "histogram":
        values = pd.to_numeric(frame[x], errors="coerce").dropna()
        counts, edges = np.histogram(values, bins=min(bins, max(5, int(np.sqrt(len(values))))))
        data = [
            {
                "bin_start": float(edges[i]),
                "bin_end": float(edges[i + 1]),
                "label": f"{edges[i]:.4g} to {edges[i + 1]:.4g}",
                "count": int(c),
            }
            for i, c in enumerate(counts)
        ]
        spec.update(x="label", y=["count"], y_zero=True, x_label=x, y_label="count")
        return spec, data
    if chart_type == "box":
        groups = frame.groupby(series) if series else [("all", frame)]
        data = []
        for key, group in groups:
            values = pd.to_numeric(group[y[0]], errors="coerce").dropna()
            if values.empty:
                continue
            q1, med, q3 = values.quantile([0.25, 0.5, 0.75])
            iqr = q3 - q1
            lo = float(values[values >= q1 - 1.5 * iqr].min())
            hi = float(values[values <= q3 + 1.5 * iqr].max())
            data.append(
                {
                    "group": str(key),
                    "min": lo,
                    "q1": float(q1),
                    "median": float(med),
                    "q3": float(q3),
                    "max": hi,
                    "outliers": int(((values < lo) | (values > hi)).sum()),
                    "n": int(values.size),
                }
            )
        spec.update(x="group", y=["median"], y_zero=False)
        return spec, data
    if chart_type == "heatmap":
        if len(y) != 1 or not series:
            raise ChartSpecError("heatmap needs x (column), series (row) and one y value column")
        data = [{"x": str(r[x]), "y": str(r[series]), "value": _num(r[y[0]])} for _, r in frame.iterrows()]
        spec.update(y_zero=False)
        return spec, data[:max_points]
    for column in y:
        coerced = pd.to_numeric(frame[column], errors="coerce")
        if coerced.notna().sum() == 0:
            raise ChartSpecError(f"y column '{column}' is not numeric")
        frame[column] = coerced
    if series:
        if len(y) != 1:
            raise ChartSpecError("With 'series', pass exactly one y column")
        pivot = frame.pivot_table(index=x, columns=series, values=y[0], aggfunc="sum").reset_index()
        pivot.columns = [str(c) for c in pivot.columns]
        spec["y"] = [c for c in pivot.columns if c != x][:12]
        frame = pivot
    if chart_type in {"line", "area"}:
        frame = frame.sort_values(x)
    data = [
        {str(k): (_num(v) if k != x else (str(v) if v is not None else None)) for k, v in record.items()}
        for record in frame[[x, *spec["y"]]].head(max_points).to_dict(orient="records")
    ]
    spec["y_zero"] = chart_type in {"bar", "stacked_bar", "area"}
    if chart_type in {"line"}:
        points = [float(v) for d in data for k in spec["y"] if isinstance(v := d.get(k), int | float)]
        if points and min(points) > 0 and (max(points) - min(points)) / max(points) < 0.05:
            spec["note"] = "Values vary by less than 5%; the axis is zoomed to make the variation visible."
    return spec, data


def _num(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return None if np.isnan(number) or np.isinf(number) else number
