# Security design

AnalystOS executes model-generated SQL and Python against user data, so the design assumes the model can be
wrong or manipulated (for example by text inside a dataset). Every layer below is enforced in code and covered
by tests.

## SQL safety

Validation is AST-based (`sqlglot`), never regex-based (`backend/app/services/sql/validator.py`).

| Check | Behaviour |
|---|---|
| Statement count | Exactly one statement; `SELECT 1; DROP TABLE x` is rejected |
| Root type | Only `SELECT` and set operations of selects (`UNION`, `INTERSECT`, `EXCEPT`), with CTEs |
| Forbidden nodes anywhere in the tree | INSERT, UPDATE, DELETE, MERGE, CREATE, DROP, ALTER, TRUNCATE, GRANT, REVOKE, COPY, CALL/commands, PRAGMA, ATTACH, SET, INSTALL/LOAD, `SELECT ... INTO`, `FOR UPDATE` locks, transactions. This also catches DML inside CTEs |
| Forbidden functions | File access (`read_csv`, `read_parquet`, `pg_read_file`, `load_file`...), sleep/benchmark, settings (`current_setting`, `set_config`, `getenv`), remote access (`dblink`, `http*`), process control. Table functions and literal file paths in `FROM` are rejected |
| Catalog | Every table must exist in the data source's catalog and be on its allowlist; every column must resolve (misspellings get suggestions) |
| PII | Columns flagged as PII (automatically or by the user) may only appear inside `COUNT`; `SELECT *` is checked after star expansion |
| Complexity | Max joins, max subquery depth, max AST size |
| Rows | A `LIMIT` of `SQL_MAX_ROWS + 1` is enforced to detect truncation |

Execution-side defences (defence in depth):

- **Uploaded datasets**: DuckDB file opened `read_only`, `enable_external_access=false`,
  `lock_configuration=true`, memory and thread limits, timeout via interrupt.
- **PostgreSQL**: `default_transaction_read_only=on`, `SET TRANSACTION READ ONLY`, `statement_timeout`;
  the transaction is always rolled back. Use a read-only database role as well.
- **MySQL**: `SET SESSION TRANSACTION READ ONLY`, `max_execution_time`, rollback.
- **SQLite**: opened with `mode=ro`; files must live under `DATA_DIR/sqlite` (path traversal is rejected);
  a progress handler enforces the timeout.

Every statement, including blocked ones, is stored in `sql_executions` with its validation result.

## Python sandbox

`backend/app/services/sandbox/docker_runner.py` and `sandbox/`.

| Control | Setting |
|---|---|
| Isolation | New container and new volume per execution; both destroyed afterwards |
| Network | `network_mode=none` (no internet, no cloud metadata endpoint) |
| User | uid/gid 65534 (nobody) |
| Filesystem | read-only root filesystem; `/tmp` is a 64 MB `noexec,nosuid,nodev` tmpfs; inputs are root-owned and mode 0444; only `/work/out` is writable |
| Privileges | all Linux capabilities dropped, `no-new-privileges`, private IPC |
| Resources | 1 CPU, 512 MB memory with swap disabled, 128 PIDs, 30 s wall clock (killed from the host) |
| Secrets | empty environment; no host mounts, no source tree, no Docker socket |
| Outputs | `result.json` and PNG charts copied out with size caps |

Before a container is started, a static AST check rejects imports outside an allowlist (pandas, numpy, scipy,
sklearn, statsmodels, matplotlib and standard numeric modules), `eval`/`exec`/`open`/`__import__`/`getattr`,
dunder access, and file or network methods (`read_csv`, `to_csv`, `savefig`, `urlopen`...). The static check is
a convenience; the container is the security boundary. Tests run hostile code with the static check bypassed
and assert: no canary secret in the environment, no network, no Docker socket, no host paths, read-only inputs
and root filesystem, uid 65534, fork bombs contained, timeouts and OOM enforced, no leftover containers.

**Known trade-off.** The worker needs the Docker API to start sandboxes, so in Docker Compose it mounts the
Docker socket. Generated code never runs in the worker. For production, run sandboxes through a rootless
Docker daemon, a dedicated sandbox host, or gVisor/Firecracker (`runsc` runtime) instead of the host socket.

## Prompt injection

- Dataset content reaches the model only inside `<data>...</data>` blocks and every system prompt states that
  such content is untrusted data that must never be followed.
- Cell values are truncated and control characters stripped; PII values are never sent.
- The profiler flags instruction-like text (`ignore previous instructions`, `reveal ... environment`, fake
  role tags) and the flag is shown both to the model and in the UI.
- The model has no tool that can read configuration, environment variables or files, so an injected
  instruction has nothing to call. Reports are served with a restrictive Content Security Policy and rendered
  in a sandboxed iframe in the UI.
- CSV/Excel exports neutralise spreadsheet formula injection (`=`, `+`, `-`, `@` prefixes).

## Secrets and credentials

- Required secrets (`SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`) are validated at startup; production refuses
  short or default keys.
- Database passwords are encrypted with Fernet before storage and are never returned by the API
  (`has_password` only). Driver error messages are trimmed so they cannot echo connection strings.
- Logs redact keys containing password, secret, token, api_key or authorization.
- `.env` files are git-ignored; CI runs gitleaks.

## Access control

All resources are scoped to the authenticated user; other users' ids return 404. JWTs are HS256 with expiry.
