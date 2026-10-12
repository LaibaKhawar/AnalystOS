import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import type { User } from '@/api/types'
import { AuthContext, type AuthContextValue } from '@/providers/auth-context'

export const testUser = (over: Partial<User> = {}): User => ({
  id: 'usr_1',
  email: 'ana@example.com',
  name: 'Ana Analyst',
  is_admin: false,
  role: 'analyst',
  ...over,
})

export function authValue(user: User | null): AuthContextValue {
  return {
    user,
    isAuthenticated: Boolean(user),
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }
}

export function renderWithProviders(
  ui: ReactElement,
  { user, route = '/' }: { user?: User | null; route?: string } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const tree = (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
  return {
    client,
    ...render(user === undefined ? tree : <AuthContext.Provider value={authValue(user)}>{tree}</AuthContext.Provider>),
  }
}

export function json(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type Handler = (init: RequestInit | undefined, url: URL) => Response | Promise<Response>

/**
 * Stub global fetch with a route table keyed by "METHOD /api/path" (query string ignored).
 * Unknown routes answer 404 so a missing stub fails loudly. Returns the mock to inspect calls.
 */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://x')
    const key = `${(init?.method ?? 'GET').toUpperCase()} ${url.pathname}`
    if (!(key in routes)) return json(404, { error: { code: 'not_found', message: `No stub for ${key}`, details: {} } })
    const route = routes[key]
    return typeof route === 'function' ? (route as Handler)(init, url) : json(200, route)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Parsed JSON body of the n-th call to `key` ("POST /api/x"). */
export function sentBody(fetchMock: ReturnType<typeof mockApi>, key: string, n = 0): unknown {
  const calls = fetchMock.mock.calls.filter(([input, init]) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://x')
    return `${(init?.method ?? 'GET').toUpperCase()} ${url.pathname}` === key
  })
  const body = calls[n]?.[1]?.body
  return typeof body === 'string' ? (JSON.parse(body) as unknown) : undefined
}
