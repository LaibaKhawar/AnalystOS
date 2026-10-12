# API reference

The interactive OpenAPI documentation is served at `http://localhost:8000/docs` (Swagger UI) and
`/redoc`. A snapshot of the schema is committed as [`openapi.json`](openapi.json).

Authentication: `POST /api/auth/register` or `/api/auth/login` returns `{access_token, user}`; send
`Authorization: Bearer <token>` on every other call. Errors always have the shape
`{"error": {"code": "...", "message": "safe, human readable", "details": {...}}}`.

## Typical flow

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"demo@analystos.dev","password":"analystos-demo-2026"}' | jq -r .access_token)
SRC=$(curl -s -X POST localhost:8000/api/sources/upload -H "Authorization: Bearer $TOKEN" \
  -F file=@backend/evals/data/sales.csv | jq -r .id)
CNV=$(curl -s -X POST localhost:8000/api/conversations -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d "{\"data_source_id\":\"$SRC\"}" | jq -r .id)
ANA=$(curl -s -X POST localhost:8000/api/conversations/$CNV/ask -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"question":"Which region declined most in Q3 2026?"}' | jq -r .id)
curl -N localhost:8000/api/analyses/$ANA/stream -H "Authorization: Bearer $TOKEN"   # SSE progress
curl -s localhost:8000/api/analyses/$ANA/claims -H "Authorization: Bearer $TOKEN"   # verified claims + evidence
```

The progress stream emits `progress` events (`{id, type, message, payload, created_at}`; types: `status`, `plan`,
`step_started`, `step_completed`, `step_failed`, `step_skipped`, `retry`, `replan`, `verification`, `completed`,
`failed`, `cancelled`, `clarification`) and a final `end` event. Reconnect with `?after=<last id>`.

## Endpoints

| Area | Method | Path | Summary |
|---|---|---|---|
| analyses | GET | `/api/analyses` | Recent |
| analyses | GET | `/api/analyses/{analysis_id}` | Get Analysis |
| analyses | GET | `/api/analyses/{analysis_id}/artifacts/{python_id}/{file_name}` | Artifact |
| analyses | GET | `/api/analyses/{analysis_id}/charts` | Charts |
| analyses | GET | `/api/analyses/{analysis_id}/claims` | Claims |
| analyses | GET | `/api/analyses/{analysis_id}/claims/{claim_id}/evidence` | Claim Evidence |
| analyses | GET | `/api/analyses/{analysis_id}/events` | Events |
| analyses | GET | `/api/analyses/{analysis_id}/executions` | Executions |
| analyses | GET | `/api/analyses/{analysis_id}/executions/{execution_id}` | Execution Detail |
| analyses | GET | `/api/analyses/{analysis_id}/findings` | Findings |
| analyses | GET | `/api/analyses/{analysis_id}/results/{result_id}.csv` | Result Download |
| analyses | GET | `/api/analyses/{analysis_id}/stream` | Stream |
| analyses | POST | `/api/analyses/{analysis_id}/cancel` | Cancel |
| analyses | POST | `/api/analyses/{analysis_id}/retry` | Retry |
| auth | GET | `/api/auth/me` | Me |
| auth | POST | `/api/auth/login` | Login |
| auth | POST | `/api/auth/register` | Register |
| conversations | DELETE | `/api/conversations/{conversation_id}` | Delete Conversation |
| conversations | GET | `/api/conversations` | List Conversations |
| conversations | GET | `/api/conversations/{conversation_id}` | Get Conversation |
| conversations | GET | `/api/conversations/{conversation_id}/analyses` | Analyses |
| conversations | GET | `/api/conversations/{conversation_id}/messages` | Messages |
| conversations | POST | `/api/conversations` | Create Conversation |
| conversations | POST | `/api/conversations/{conversation_id}/ask` | Ask |
| conversations | POST | `/api/conversations/{conversation_id}/reset-context` | Reset Context |
| data sources | DELETE | `/api/sources/{source_id}` | Delete Source |
| data sources | GET | `/api/sources` | List Sources |
| data sources | GET | `/api/sources/{source_id}` | Get Source |
| data sources | GET | `/api/sources/{source_id}/tables` | Tables |
| data sources | GET | `/api/sources/{source_id}/tables/{table_id}/columns.csv` | Schema Csv |
| data sources | GET | `/api/sources/{source_id}/tables/{table_id}/preview` | Preview |
| data sources | PATCH | `/api/sources/{source_id}/columns/{column_id}` | Patch Column |
| data sources | POST | `/api/sources/connections` | Create Connection |
| data sources | POST | `/api/sources/upload` | Upload |
| data sources | POST | `/api/sources/{source_id}/refresh` | Refresh Connection |
| evaluations | GET | `/api/evaluations` | Runs |
| evaluations | GET | `/api/evaluations/{run_id}` | Run Detail |
| reports | GET | `/api/reports` | List Reports |
| reports | GET | `/api/reports/{report_id}` | Get Report |
| reports | GET | `/api/reports/{report_id}/html` | Report Html |
| reports | GET | `/api/reports/{report_id}/pdf` | Report Pdf |
| reports | GET | `/api/reports/{report_id}/results.xlsx` | Report Results |
| reports | POST | `/api/analyses/{analysis_id}/report` | Create Report |
| system | GET | `/api/dashboard` | Dashboard |
| system | GET | `/api/health` | Health |
| system | GET | `/api/system/status` | Status |
Prometheus metrics are exposed at `GET /metrics`.
