# AnalystOS frontend

The web app for **AnalystOS**, the analyst that shows its work. Users upload CSV/XLSX files or connect PostgreSQL, MySQL or SQLite, ask business questions, watch the agent plan and execute, and get answers where every number is verified and traceable to the SQL or Python that produced it.

Stack: Vite, React 19, TypeScript (strict), React Router, TanStack Query, Tailwind CSS v4, shadcn/ui (radix base), Recharts, Phosphor icons, `motion`, Vitest + React Testing Library, Playwright.

## Setup

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173, proxies /api to http://127.0.0.1:8000
```

The backend (API, worker and LLM) must be running on port 8000. Override the proxy target with `VITE_API_PROXY=http://host:port npm run dev`. In production the app calls `/api` on its own origin (override at build time with `VITE_API_BASE`).

## Scripts

| Script              | What it does                                                                |
| ------------------- | --------------------------------------------------------------------------- |
| `npm run dev`       | Vite dev server on port 5173 with the `/api` proxy                          |
| `npm run build`     | Type-check (project references) and build to `dist/`                        |
| `npm run preview`   | Serve the built app on port 4173 (same proxy)                               |
| `npm run lint`      | ESLint (typescript-eslint, react-hooks, react-refresh)                      |
| `npm run typecheck` | `tsc --noEmit` for app and node configs                                     |
| `npm run test`      | Vitest unit and component tests (jsdom)                                     |
| `npm run format`    | Prettier (with the Tailwind class sorter)                                   |
| `npm run e2e`       | Playwright end-to-end specs against a running dev server and backend        |
| `npm run e2e:ci`    | Deterministic end-to-end run: starts the API with a rule-based LLM and Vite |

### End-to-end tests

`npm run e2e:ci` is the deterministic mode used in CI: Playwright starts the real API with a rule-based LLM stand-in (`backend/tests/e2e_server.py`, port 8001, fresh database on every run) and Vite on port 5174. Both specs run in it.

