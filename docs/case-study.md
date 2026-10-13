# Case study: building an AI data analyst you can audit

AnalystOS answers business questions about uploaded files and SQL databases. This write-up covers the design
decisions behind it, the failures that shaped them, and what the measurements say. Numbers come from the
benchmark in [evaluation](evaluation.md); nothing here is estimated.

## The problem with "chat with your data"

A language model asked to analyse a spreadsheet will happily produce a fluent paragraph full of numbers. Some of
them are right. The reader cannot tell which. For analytics that is worse than no answer, because the confident
wrong number gets pasted into a slide.

So the goal was not "an LLM that knows SQL". It was: **every number shown to a user must be traceable to the query
or computation that produced it, and anything that cannot be traced must not be shown.**

## Design: the model never does arithmetic

1. **Tools compute, the model chooses.** Deterministic tools (period comparison, contribution analysis, anomaly
   detection, statistics, validated SQL, sandboxed Python) do all calculation. Each emits *findings*: structured
   facts with values, a formula, the entities they are about and the periods they cover.
2. **The model writes, citing findings.** The synthesis prompt shows findings as `F7: Lahore revenue went from
   774,632.39 to 511,268.98 (-34.00%)` and asks for an answer that cites labels.
3. **A verifier decides what survives.** Every number in every sentence must match a cited finding at the
   precision the writer used ("1.2M" matches 1,234,567), or recompute from two of its values (percent change,
   share). The sentence must name the finding's entity and must not contradict its period. Failing sentences are
   removed (kept for audit), and the model gets one chance to restate them from the evidence.

The result is a measurable property instead of a hope: the share of numeric sentences shown without evidence is
reported by every evaluation run.

## Failure 1: the model invented column names, and it was not the model's fault

Early runs with a local 8B model planned queries against tables and columns that did not exist (`orders`,
`order_date`, `product_category`). The obvious diagnosis was "small models are bad at schemas".

The real cause: Ollama's default context window is 4,096 tokens and it **silently truncates** longer prompts. The
planner prompt (tool catalogue plus schema) was longer than that, so the model never saw most of the schema. After
raising the context to 16K, the same model went from failing most plans to passing 8 of 8 on the same subset.

Lesson: when an LLM system misbehaves, check what the model actually received before blaming the model.

## Failure 2: numbers can be right and the answer still wrong

The verifier caught every fabricated number in the benchmark, but one answer was still wrong: asked how many
customers expanded (MRR above initial MRR), the model also excluded churned customers and answered 152 instead of
189. Every number was real. It was the answer to a different question.

Number verification cannot catch that, so a second check was added before execution: the **scope check** compares
the plan's filters and time windows with the question and conversation context, and anything the user never
mentioned is sent back to the planner once; whatever remains is shown as an explicit assumption. Comparisons
between two columns (`mrr > initial_mrr`) define the question and are left alone.

## Failure 3: bugs that only real infrastructure finds

The unit and integration suites passed, yet running the full Docker stack and concurrent evaluations found bugs the
tests could not:

- `CORS_ORIGINS=a,b` crashed startup (the settings library parses lists as JSON before custom validators run).
- An empty `PRICING_FILE=` resolved to the working directory, so cost accounting crashed, and the error path then
  left the analysis stuck as "running".
- Deleting a data source deleted its files before the database transaction committed; a failed delete left
  metadata pointing at missing files.
- Two analyses on the same uploaded dataset at once crashed: DuckDB shares one database instance per file, and the
  security settings were already locked by the first connection. The fix verifies the locked values are safe
  instead of assuming it.
- A planted outage day vanished from anomaly detection because `GROUP BY` never returns empty buckets; time series
  are now completed with zeros for additive metrics (and never extended beyond the data's real range).

Each now has a regression test. Lesson: an end-to-end run on the real topology is a test suite of its own.

## Making it fast where it can be

Almost all latency is LLM generation. Two changes cut it where safe:

- **Fast path.** Simple whole-table statistics ("What is the average revenue?") are answered from the profile
  computed at upload, with a template answer that still passes the verifier: zero model calls.
- **Context, not queries.** Every column's profile (counts, missing share, sum, mean, median, spread, range,
  distinct values) is in the planner's context, so it does not spend steps rediscovering basics.

Streaming the answer token by token was deliberately not done: answers are verified before display, and streaming
unverified text would undo the main guarantee.

## Safety

- SQL is validated on the parsed AST (single SELECT-family statement, no DML/DDL anywhere in the tree, no file or
  system functions, catalog and allowlist checks, PII columns count-only), then executed in read-only sessions.
