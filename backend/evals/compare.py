"""Side-by-side comparison of evaluation results across models.

Each input is a results file written by evals.run: either a single run (`evals/results/<run_id>.json`) or a
repeated-run summary (`evals/results/summary_<batch>.json`, reported as mean with min..max).

  python -m evals.compare evals/results/summary_A.json evals/results/summary_B.json --out ../docs/model-comparison.md

Typical workflow for a new model:
  python -m evals.run --repeat 3 --model gpt-4o-mini --base-url https://api.openai.com/v1 \
      --api-key-env OPENAI_API_KEY --notes "gpt-4o-mini"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROWS: list[tuple[str, str, bool]] = [  # (metric key, label, higher is better)
    ("pass_rate", "Overall pass rate", True),
    ("numerical_accuracy", "Numerical accuracy", True),
    ("entity_accuracy", "Entity accuracy", True),
    ("sql_execution_accuracy", "Computation accuracy", True),
    ("unsupported_claim_rate_draft", "Unsupported numbers in drafts", False),
    ("unsupported_claim_rate_final", "Unsupported numbers in final answers", False),
    ("first_pass_success_rate", "First-pass step success", True),
    ("retry_recovery_rate", "Retry recovery", True),
    ("safety_pass_rate", "Safety cases passed", True),
    ("latency_p50_ms", "Latency p50", False),
    ("latency_p95_ms", "Latency p95", False),
    ("avg_llm_calls", "LLM calls per task", False),
    ("avg_cost_usd", "Cost per task", False),
]


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if "stats" in data:  # repeated-run summary
        return {
            "label": data.get("model", path.stem),
            "runs": len(data["runs"]),
            "values": {k: (v["mean"], v["min"], v["max"]) for k, v in data["stats"].items()},
        }
    return {
        "label": data["model"],
        "runs": 1,
        "values": {k: (v, v, v) for k, v in data["metrics"].items() if isinstance(v, int | float)},
    }


def fmt(key: str, value: float) -> str:
    if key.endswith("_ms"):
        return f"{value / 1000:.1f}s"
    if "cost" in key:
        return f"${value:.4f}"
    if key == "avg_llm_calls":
        return f"{value:.2f}"
    return f"{value * 100:.1f}%"


def table(entries: list[dict[str, Any]]) -> str:
    header = (
        "| Metric | "
        + " | ".join(f"{e['label']} ({e['runs']} run{'s' if e['runs'] > 1 else ''})" for e in entries)
        + " |"
    )
    lines = [header, "|---|" + "---|" * len(entries)]
    for key, label, higher in ROWS:
        cells = [e["values"].get(key) for e in entries]
        means = [c[0] for c in cells if c is not None]
        best = (max(means) if higher else min(means)) if means else None
        row = []
        for cell in cells:
            if cell is None:
                row.append("n/a")
                continue
            text = fmt(key, cell[0])
            if cell[1] != cell[2]:
                text += f" ({fmt(key, cell[1])} to {fmt(key, cell[2])})"
            if best is not None and cell[0] == best and len(entries) > 1:
                text = f"**{text}**"
            row.append(text)
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare evaluation results across models")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    text = "# Model comparison\n\nBest value per row in bold; ranges are min to max across repeated runs.\n\n" + table(
        [load(p) for p in args.files]
    )
    if args.out:
        args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
