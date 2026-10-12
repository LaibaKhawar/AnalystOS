# Evaluation methodology

## Data

`backend/evals/datasets/generate.py` produces deterministic data from a fixed seed (CI regenerates it and fails on
any diff):

| Dataset | Rows | Planted structure |
|---|---|---|
| `sales.csv` | 26,358 | Nov/Dec seasonality and a February dip; Lahore decline in 2026-Q3 concentrated in Aurora Laptop (fewer units, lower price); Nimbus Earbuds promotion in March 2026; Karachi outage on 2026-08-14; company-wide flash sale on 2026-05-20; 1.5% missing segments, 0.5% missing cost, exactly 40 duplicated rows |
| `sales_2026.xlsx` | 3 sheets | Transactions (title rows above the header), monthly targets, region managers |
| `saas_subscriptions.csv` | 800 | plan-dependent churn (Starter highest), support tickets associated with churn, expansion/contraction vs `initial_mrr`, anomalous accounts |
| `marketing_performance.csv` | 1,365 | five channels with different cost per conversion, June social push |
| `adversarial_accounts.csv` | 120 | prompt-injection text in a notes column, columns named `Revenue ($)`, `Customer ID`, `2026 Sales`, `Growth %` |

Ground truth (`evals/data/ground_truth.json`) is computed from the generated frames with pandas, independently of
the application code; cases reference it as `$gt.<key>`.

## Cases (67)

`evals/cases.yaml`: numeric (21), multi-table (14: the Chinook database over a SQLite connection with joins across
up to three tables, and a two-sheet CRM workbook), entity (13), safety (5: destructive SQL, SQL smuggled into a
question, prompt injection, environment exfiltration), drivers (3), recovery (2: wrong column names on purpose),
follow-up (2-turn conversation), clarification (2), fast path (2), anomaly, chart and saved-metric cases. Cases that
need multi-step reasoning are marked `hard`. Chinook is MIT-licensed (`evals/data/CHINOOK_LICENSE.md`).

## Metrics

| Metric | Definition |
|---|---|
| Numerical accuracy | numeric cases whose verified answer (headline + facts) states the expected value within tolerance (relative %, percentage points, or absolute) |
| Entity accuracy | entity cases whose answer names the expected entity |
| SQL / computation accuracy | the expected value or entity appears in the findings or result tables the tools computed, independent of the prose |
| Analysis correctness | share of expected columns that the executed tool calls and SQL actually used |
| Chart correctness | expected charts exist, are verified against their source result, and use the expected columns |
| Unsupported claim rate (draft) | numeric sentences in the model's first draft that the verifier rejected (a hallucination measure) |
| Unsupported claim rate (final) | numeric sentences shown to the user without evidence rows (checked independently from claim/evidence tables) |
| Tool success | successful tool executions / all executions |
| First-pass success | plan steps whose first attempt succeeded |
| Retry recovery | steps with a recoverable first failure that later succeeded |
| Unsafe SQL executed | executed statements that an independent re-check does not classify as read-only selects |
| Safety pass rate | safety cases with nothing unsafe executed and no secret or canary leaked |
| Latency p50/p95, cost, tokens | from the analysis records (cost uses the configurable price table; local models cost $0) |

Run it with `make eval` or `python -m evals.run [--cases ...] [--categories ...] [--repeat N] [--concurrency K]
[--model M --base-url URL --api-key-env VAR]`. With `--repeat`, a summary reports mean, standard deviation, min and
max per metric and lists cases that are unstable or always fail. `python -m evals.compare <results...>` builds a
side-by-side table across models. Every run is stored
in `evaluation_runs` / `evaluation_cases` (visible on the Evaluations page) and written to
`backend/evals/results/<run_id>.json` and `.md`.

## Caveats

- Results depend heavily on the model. The published numbers come from a local quantized model on a laptop;
  re-run with a hosted model by changing `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`.
- The benchmark is synthetic. It tests the system's mechanics (planning, recovery, verification, safety) with known
  answers; it is not a measure of performance on arbitrary real-world data.
- String matching for entities and numbers is strict but can, rarely, credit an answer that mentions the right
  value in a different context; per-case answers are stored for inspection.
