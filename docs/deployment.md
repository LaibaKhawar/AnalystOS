# Deployment

## Local, one command

```bash
cp .env.example .env
# set SECRET_KEY and ENCRYPTION_KEY (commands are in the file), then choose an LLM endpoint
docker compose up --build
```

- App: http://localhost:3000 (demo login `demo@analystos.dev` / `analystos-demo-2026`, created by the `migrate`
  service together with the sample datasets)
- API + docs: http://localhost:8000/docs, metrics: http://localhost:8000/metrics

Services: `postgres` (pgvector), `redis`, `sandbox` (builds the sandbox image and exits), `migrate` (Alembic +
demo seed, exits), `backend` (FastAPI), `worker` (Celery; starts sandbox containers through the Docker socket),
`frontend` (nginx serving the built app and proxying `/api`, SSE-safe buffering disabled).

### LLM options

| Option | Settings |
|---|---|
| Ollama on the host (default) | `LLM_BASE_URL=http://host.docker.internal:11434/v1`, `LLM_MODEL=analystos-qwen3-14b` (create it with `ollama create analystos-qwen3-14b -f ollama/Modelfile.qwen3-14b`, which raises the context window to 16K tokens) |
| OpenAI | `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_MODEL=gpt-4o-mini`, `LLM_API_KEY=sk-...` |
| Azure OpenAI | `LLM_PROVIDER=azure_openai`, `LLM_BASE_URL=https://<resource>.openai.azure.com`, `LLM_MODEL=<deployment>`, `LLM_API_KEY=...` |
| vLLM / LM Studio / OpenRouter | any OpenAI-compatible `/v1` endpoint |

Important for Ollama: the default context window is small (4K tokens). The planner prompt (tool catalog +
schema) is larger, and Ollama silently truncates it. Use the provided Modelfiles (`num_ctx 16384`) or set
`OLLAMA_CONTEXT_LENGTH`.

Costs are estimated from `app/agent/llm/pricing.py`; override or add models with `PRICING_FILE` (YAML:
`model: {input: <usd per 1M>, output: <usd per 1M>}`).

## Monitoring stack

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up --build
```

Grafana http://localhost:3001 (provisioned "AnalystOS" dashboard: analysis latency, tool outcomes, retries, LLM
tokens and latency by purpose, SQL duration, sandbox outcomes, claim verification), Prometheus
http://localhost:9090, Jaeger http://localhost:16686 (one trace per analysis). The worker serves its metrics on
port 9100.

## Hosts without Docker (Render, Fly, Railway)

Platform hosts do not give containers a Docker daemon, so set `SANDBOX_BACKEND=modal` (with `MODAL_TOKEN_ID` and
`MODAL_TOKEN_SECRET`) to run generated Python in Modal sandboxes, and point `LLM_BASE_URL` at a hosted model or the
Modal GPU deployment (`deploy/modal/llm_server.py`). For a single-service demo, `RUN_ANALYSES_INLINE=true` runs
analyses in the API process instead of a separate worker.

## Production checklist

- Set `ENVIRONMENT=production` (startup refuses short or default `SECRET_KEY`).
- Put the API behind TLS; restrict `CORS_ORIGINS`.
- Give external database connections a read-only role in addition to AnalystOS's read-only sessions.
- Replace the Docker socket mount with a rootless daemon, a dedicated sandbox host, or a gVisor/Kata runtime
  for sandbox containers (see [security](security.md)).
- Scale `worker` replicas for concurrent analyses; the API is stateless and can be replicated.
- Persist the `appdata` volume (dataset files and Python artifacts) or move it to network storage.
- Scrape `/metrics` with Prometheus; ship JSON logs (`LOG_JSON=true`) to your log platform.
- Back up PostgreSQL (metadata, provenance, evaluation history).
