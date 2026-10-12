import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, errorMessage, request, setUnauthorizedHandler, toApiError, tokenStore } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('toApiError', () => {
  it('uses the backend error envelope message and code', () => {
    const err = toApiError(422, {
      error: { code: 'validation_failed', message: 'name: Field required', details: { a: 1 } },
    })
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(err.code).toBe('validation_failed')
    expect(err.message).toBe('name: Field required')
    expect(err.details).toEqual({ a: 1 })
  })

  it('falls back to FastAPI detail strings', () => {
    expect(toApiError(404, { detail: 'Not Found' }).message).toBe('Not Found')
  })

  it('falls back to a status message for unknown bodies', () => {
    expect(toApiError(502, '<html>bad gateway</html>').message).toBe('The server is unreachable right now.')
    expect(toApiError(418, null).message).toBe('Request failed (HTTP 418).')
  })
})

describe('request', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    localStorage.clear()
  })
  afterEach(() => {
    fetchMock.mockReset()
    vi.unstubAllGlobals()
    setUnauthorizedHandler(null)
  })

  it('sends the bearer token and JSON body', async () => {
    tokenStore.set('tok-123')
    fetchMock.mockResolvedValue(jsonResponse(200, { ok: true }))
    const data = await request<{ ok: boolean }>('/things', {
      method: 'POST',
      body: { a: 1 },
      query: { limit: 5, empty: '' },
    })
    expect(data).toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/things?limit=5')
    const headers = new Headers(init?.headers)
    expect(headers.get('Authorization')).toBe('Bearer tok-123')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(init?.body).toBe(JSON.stringify({ a: 1 }))
  })

  it('throws ApiError carrying error.message', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(400, { error: { code: 'error', message: 'This analysis has already finished', details: {} } }),
    )
    await expect(request('/analyses/x/cancel', { method: 'POST' })).rejects.toMatchObject({
      status: 400,
      message: 'This analysis has already finished',
    })
  })

  it('clears the token and calls the unauthorized handler on 401', async () => {
    tokenStore.set('expired')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    fetchMock.mockResolvedValue(
      jsonResponse(401, { error: { code: 'unauthorized', message: 'Sign in to continue', details: {} } }),
    )
    await expect(request('/sources')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledOnce()
    expect(tokenStore.get()).toBeNull()
  })

  it('does not redirect on a failed login', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    fetchMock.mockResolvedValue(
      jsonResponse(401, { error: { code: 'unauthorized', message: 'Incorrect email or password', details: {} } }),
    )
    await expect(request('/auth/login', { method: 'POST', body: {} })).rejects.toThrow('Incorrect email or password')
    expect(handler).not.toHaveBeenCalled()
  })

  it('maps network failures to a friendly error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await request('/sources').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(errorMessage(error)).toMatch(/Cannot reach the AnalystOS server/)
  })

  it('returns undefined for 204', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(request('/sources/x', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})
