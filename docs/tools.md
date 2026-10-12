# Tool interfaces

Every tool has a pydantic input model (validated before execution), returns a `ToolResult`
(`summary` for the model, `data`, optional `result_table_id`, `findings`, `chart_ids`, `notable`), and every call is
logged as a `ToolExecution` with timing, status, error kind and retry lineage. Errors are classified; only
recoverable kinds are retried.

| Tool | Inputs (abridged) | Output |
|---|---|---|
| `list_tables` | none | tables with row/column counts |
| `describe_table` | `table?` | columns, types, roles, semantic meaning with confidence |
| `inspect_schema` | none | semantic schema (metrics, dimensions, time, identifiers) |
| `profile_dataset` | `table?`, `columns[]` | precomputed row count, duplicates, and per-column non-null count, missing %, sum, mean, median, std, min, max, distinct and top values as findings (estimates when the profile is sample-based) |
| `compute_metric` | `name`, `group_by[]`, `time_grain?`, `period?`, `filters[]` | a saved metric definition evaluated exactly (definition filters always applied) |
| `aggregate_metric` | `metric {column, agg}`, `group_by[]`, `time_grain?`, `period?`, `filters[]`, `order`, `limit` | totals, rankings (with shares) or time series (with period-over-period % change); empty periods filled |
| `compare_periods` | `metric`, `current_period`, `previous_period`, `dimension?`, `filters[]` | previous, current, change, % change; per segment with contribution to total change |
| `analyze_segments` | `metric`, `dimension`, `period?`, `filters[]`, `top_n` | value, share, rank, row count, average per row, concentration |
| `compute_statistics` | `column`, `group_by?`, `period?` | count, mean, median, std, variance, quantiles, 95% CI; Welch t-test and Mann-Whitney for two groups |
| `calculate_correlation` | `columns[2..8]`, `method`, `aggregate_by?` | pairwise coefficient, p-value, n (association only) |
| `detect_anomalies` | `metric`, `time_grain?`, `dimension?`, `method` (auto/zscore/iqr/rolling/isolation_forest), `threshold`, `period?` | anomalies with observed, baseline, deviation %, method, severity, direction |
| `identify_drivers` | `metric` (sum/count), `current_period`, `previous_period`, `dimensions[]`, `quantity_column?` | per-dimension contributions, concentration ranking, volume vs price decomposition |
| `execute_sql` | `sql`, `purpose` | validated read-only query result (capped) |
| `execute_python` | `code`, `tables[]`, `results[]` | sandboxed pandas result (table, dict or value) and PNG charts |
| `create_chart` | `result_id` (or `$step`), `chart_type`, `x`, `y[]`, `series?`, `title`, `interpretation?` | chart spec + data from a stored result, hashed |
| `retrieve_evidence` | `labels[]` | recorded findings |
| `retrieve_previous_analysis` | `query` | earlier analysis summaries (pgvector, keyword fallback) |
| `generate_report` | `title?` | flags the analysis for report generation after verification |

Error kinds treated as recoverable: `invalid_arguments`, `unknown_column`, `unknown_table`, `syntax`, `type_error`,
`execution_error`, `python_error`, `missing_result`, `empty_result`, `unknown_result`, `bad_period`,
`invalid_chart`, `statement_type`, `forbidden_operation`, `forbidden_function`, `restricted_column`, `static_check`.

Findings are the provenance primitive: `{label: "F7", kind, statement, values, formula, entities, periods}`, linked
to the tool execution and result table (and through them to the SQL or Python that produced them).
