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

Platform hosts do not give containers a Docker daemon. Either run generated Python in Modal sandboxes
(`SANDBOX_BACKEND=modal` with `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`; build the backend image with
`--build-arg INSTALL_MODAL=true`) or switch the Python tool off (`SANDBOX_ENABLED=false`). For a single-service
deployment, `RUN_ANALYSES_INLINE=true` runs analyses in the API process instead of a separate worker.

### Free live deployment (Vercel + Render + Groq)

The [live app](https://analystos-six.vercel.app) runs on three free tiers that need no payment card:

| Piece | Where | File |
|---|---|---|
| React app; `/api` rewritten to the backend (same origin, no CORS); deploys on every push that changes `frontend/` | Vercel Hobby | `frontend/vercel.json` |
| API with PostgreSQL 16 (pgvector) and Redis in the same container; analyses inline | Render free web service (512 MB) | `deploy/render/Dockerfile`, [`render.yaml`](../render.yaml) |
| Qwen 3.8 27B through an OpenAI-compatible API | Groq free tier | `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` |

Setup: create the backend from `render.yaml` (Render: **New > Blueprint**) and fill `ENCRYPTION_KEY` (a Fernet key)
and `LLM_API_KEY` (a Groq key); point the rewrite in `frontend/vercel.json` at the Render URL; import the repository
in Vercel with `frontend` as the root directory.

What the free tiers imply, all measured:

- **Memory.** Render's free instance has 512 MB; the container idles at about 310 MB and peaked at about 420 MB
  during an analysis plus a PDF report.
- **Ephemeral data.** The service sleeps after 15 idle minutes and its disk does not survive that: each start
  re-creates the database with the demo account and sample datasets (a separate free Render database would expire
  after 30 days, and only one is allowed per workspace). The first request after a sleep waits for the start.
- **Model rate limits.** Groq's free tier allows about 8,000 tokens per minute per model. The client waits out 429
  responses as the provider asks, so a question takes one to two minutes; a request larger than the per-request
  limit (a very wide multi-table schema) is refused with a clear message.
- **No Python sandbox.** Render has no Docker daemon or isolation layer, so the Python tool is switched off
  (`SANDBOX_ENABLED=false`) and never offered to the planner; SQL, statistics, anomaly detection, charts,
  verification and reports all work.
- **Schedules** run only while the service is awake.

### Modal deployment (needs a payment method)

`deploy/modal/llm_cpu.py` (Qwen3-4B on CPU with llama.cpp), `deploy/modal/llm_server.py` (Qwen3-8B on a GPU with
vLLM) and `deploy/modal/app_server.py` (the API with Postgres and Redis, data dumped to a Volume) follow Modal's
[Qwen chatbot with Vercel](https://modal.com/blog/deploy-qwen-chatbot-vercel) architecture. They ran the live app
until Modal disabled the workspace: without a payment method a workspace gets only about $1 of usage. Measured while
it ran: 27 tokens/s on 16 vCPUs, a 5-case benchmark subset passed 5/5, the Playwright end-to-end test passed against
the public URL, and the database survived a forced container restart. With a card on the account, the $30 monthly
credits cover a scale-to-zero demo.

### Free static demo (GitHub Pages)

The [live demo](https://laibakhawar.github.io/AnalystOS/) costs nothing to host: it is the frontend built in replay
mode (`npm run build:replay`), serving API responses recorded from a running stack instead of calling a backend.

```bash
node frontend/scripts/showcase.mjs        # ask the showcase questions through the real API and model
node frontend/scripts/record-replay.mjs   # browse the app as the demo user, save frontend/public/replay.json
git push                                  # .github/workflows/pages.yml builds and publishes it
```

Every answer, chart, claim and evidence item in the replay was produced by the backend and model at recording time.
Writes (asking, uploading, sharing) are refused with a message, and views that were not recorded say so.

### Frontend behind any backend

The frontend image renders its nginx config from a template at start: `BACKEND_URL` (default
`http://backend:8000`, the Compose service) is where `/api` is proxied, over HTTP or HTTPS, and the DNS resolver is
read from the container's `/etc/resolv.conf` (override with `NGINX_RESOLVER`).

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
