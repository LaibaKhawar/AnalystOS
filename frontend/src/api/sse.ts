import { analysesApi } from './endpoints'
import { authFetch, buildUrl, freshAccessToken, toApiError } from './client'
import type { AnalysisEvent } from './types'

export interface SseMessage {
  event: string
  data: string
  id?: string
}

/**
 * Incremental Server-Sent Events parser. Feed it text chunks in any split;
 * it returns the complete messages found so far. Handles \n, \r\n and \r line endings,
 * comment lines (": ping") and multi-line data fields.
 */
export class SseParser {
  private buffer = ''
  private event = ''
  private data: string[] = []
  private id: string | undefined
  private lastEndedWithCR = false

  push(chunk: string): SseMessage[] {
    // A "\r\n" pair split across chunks: the "\r" already ended the line, so drop the "\n".
    let text = chunk
    if (text === '') return []
    if (this.lastEndedWithCR && text.startsWith('\n')) text = text.slice(1)
    this.lastEndedWithCR = text.endsWith('\r')
    this.buffer += text
    const messages: SseMessage[] = []
    const lines = this.buffer.split(/\r\n|\r|\n/)
    this.buffer = lines.pop() ?? ''
    for (const line of lines) {
      const message = this.processLine(line)
      if (message) messages.push(message)
    }
    return messages
  }

  private processLine(line: string): SseMessage | null {
    if (line === '') {
      if (this.data.length === 0) {
        this.event = ''
        return null
      }
      const message: SseMessage = { event: this.event || 'message', data: this.data.join('\n'), id: this.id }
      this.event = ''
      this.data = []
      return message
    }
    if (line.startsWith(':')) return null
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.event = value
    else if (field === 'data') this.data.push(value)
    else if (field === 'id') this.id = value
    return null
  }
}

export function parseProgressData(data: string): AnalysisEvent | null {
  try {
    const parsed = JSON.parse(data) as Partial<AnalysisEvent>
    if (typeof parsed.id !== 'number' || typeof parsed.type !== 'string') return null
    return {
      id: parsed.id,
      type: parsed.type,
      message: typeof parsed.message === 'string' ? parsed.message : '',
      payload: parsed.payload && typeof parsed.payload === 'object' ? parsed.payload : {},
      created_at: typeof parsed.created_at === 'string' ? parsed.created_at : new Date().toISOString(),
    }
  } catch {
    return null
  }
}

export interface StreamCallbacks {
  onEvent: (event: AnalysisEvent) => void
  onEnd: (status: string | null) => void
  onModeChange?: (mode: 'stream' | 'polling') => void
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = window.setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer)
      resolve()
    })
  })

/**
 * Follow an analysis' progress. Uses fetch + ReadableStream so the Authorization header is sent,
 * reconnects with ?after=<last id>, and falls back to polling /events when streaming keeps failing.
 * Returns a function that stops following.
 */
export function followAnalysis(analysisId: string, startAfter: number, callbacks: StreamCallbacks): () => void {
  const controller = new AbortController()
  const { signal } = controller
  let lastId = startAfter
  let ended = false

  const emit = (event: AnalysisEvent) => {
    if (event.id <= lastId) return
    lastId = event.id
    callbacks.onEvent(event)
  }
  const finish = (status: string | null) => {
    if (ended) return
    ended = true
    callbacks.onEnd(status)
  }

  async function streamOnce(): Promise<'ended' | 'dropped'> {
    // Streams outlive short access tokens: renew first when it is about to expire, and on a 401 authFetch
    // refreshes once (shared with other requests) and reconnects with the rotated token.
    await freshAccessToken()
    const path = `/analyses/${encodeURIComponent(analysisId)}/stream`
    const response = await authFetch(path, buildUrl(path, { after: lastId }), {
      headers: { Accept: 'text/event-stream' },
      signal,
    })
    if (!response.ok || !response.body) {
      let body: unknown = null
      try {
        body = await response.json()
      } catch {
        /* ignore */
      }
      throw toApiError(response.status, body)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const parser = new SseParser()
    for (;;) {
      const { value, done } = await reader.read()
      if (done) return 'dropped'
      for (const message of parser.push(decoder.decode(value, { stream: true }))) {
        if (message.event === 'progress') {
          const event = parseProgressData(message.data)
          if (event) emit(event)
        } else if (message.event === 'end') {
          let status: string | null = null
          try {
            status = (JSON.parse(message.data) as { status?: string }).status ?? null
          } catch {
            /* ignore */
          }
          finish(status)
          await reader.cancel().catch(() => undefined)
          return 'ended'
        }
      }
    }
  }

  async function poll(): Promise<void> {
    callbacks.onModeChange?.('polling')
    while (!signal.aborted && !ended) {
      try {
        const events = await analysesApi.events(analysisId, lastId)
        events.forEach(emit)
        const terminal = events.find((e) => ['completed', 'failed', 'cancelled', 'clarification'].includes(e.type))
        if (terminal) {
          finish(terminal.type)
          return
        }
        const analysis = await analysesApi.get(analysisId)
        if (!['queued', 'running'].includes(analysis.status)) {
          const rest = await analysesApi.events(analysisId, lastId)
          rest.forEach(emit)
          finish(analysis.status)
          return
        }
      } catch {
        /* transient: keep polling */
      }
      await sleep(2000, signal)
    }
  }

  void (async () => {
    let failures = 0
    while (!signal.aborted && !ended) {
      try {
        const outcome = await streamOnce()
        if (outcome === 'ended') return
        failures += 1
      } catch (error) {
        if (signal.aborted) return
        if (error && typeof error === 'object' && 'status' in error && (error as { status: number }).status === 401) {
          return
        }
        failures += 1
      }
      if (failures >= 3) {
        await poll()
        return
      }
      await sleep(1000 * failures, signal)
    }
  })()

  return () => controller.abort()
}
