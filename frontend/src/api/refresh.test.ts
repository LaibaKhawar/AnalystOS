import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json } from '@/test/utils'
import {
  freshAccessToken,
  logoutSession,
  request,
  secondsUntilExpiry,
  setUnauthorizedHandler,
  tokenStore,
  uploadWithProgress,
} from './client'

const fetchMock = vi.fn<typeof fetch>()
const unauthorized = (message = 'Session expired') =>
  json(401, { error: { code: 'unauthorized', message, details: {} } })
const auth = (init: RequestInit | undefined) => new Headers(init?.headers).get('Authorization')
const pathOf = (input: Parameters<typeof fetch>[0]) => new URL(String(input), 'http://x').pathname

/** A fake JWT whose payload expires `inSeconds` from now. */
function jwt(inSeconds: number): string {
  const payload = btoa(JSON.stringify({ sub: 'usr_1', exp: Math.floor(Date.now() / 1000) + inSeconds }))
  return `h.${payload.replace(/=+$/, '')}.s`
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  localStorage.clear()
})
afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('token refresh', () => {
  it('stores both tokens and clears both', () => {
    tokenStore.set('access-1', 'refresh-1')
    expect(tokenStore.get()).toBe('access-1')
    expect(tokenStore.getRefresh()).toBe('refresh-1')
    tokenStore.clear()
    expect(tokenStore.get()).toBeNull()
    expect(tokenStore.getRefresh()).toBeNull()
  })

  it('refreshes once on a 401, stores the rotated pair and retries the request', async () => {
    tokenStore.set('old-access', 'old-refresh')
    fetchMock.mockImplementation(async (input, init) => {
      const path = pathOf(input)
      if (path === '/api/auth/refresh') {
        expect(JSON.parse(String(init?.body))).toEqual({ refresh_token: 'old-refresh' })
        return json(200, { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer', user: {} })
      }
      return auth(init) === 'Bearer new-access' ? json(200, [{ id: 'src_1' }]) : unauthorized()
    })

    await expect(request('/sources')).resolves.toEqual([{ id: 'src_1' }])
    expect(tokenStore.get()).toBe('new-access')
    expect(tokenStore.getRefresh()).toBe('new-refresh')
    const paths = fetchMock.mock.calls.map(([input]) => pathOf(input))
    expect(paths).toEqual(['/api/sources', '/api/auth/refresh', '/api/sources'])
  })

  it('shares one refresh between concurrent 401s (single flight)', async () => {
    tokenStore.set('old-access', 'old-refresh')
    let release: (r: Response) => void = () => undefined
    const refreshResponse = new Promise<Response>((resolve) => (release = resolve))
    fetchMock.mockImplementation(async (input, init) => {
      if (pathOf(input) === '/api/auth/refresh') return refreshResponse
      return auth(init) === 'Bearer new-access' ? json(200, { path: pathOf(input) }) : unauthorized()
    })

    const pending = Promise.all([request('/a'), request('/b'), request('/c')])
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.filter(([i]) => pathOf(i) === '/api/auth/refresh')).toHaveLength(1),
    )
    release(json(200, { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer', user: {} }))

    await expect(pending).resolves.toEqual([{ path: '/api/a' }, { path: '/api/b' }, { path: '/api/c' }])
    expect(fetchMock.mock.calls.filter(([i]) => pathOf(i) === '/api/auth/refresh')).toHaveLength(1)
  })

  it('retries without refreshing when another request already renewed the token', async () => {
    tokenStore.set('old-access', 'old-refresh')
    fetchMock.mockImplementation(async (_input, init) => {
      if (auth(init) === 'Bearer old-access') {
        tokenStore.set('renewed-access', 'renewed-refresh') // a concurrent refresh landed meanwhile
        return unauthorized()
      }
      return json(200, { ok: true })
    })
    await expect(request('/sources')).resolves.toEqual({ ok: true })
    expect(fetchMock.mock.calls.some(([i]) => pathOf(i) === '/api/auth/refresh')).toBe(false)
  })

  it('clears tokens and calls the unauthorized handler when the refresh fails', async () => {
    tokenStore.set('old-access', 'revoked-refresh')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    fetchMock.mockImplementation(async (input) =>
      pathOf(input) === '/api/auth/refresh' ? unauthorized('Session expired, please sign in again') : unauthorized(),
    )
    await expect(request('/sources')).rejects.toMatchObject({ status: 401 })
    expect(handler).toHaveBeenCalledOnce()
    expect(tokenStore.get()).toBeNull()
    expect(tokenStore.getRefresh()).toBeNull()
  })

  it('logs out when the retried request is still unauthorized', async () => {
    tokenStore.set('old-access', 'old-refresh')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    fetchMock.mockImplementation(async (input) =>
      pathOf(input) === '/api/auth/refresh'
        ? json(200, { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer', user: {} })
        : unauthorized(),
    )
    await expect(request('/sources')).rejects.toMatchObject({ status: 401 })
    expect(handler).toHaveBeenCalledOnce()
    expect(tokenStore.get()).toBeNull()
  })

  it('never refreshes for the auth endpoints themselves', async () => {
    tokenStore.set('a', 'r')
    fetchMock.mockResolvedValue(unauthorized('Incorrect email or password'))
    await expect(request('/auth/login', { method: 'POST', body: {} })).rejects.toThrow('Incorrect email or password')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('refreshes and re-sends an upload that got a 401', async () => {
    tokenStore.set('old-access', 'old-refresh')
    fetchMock.mockResolvedValue(
      json(200, { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer', user: {} }),
    )
    const sent: (string | null)[] = []
    class FakeXhr {
      status = 0
      responseText = ''
      upload = { onprogress: null }
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      onabort: (() => void) | null = null
      private headers: Record<string, string> = {}
      open() {}
      setRequestHeader(name: string, value: string) {
        this.headers[name] = value
      }
      abort() {}
      send() {
        const token = this.headers.Authorization ?? null
        sent.push(token)
        this.status = token === 'Bearer new-access' ? 201 : 401
        this.responseText = JSON.stringify(
          this.status === 201 ? { id: 'src_9' } : { error: { code: 'x', message: 'no', details: {} } },
        )
        queueMicrotask(() => this.onload?.())
      }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const handle = uploadWithProgress<{ id: string }>('/sources/upload', new FormData(), () => undefined)
    await expect(handle.promise).resolves.toEqual({ id: 'src_9' })
    expect(sent).toEqual(['Bearer old-access', 'Bearer new-access'])
  })
})

describe('fresh tokens for streams', () => {
  it('reads JWT expiry', () => {
    expect(secondsUntilExpiry(jwt(600))).toBeGreaterThan(590)
    expect(secondsUntilExpiry('not-a-jwt')).toBeNull()
  })

  it('refreshes ahead of time when the access token is about to expire', async () => {
    tokenStore.set(jwt(5), 'r1')
    fetchMock.mockResolvedValue(
      json(200, { access_token: 'renewed', refresh_token: 'r2', token_type: 'bearer', user: {} }),
    )
    await expect(freshAccessToken()).resolves.toBe('renewed')
    expect(tokenStore.getRefresh()).toBe('r2')
  })

  it('keeps a token that is still valid', async () => {
    const token = jwt(900)
    tokenStore.set(token, 'r1')
    await expect(freshAccessToken()).resolves.toBe(token)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('logout', () => {
  it('revokes the refresh token on the server and clears local tokens', async () => {
    tokenStore.set('a', 'refresh-xyz')
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await logoutSession()
    const [input, init] = fetchMock.mock.calls[0]
    expect(pathOf(input)).toBe('/api/auth/logout')
    expect(JSON.parse(String(init?.body))).toEqual({ refresh_token: 'refresh-xyz' })
    expect(tokenStore.get()).toBeNull()
    expect(tokenStore.getRefresh()).toBeNull()
  })

  it('still signs out locally when the server is unreachable', async () => {
    tokenStore.set('a', 'r')
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(logoutSession()).resolves.toBeUndefined()
    expect(tokenStore.get()).toBeNull()
  })
})
