# Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Analysis stays "queued", later fails with "no worker picked it up" | The worker is not running or cannot reach Redis. Start it (`make worker` or the `worker` service). Stale jobs are failed automatically after `AGENT_JOB_TIMEOUT_SECONDS` + 2 minutes so they can be retried. |
| Celery on macOS: `ValueError: not enough values to unpack (expected 3, got 0)` | A known prefork issue on macOS. Use `--pool=threads` (the Makefile does). Linux containers are unaffected. |
| "The language model could not complete the analysis" | The LLM endpoint is unreachable or returned invalid JSON three times. Check `/api/system/status`, `LLM_BASE_URL`, `LLM_MODEL` and the API key. |
| The agent invents column or table names with Ollama | The prompt was truncated by Ollama's default 4K context. Use the `analystos-qwen3-*` models from `ollama/` (16K context). |
| Python steps fail with "sandbox is unavailable" | Docker is not reachable from the worker or the image is missing. Run `docker build -t analystos-sandbox:latest sandbox` and check the worker can access the Docker socket. |
| PDF export returns an error locally | WeasyPrint needs pango system libraries. They are included in the Docker image; on macOS run `brew install pango`. HTML export always works. |
| "Unsupported file type" | Only `.csv`, `.tsv`, `.txt` and `.xlsx` are accepted. Save legacy `.xls` files as `.xlsx`. |
| CSV columns typed as text | Values are coerced to numbers/dates only when at least 97% of non-empty values parse, to avoid corrupting free text. Clean the column or override its semantic type in the explorer. |
| Dates interpreted with the wrong day/month order | Ambiguous formats produce an ingestion warning naming the format used. Re-export dates as ISO `YYYY-MM-DD`. |
| SQLite connection rejected | SQLite files must be placed under `DATA_DIR/sqlite`; paths outside it are refused. |
| A number I expected is missing from the answer | The verifier removed it because no computed finding supports it. Open "Removed claims" in the evidence panel (`include_removed=true`) to see what was dropped and why. |
| Tests fail with connection errors | Start the test database: `make dev-db` (PostgreSQL on port 5434 with database `analystos_test`), or set `TEST_DATABASE_URL`. Docker tests are skipped when the sandbox image is not built. |
