/**
 * Read-only replay of recorded API responses, for the static demo on GitHub Pages (`npm run build:replay`).
 *
 * `scripts/record-replay.mjs` browses a running stack as the demo user and stores every JSON GET response in
 * `public/replay.json`. In replay mode `window.fetch` answers API calls from that file; writes (asking a question,
 * uploading, sharing...) are refused with a clear message. Nothing is generated in the browser: every answer,
 * finding and claim shown was produced by the real backend and model when the recording was made.
 */
import { API_BASE, tokenStore } from './client'

export const REPLAY = import.meta.env.VITE_REPLAY === '1'

interface Recording {
  recorded_at: string
  model: string
  // JSON responses keep `body`; HTML/CSV (report views, downloads) keep `text` and its content type.
  responses: Record<string, { status: number; body?: unknown; text?: string; type?: string }>
}

/** "GET /sources/src_1?b=2&a=1" -> "GET /sources/src_1?a=1&b=2" (stable regardless of parameter order). */
export function replayKey(method: string, url: string): string {
  const parsed = new URL(url, 'http://replay.local')
  const base = new URL(API_BASE, 'http://replay.local').pathname.replace(/\/$/, '')
  const path = parsed.pathname.startsWith(base) ? parsed.pathname.slice(base.length) : parsed.pathname
  const params = [...parsed.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b))
  const query = params.length ? `?${new URLSearchParams(params).toString()}` : ''
  return `${method.toUpperCase()} ${path}${query}`
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

const refusal = (message: string) => json(403, { error: { code: 'replay_read_only', message, details: {} } })

export function isApiUrl(url: string): boolean {
  const path = new URL(url, window.location.origin).pathname
  return path.startsWith(new URL(API_BASE, window.location.origin).pathname)
}

export function replayFetch(recording: Recording, original: typeof fetch): typeof fetch {
  return async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (!isApiUrl(url)) return original(input, init)
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    if (method !== 'GET') {
      return refusal(
        'This is a read-only replay of recorded analyses. Run AnalystOS locally (docker compose up) to ask new questions.',
      )
    }
    const hit = recording.responses[replayKey(method, url)]
    if (hit?.text !== undefined)
      return new Response(hit.text, { status: hit.status, headers: { 'content-type': hit.type ?? 'text/plain' } })
    if (hit) return json(hit.status, hit.body)
    return json(404, {
      error: { code: 'not_recorded', message: 'This view was not part of the recorded demo.', details: {} },
    })
  }
}

export interface ReplayInfo {
  recordedAt: string
  model: string
}

/** Load the recording and route API calls to it. Resolves with what the banner shows. */
export async function installReplay(): Promise<ReplayInfo> {
  const response = await fetch(`${import.meta.env.BASE_URL}replay.json`)
  const recording = (await response.json()) as Recording
  window.fetch = replayFetch(recording, window.fetch.bind(window))
  tokenStore.set('replay', null)
  return { recordedAt: recording.recorded_at, model: recording.model }
}
