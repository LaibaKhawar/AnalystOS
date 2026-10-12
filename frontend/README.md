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

| Script              | What it does                                                        |
| ------------------- | ------------------------------------------------------------------- |
| `npm run dev`       | Vite dev server on port 5173 with the `/api` proxy                  |
| `npm run build`     | Type-check (project references) and build to `dist/`                |
| `npm run preview`   | Serve the built app on port 4173 (same proxy)                       |
| `npm run lint`      | ESLint (typescript-eslint, react-hooks, react-refresh)              |
| `npm run typecheck` | `tsc --noEmit` for app and node configs                             |
| `npm run test`      | Vitest unit and component tests (jsdom)                             |
| `npm run format`    | Prettier (with the Tailwind class sorter)                           |
| `npm run e2e`       | Playwright end-to-end spec against a running dev server and backend |

### End-to-end tests

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

## Structure

```
src/
  api/            types.ts (every response type), client.ts (fetch, errors, auth, upload progress),
                  endpoints.ts (typed functions), sse.ts (SSE parser + follow with reconnect and polling fallback)
  hooks/queries/  TanStack Query hooks per resource with cache invalidation
  hooks/          useAnalysisStream (live progress), useElementWidth
  providers/      Auth (token in localStorage, 401 redirects to /login) and Theme (dark default)
  lib/            format, claims grouping, chart selection and export, upload validation, metrics
  components/
    analysis/     thread turn, running view, answer, claims, evidence drawer, cost line, activity feed
    inspector/    plan, evidence (findings) and execution history panels, execution detail sheet
    charts/       Recharts renderers, SVG box plot and heatmap, chart card with SVG and PNG export
    explorer/     schema grid with column editor, preview, profiling, semantic summary
    workspace/    source tree, active context chips, conversation list, ask box
    layout/       app shell, nav, command palette (Cmd K), user menu, theme toggle
    watermelon/   customized Watermelon UI components (see below)
    ui/           shadcn/ui primitives plus customized Watermelon components installed into ui/
  pages/          one file per route
```

Routes: `/welcome` (public landing), `/login`, `/register`, `/` (dashboard), `/datasets`, `/connections`, `/sources/:id` (explorer), `/workspace/:conversationId`, `/reports`, `/reports/:id`, `/evaluations`, `/evaluations/:runId`.

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