`e2e/collaboration.spec.ts` registers two users in separate browser contexts. User A uploads `sales.csv`, creates a saved metric (after checking that the API's "A metric must aggregate" message appears inline), and shares the dataset with user B as a viewer. B sees it with a "Shared with you, Read only" badge, no ask action and no owner actions. A changes B's share to analyst in the share dialog; B can then ask a question and gets a completed answer with verified statements. A creates a schedule (the https-only webhook check is exercised), runs it now, sees the last run linked and opens that analysis. The last step checks the Users page: it is visible only when A is the first account (and so the admin), which is the case when the spec runs alone.

`e2e/analysis.spec.ts` registers a new user, uploads `../backend/evals/data/sales.csv`, checks profiling in the dataset explorer, asks "Which region had the highest revenue in 2026?", follows live progress, waits for the verified answer, checks the chart (if the planner answered with a single-row result and no chart, it asks a follow-up chart request in the same conversation and records a test annotation), opens the evidence drawer for a verified claim (SQL visible), generates a report and downloads the HTML.

```bash
npx playwright install chromium
npm run dev &                         # and the backend with its worker
npm run e2e                           # E2E_BASE_URL=http://host:port to target another server
```

Timeouts are generous because analyses run on a shared local LLM. The analysis gets 12 minutes once it starts (`E2E_ANALYSIS_TIMEOUT_MS`), queue wait gets 10 minutes (`E2E_QUEUE_TIMEOUT_MS`), and the whole test 30 minutes (`E2E_TEST_TIMEOUT_MS`). If an evaluation run is using the worker at the same time, raise the queue timeout.

## Docker

```bash
docker build -t analystos-frontend .
docker run -p 8080:80 --network <compose-network> analystos-frontend
```

Multi-stage: Node builds `dist/`, nginx serves it. `nginx.conf` proxies `/api/` to `http://backend:8000` with SSE-friendly settings (`proxy_buffering off`, `proxy_read_timeout 3600s`), raises the upload limit to 210 MB, caches hashed assets and falls back to `index.html` for client routes.

## Deployment

The live app (https://analystos-six.vercel.app) is the Vercel project `analystos`, connected to this repository with
`frontend` as its root directory. Every push to `main` that changes `frontend/` deploys to production automatically;
pushes that only touch the backend or docs skip the build. `/api` is rewritten to the Render backend in `vercel.json`.
Pull requests get preview deployments.

## Structure

```
src/
  api/            types.ts (every response type), client.ts (fetch, errors, access and refresh tokens with
                  single-flight refresh, upload progress), endpoints.ts (typed functions),
                  sse.ts (SSE parser + follow with reconnect, fresh tokens and polling fallback)
  hooks/queries/  TanStack Query hooks per resource with cache invalidation (sources and shares, metrics,
                  schedules, alerts, admin users, analyses, reports, evaluations)
  hooks/          useAnalysisStream (live progress), usePermissions (role and per-source abilities), useElementWidth
  providers/      Auth (tokens in localStorage, refresh on 401, logout revokes the refresh token) and Theme
  lib/            format, claims grouping, chart selection and export, upload validation, eval metrics,
                  permissions, metric and schedule forms, scope check summary, compare-runs best values
  components/
    analysis/     thread turn, running view, answer, claims, evidence drawer, cost line, activity feed
    inspector/    plan, evidence (findings) and execution history panels, execution detail sheet
    charts/       Recharts renderers, SVG box plot and heatmap, chart card with SVG and PNG export
    explorer/     schema grid with column editor, preview, profiling, semantic summary, relationships (join keys)
    metrics/      saved metric list and create/edit form
    sources/      access badges, share dialog, delete confirmation
    schedules/    schedule card (run now, pause, last analysis) and create/edit form
    alerts/       bell with unread count and panel, alert item
    evaluations/  cases table, charts, compare table
    workspace/    source tree, active context chips, conversation list, ask box
    layout/       app shell, nav, command palette (Cmd K), user menu, theme toggle
    watermelon/   customized Watermelon UI components (see below)
    ui/           shadcn/ui primitives plus customized Watermelon components installed into ui/
  pages/          one file per route
```

Routes: `/welcome` (public landing), `/login`, `/register`, `/` (dashboard), `/datasets`, `/connections`, `/sources/:id` (explorer), `/workspace/:conversationId`, `/workspace/by-analysis/:analysisId`, `/schedules`, `/alerts`, `/reports`, `/reports/:id`, `/evaluations`, `/evaluations/compare?runs=a,b`, `/evaluations/:runId`, `/admin/users` (admins).

## Collaboration, roles and automation

- **Sessions.** Login and registration return an access token (30 minutes) and a refresh token; both are stored. Any 401 triggers one `POST /api/auth/refresh` shared by every request that failed at the same time (the server rotates refresh tokens and treats reuse as theft), stores the new pair and retries. If the refresh fails, both tokens are cleared and the app returns to `/login`. Uploads re-send after a refresh, and the progress stream renews a token that is about to expire before reconnecting. Sign out calls `POST /api/auth/logout` with the refresh token, then clears it.
- **Roles.** `admin`, `analyst` or `viewer` (from `/api/auth/me`). Viewers do not see upload, connect, ask or schedule controls; each place says why instead. `403 forbidden` errors are titled "You do not have permission" without a retry button, and `429 rate_limited` errors say how long to wait (`details.retry_after_seconds`).
- **Sharing.** Shared sources carry a "Shared with you" badge and the access level (`Can ask` or `Read only`). Owners get a Share dialog in the explorer to add people by email as viewer or analyst, change their access or remove it. Delete, refresh, column edits, metric edits and sharing are only shown with `manage` access; "Ask a question" is hidden with `read` access.
- **Users** (`/admin/users`, admins only): every account with a role selector.
- **Saved metrics** (explorer, Metrics tab): name (snake_case), label, description, table, aggregate expression, format and optional filters. Client checks run first; the API's validation messages are shown under the field they describe. The analyst always uses these definitions.
- **Relationships** (explorer, Relationships tab): join keys as `child.column -> parent.column`, declared or inferred, with the share of matching values. Read from the source's `relationships` (all source kinds), falling back to the upload's ingestion report.
- **Schedules** (`/schedules`): a question on a source you can ask about, an interval (hourly, every 6 hours, daily, weekly or custom, minimum 15 minutes), an alert threshold, an optional https webhook and an enabled switch. Run now, pause, edit, delete, next and last run, and a link to the last analysis.
- **Alerts**: a bell in the shell polls `GET /api/alerts?unread_only=true` every minute and shows the unread count; its panel and `/alerts` list severity, title, message, webhook delivery status, time and a link to the analysis, with "Mark read".
- **Workspace**: the headline is a verified claim and opens its evidence; the scope check shows a short note when the plan was narrowed and corrected, and a warning caveat when restrictions remain; answers from the precomputed profile show "0 model calls" in the cost line; the report button uses `GET /api/analyses/:id/report`; live step status is matched to steps by `step_record_id`.
- **Compare runs** (`/evaluations`): select 2 to 4 runs and compare model, pass rate, accuracy, unsupported claim rates, retry recovery, first pass success, latency p50/p95, cost and LLM calls; the best value per row is highlighted, with the right direction for each metric.

## Watermelon UI components used

Installed with `npx shadcn@latest add https://registry.watermelon.sh/r/<name>.json` and then restyled to the design system. None ship in their default styling.

| Registry item                     | Where                                                                     | Customization                                                                                                                                             |
| --------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `continuous-tabs-base`            | Inspector tabs, explorer sections, mobile workspace panes, dataset filter | Controlled value, generic typed ids, WAI-ARIA tablist with arrow/Home/End keys, per-instance `layoutId`, counts, token colors, 8px radius, reduced motion |
| `labeled-progress-indicator-base` | Running analysis                                                          | Label driven by real progress events instead of a timer; width is the real share of finished plan steps; indeterminate mode; blur and 3D removed          |
| `step-indicator-base`             | Plan progress bar in running analyses and the landing preview             | One segment per plan step colored by real status, sliding tooltip, keyboard focus, Phosphor icons instead of react-icons                                  |
| `status-indicator`                | System status, LLM and sandbox reachability                               | Theme tokens instead of raw green/red; ping only for real live state and only with motion allowed                                                         |
| `skeleton`                        | Every loading state                                                       | Muted token, 8px radius, `motion-safe` pulse                                                                                                              |
| `file-upload-4`                   | Dataset upload                                                            | Simulated progress removed; real XHR progress, a server "processing" phase, inline validation and server errors with retry, Phosphor icons                |
| `code-block`                      | SQL and Python in evidence and execution detail                           | shiki core with only SQL and Python, a CSS-variables theme that follows app tokens, inline copy, zod/action scaffolding removed                           |
| `inline-toast-base`               | Copy control inside code blocks                                           | Turned into a compact copy button that morphs into an inline "Copied" confirmation                                                                        |

`stats-*` were reviewed and not used because they rely on glow and gradient effects the design rules forbid.

## OriginKit

The landing headline's mask reveal (each word rising from behind a clip) is inspired by OriginKit's "appear text" motion. OriginKit's code is behind a sign-in, so nothing was copied: `src/components/landing/AppearText.tsx` is an original implementation with `motion`, and it is disabled under `prefers-reduced-motion`.

## Design system

Follows the owner's Taste Skill rules.

- **Accent:** one deep teal, locked app-wide. Light `--brand: #0f766e` (5.4:1 on the background), dark `--brand: #2dd4bf`. Neutral base is zinc. No gradients, glows or neon.
- **Surfaces:** off-black `#0d0d0f` and off-white `#fafafa`; never pure black or white.
- **Radius:** `--radius: 8px` for cards, inputs, buttons, popovers and dialogs (all Tailwind radius steps from `md` up map to it). `rounded-full` is reserved for small status pills.
- **Type:** Geist Sans and Geist Mono via `@fontsource/geist-sans` and `@fontsource/geist-mono`. Tabular numerals for figures.
- **Theme:** dark by default with a light toggle, stored in `localStorage` and applied before first paint. Tokens live in `src/index.css` under `:root` and `.dark`.
- **Status tokens:** `success`, `warning`, `danger` each with a `-soft` background, used only for real state, always with an icon and a label.
- **Charts:** six categorical slots led by teal, validated for color-vision deficiency and contrast in both themes. Bar and area axes start at zero. Every chart has a table view, which also relieves the two light-mode slots below 3:1 contrast.
- **States:** skeletons shaped like the final layout, composed empty states that say how to populate them, inline errors that show the backend's `error.message` with a retry action, `active:` press feedback on controls.
- **Forms:** labels above inputs, hints or errors below, `aria-invalid` and `aria-describedby` wired.
- **Copy:** no en or em dashes anywhere in the UI; server text is passed through `noDashes()`.
- **Motion:** short, purposeful, and off under `prefers-reduced-motion`.
