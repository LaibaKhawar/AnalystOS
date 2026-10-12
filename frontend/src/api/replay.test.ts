import { describe, expect, it, vi } from 'vitest'
import { replayFetch, replayKey } from './replay'

const recording = {
  recorded_at: '2026-10-13T09:00:00Z',
  model: 'Qwen3 8B',
  responses: {
    'GET /sources': { status: 200, body: [{ id: 'src_1' }] },
    'GET /analyses?limit=20': { status: 200, body: [] },
    'GET /reports/rep_1/html': { status: 200, text: '<h1>Report</h1>', type: 'text/html' },
  },
}

describe('replay', () => {
  it('keys requests by method, path and sorted query', () => {
    expect(replayKey('get', '/api/analyses?limit=20')).toBe('GET /analyses?limit=20')
    expect(replayKey('GET', '/api/x?b=2&a=1')).toBe('GET /x?a=1&b=2')
  })

  it('serves recorded JSON and text responses', async () => {
    const fetchReplay = replayFetch(recording, vi.fn())
    const sources = await fetchReplay('/api/sources')
    expect(await sources.json()).toEqual([{ id: 'src_1' }])
    const html = await fetchReplay('/api/reports/rep_1/html')
    expect(html.headers.get('content-type')).toBe('text/html')
    expect(await html.text()).toBe('<h1>Report</h1>')
  })

  it('refuses writes and reports views that were not recorded', async () => {
    const fetchReplay = replayFetch(recording, vi.fn())
    const ask = await fetchReplay('/api/conversations/cnv_1/ask', { method: 'POST', body: '{}' })
    expect(ask.status).toBe(403)
    expect((await ask.json()).error.message).toMatch(/read-only replay/)
    const missing = await fetchReplay('/api/sources/src_9')
    expect(missing.status).toBe(404)
  })

  it('passes non-API requests through', async () => {
    const original = vi.fn().mockResolvedValue(new Response('font'))
    await replayFetch(recording, original)('/assets/font.woff2')
    expect(original).toHaveBeenCalledOnce()
  })
})
