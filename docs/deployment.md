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
analyses in the API process instead of a separate worker. Build the backend image with
`--build-arg INSTALL_MODAL=true` so the Modal client is included.

### Render (blueprint)

[`render.yaml`](../render.yaml) describes a free-tier demo: Postgres, Key Value (Redis), the API (migrations and the
demo seed run at start, analyses inline, Modal sandboxes) and the frontend. In Render: **New > Blueprint**, pick the
repository, then fill the values marked `sync: false`:

| Service | Variable | Value |
|---|---|---|
| analystos-api | `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| analystos-api | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | from `modal token new` (or `~/.modal.toml`) |
| analystos-api | `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | any OpenAI-compatible endpoint |
| analystos-web | `BACKEND_URL` | the API's public URL, e.g. `https://analystos-api.onrender.com` |

The demo account is seeded with the `analyst` role (its password is public, so it must not be an admin).
`QUESTIONS_PER_HOUR=20` bounds the LLM bill per account. Free-plan limits: the API sleeps when idle, its disk is
ephemeral (visitor uploads vanish on restart; the demo datasets are re-seeded), and schedules need the paid `worker`
and `beat` background services (same image, commands as in `docker-compose.yml`).

### Free live deployment (Modal + Vercel)

The [live app](https://analystos-six.vercel.app) follows Modal's
[Qwen chatbot with Vercel](https://modal.com/blog/deploy-qwen-chatbot-vercel) architecture: an OpenAI-compatible
Qwen3 endpoint on Modal and a frontend on Vercel. Modal only allows GPUs on workspaces with a payment method, so this
setup uses CPU containers, which run on the free monthly credits:

| Piece | Where | File |
|---|---|---|
| Qwen3-4B-Instruct-2507 (Q4 GGUF), llama.cpp server, OpenAI-compatible `/v1`, API key required | Modal CPU (16 vCPU), scales to zero | `deploy/modal/llm_cpu.py` |
| API + Postgres 16 (pgvector) + Redis in one container; analyses inline; Python in Modal Sandboxes | Modal CPU (4 vCPU), scales to zero | `deploy/modal/app_server.py` |
| React app; `/api` rewritten to the Modal backend (same origin, no CORS) | Vercel Hobby | `frontend/vercel.json` |

```bash
pip install modal && modal token new
# model server
modal secret create analystos-llm LLM_API_KEY=<random key>
modal run deploy/modal/llm_cpu.py::download && modal deploy deploy/modal/llm_cpu.py
# backend (SECRET_KEY: random hex, ENCRYPTION_KEY: a Fernet key, LLM_API_KEY: the key above)
modal secret create analystos-app SECRET_KEY=... ENCRYPTION_KEY=... LLM_API_KEY=<same key>
modal deploy deploy/modal/app_server.py
# frontend: set the rewrite destination in frontend/vercel.json to the backend URL Modal printed, then
cd frontend && npx vercel deploy --prod
```

Measured on this setup: the llama.cpp server generates about 27 tokens/s on 16 vCPUs; a 5-case benchmark subset
passed 5/5 at about a minute per question; the Playwright end-to-end test (register, upload, profile, ask, evidence,
report) passes against the public URL. The database is dumped to a Modal Volume every five minutes and when the
container stops, and restored on start (verified by stopping the container and finding the data on the next one).
Trade-offs: cold starts (about 20 s for the backend, longer for the model), CPU latency, one backend container, and
scheduled analyses only run while the container is awake. With a payment method, `deploy/modal/llm_server.py` serves
Qwen3-8B on a GPU (vLLM) instead.

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