- Generated Python runs only in ephemeral sandboxes (Docker with no network, read-only filesystem, non-root, no
  capabilities, CPU/memory/time limits; or Modal sandboxes on hosts without Docker). Tests run hostile code with the
  static checker bypassed and assert the container still holds.
- Dataset text is fenced as untrusted data; instruction-like cells are flagged; the model has no tool that can reach
  configuration or secrets.

## Results

67 cases on five datasets (one of them the real, multi-table Chinook database), two full runs with a local
Qwen3 8B model on a laptop:

- **93.3% of cases passed** (92.5% and 94.0%). Numerical accuracy 93.9% and entity accuracy 92.6%, identical in both
  runs.
- **0% of numbers in final answers lacked evidence** in either run, while 1.8% to 2.9% of the numbers the model
  drafted did. That gap is the verifier's job, and it is the property the design set out to guarantee.
- **0 unsafe SQL statements executed**; all five safety cases (destructive SQL, prompt injection in the data,
  environment-variable exfiltration) passed in both runs.
- Simple statistics answered by the fast path took 0.1 s with zero model calls. Everything else took a median of
  78 s, almost all of it local LLM generation.

The remaining failures are listed one by one in the [README](../README.md#evaluation-results). Two are model
judgment calls the benchmark scores strictly (a last name instead of a full name, an overview instead of a
clarifying question), one is a disagreement about a definition (gross profit with missing costs), one was a real bug
fixed after the runs (NaN in a stored result), and two point at the next tool improvements: ratio metrics, and
grouping by a column reached through a relationship.

### What the benchmark changed

Running it found five real defects that unit tests had not: plans dropping a period the question named, the
verifier accepting an all-years number for a one-year sentence, rankings with a monthly breakdown picking the best
month instead of the best total, count questions failing when the model omitted the metric, and profile findings
that hid the very count the question asked for. Each became a regression test.

It also found a measurement trap: on a laptop, idle sleep froze local inference mid-request. Analyses that took two
minutes of compute took fifty of wall-clock time, timed out and retried. Interrupted runs were discarded (they are
kept in the database as cancelled, with the reason) and repeated with the machine kept awake; one more restart made
sure every final run used the same code.

### Three models, one guarantee

| Metric | analystos-qwen3-8b (2 runs) | analystos-qwen3-4b-instruct (1 run) | analystos-llama3.1-8b (1 run) |
|---|---|---|---|
| Overall pass rate | **93.3% (92.5% to 94.0%)** | 88.1% | 67.2% |
| Numerical accuracy | **93.9%** | 81.8% | 63.6% |
| Entity accuracy | **92.6%** | **92.6%** | 66.7% |
| Computation accuracy | **92.4% (91.5% to 93.2%)** | 84.8% | 67.8% |
| Unsupported numbers in drafts | **2.4% (1.8% to 2.9%)** | 8.6% | 12.8% |
| Unsupported numbers in final answers | **0.0%** | **0.0%** | **0.0%** |
| First-pass step success | **87.6% (85.0% to 90.3%)** | 83.4% | 72.4% |
| Retry recovery | **91.7% (83.3% to 100.0%)** | 55.9% | 66.7% |
| Safety cases passed | **100.0%** | **100.0%** | **100.0%** |
| Latency p50 | 78.1s (75.4s to 80.9s) | **26.9s** | 30.7s |
| Latency p95 | 285.6s (235.7s to 335.4s) | **75.6s** | 95.0s |
| LLM calls per task | **2.73 (2.52 to 2.93)** | 3.37 | 3.52 |
| Cost per task | **$0.0000** | **$0.0000** | **$0.0000** |

What it shows: **model quality moves pass rate, not trustworthiness.** Llama 3.1 8B drafted five times more
unsupported numbers than Qwen3 8B (12.8% vs 2.4%) and passed far fewer cases, yet 0% of the numbers in its final
answers lacked evidence, and it executed no unsafe SQL. A weaker model makes AnalystOS answer less, not answer
wrongly. The small Qwen3 4B is three times faster than the 8B and loses about five points of pass rate, mostly on
numeric and multi-table questions.

## What I would do next

- Evaluate hosted models next to the local ones (the tooling exists: `evals.run --model ... --base-url ...` and
  `evals.compare`).
- Ratio metrics and group-by columns reached through relationships in the aggregate tools, the gaps behind most
  remaining benchmark failures.
- Add a semantic check that each sentence's wording matches the finding it cites, beyond numbers, entities and
  periods.
- Learn plan templates from successful analyses to reduce planning calls further.
