import type { ApiErrorBody, TokenResponse } from './types'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'
const TOKEN_KEY = 'analystos.token'
const REFRESH_KEY = 'analystos.refresh'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}

/* ---------- token storage ---------- */
export const tokenStore = {
  /** The short-lived access token (30 minutes). */
  get(): string | null {
    return read(TOKEN_KEY)
  },
  /** The long-lived, single-use refresh token. */
  getRefresh(): string | null {
    return read(REFRESH_KEY)
  },
  set(token: string, refreshToken?: string | null): void {
    write(TOKEN_KEY, token)
    if (refreshToken !== undefined) write(REFRESH_KEY, refreshToken)
  },
  clear(): void {
    write(TOKEN_KEY, null)
    write(REFRESH_KEY, null)
  },
}

type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler | null = null
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler
}

/** End the session locally: drop both tokens and let the app route to /login. */
function expireSession(): void {
  tokenStore.clear()
  onUnauthorized?.()
}

/* ---------- errors ---------- */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const err = (value as { error: unknown }).error
  return typeof err === 'object' && err !== null && typeof (err as { message?: unknown }).message === 'string'
}

const STATUS_MESSAGES: Record<number, string> = {
  400: 'The request could not be processed.',
  401: 'Your session has expired. Sign in again.',
  403: 'You do not have access to this resource.',
  404: 'Not found.',
  413: 'The file is too large for the server.',
  422: 'Some fields are invalid.',
  429: 'Too many requests. Try again in a moment.',
  500: 'Something went wrong on the server.',
  502: 'The server is unreachable right now.',
  503: 'The service is temporarily unavailable.',
  504: 'The server took too long to respond.',
}

/** Turn any failed response body into an ApiError that carries the backend's user-facing message. */
export function toApiError(status: number, body: unknown): ApiError {
  if (isErrorBody(body)) {
    const { code, message, details } = body.error
    return new ApiError(status, code || 'error', message, details ?? {})
  }
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return new ApiError(status, 'error', detail)
  }
  return new ApiError(status, 'http_error', STATUS_MESSAGES[status] ?? `Request failed (HTTP ${status}).`)
}

/** "45 seconds", "12 minutes", "2 hours" for a rate limit wait. */
export function formatWait(seconds: number): string {
  const s = Math.max(1, Math.round(seconds))
  if (s < 90) return `${s} ${s === 1 ? 'second' : 'seconds'}`
  const m = Math.round(s / 60)
  if (m < 90) return `${m} minutes`
  const h = Math.round(m / 60)
  return `${h} ${h === 1 ? 'hour' : 'hours'}`
}

/** Seconds to wait before retrying a rate-limited request, when the server said so. */
export function retryAfterSeconds(error: unknown): number | null {
  if (!(error instanceof ApiError) || error.code !== 'rate_limited') return null
  const value = error.details.retry_after_seconds
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export const isForbidden = (error: unknown) =>
  error instanceof ApiError && (error.code === 'forbidden' || error.status === 403)
export const isRateLimited = (error: unknown) =>
  error instanceof ApiError && (error.code === 'rate_limited' || error.status === 429)

export function errorMessage(error: unknown): string {
  if (isRateLimited(error)) {
    const wait = retryAfterSeconds(error)
    return wait === null
      ? 'Too many requests. Try again in a moment.'
      : `Too many requests. Try again in ${formatWait(wait)}.`
  }
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong.'
}

function parseText(text: string): unknown {
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

async function parseBody(response: Response): Promise<unknown> {
  return parseText(await response.text())
}

const AUTH_PATHS = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/logout']
const isAuthPath = (path: string) => AUTH_PATHS.some((p) => path.startsWith(p))

function withAuth(init: RequestInit, token: string | null): RequestInit {
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  else headers.delete('Authorization')
  return { ...init, headers }
}

/* ---------- refresh (single flight) ---------- */
let refreshing: Promise<string | null> | null = null

async function performRefresh(): Promise<string | null> {
  const refreshToken = tokenStore.getRefresh()
  if (!refreshToken) return null
  let response: Response
  try {
    response = await fetch(buildUrl('/auth/refresh'), {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the AnalystOS server. Check your connection and try again.')
  }
  if (!response.ok) return null
  const data = (await parseBody(response)) as Partial<TokenResponse> | null
  if (!data?.access_token) return null
  tokenStore.set(data.access_token, data.refresh_token || refreshToken)
  return data.access_token
}

/**
 * Exchange the refresh token for a new access/refresh pair. Concurrent callers share one request,
 * because the server rotates refresh tokens and reusing a spent one revokes every session.
 * Resolves to the new access token, or null when the session cannot be renewed.
 */
export function refreshAccessToken(): Promise<string | null> {
  if (!refreshing) {
    refreshing = performRefresh().finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

/** Seconds until a JWT expires, or null when the token is not a readable JWT. */
export function secondsUntilExpiry(token: string, now = Date.now()): number | null {
  const part = token.split('.')[1]
  if (!part) return null
  try {
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    const exp = (JSON.parse(json) as { exp?: unknown }).exp
    return typeof exp === 'number' ? exp - now / 1000 : null
  } catch {
    return null
  }
}

/** A usable access token: refreshed first when it expires within `marginSeconds`. Used by long-lived streams. */
export async function freshAccessToken(marginSeconds = 30): Promise<string | null> {
  const token = tokenStore.get()
  if (!token) return null
  const left = secondsUntilExpiry(token)
  if (left !== null && left < marginSeconds && tokenStore.getRefresh()) {
    return (await refreshAccessToken()) ?? null
  }
  return token
}

/**
 * fetch with the bearer token. On a 401 it refreshes once (shared with any concurrent 401s) and retries;
 * if the session cannot be renewed it clears the tokens and hands control to the unauthorized handler.
 */
export async function authFetch(path: string, url: string, init: RequestInit = {}): Promise<Response> {
  const sent = tokenStore.get()
  const response = await fetch(url, withAuth(init, sent))
  if (response.status !== 401 || isAuthPath(path)) return response
  const current = tokenStore.get()
  // Another request already renewed the session while this one was in flight: just retry.
  const next = current && current !== sent ? current : await refreshAccessToken()
  if (!next) {
    expireSession()
    return response
  }
  const retried = await fetch(url, withAuth(init, next))
  if (retried.status === 401) expireSession()
  return retried
}

/** Revoke the refresh token on the server (best effort), then forget both tokens. */
export async function logoutSession(): Promise<void> {
  const refreshToken = tokenStore.getRefresh()
  tokenStore.clear()
  if (!refreshToken) return
  try {
    await fetch(buildUrl('/auth/logout'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
  } catch {
    /* the token expires on its own; signing out locally is what matters */
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | null | undefined>
  signal?: AbortSignal
}

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

/** JSON request. Throws ApiError with the backend's `error.message` on failure. */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal } = options
  const headers = new Headers({ Accept: 'application/json' })
  let payload: BodyInit | undefined
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json')
    payload = JSON.stringify(body)
  }
  let response: Response
  try {
    response = await authFetch(path, buildUrl(path, query), { method, headers, body: payload, signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    if (error instanceof ApiError) throw error
    throw new ApiError(0, 'network_error', 'Cannot reach the AnalystOS server. Check your connection and try again.')
  }
  if (response.status === 204) return undefined as T
  const data = await parseBody(response)
  if (!response.ok) throw toApiError(response.status, data)
  return data as T
}

/** Authenticated binary fetch (artifacts, report HTML, exports). */
export async function requestBlob(path: string, query?: RequestOptions['query']): Promise<Blob> {
  let response: Response
  try {
    response = await authFetch(path, buildUrl(path, query))
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, 'network_error', 'Cannot reach the AnalystOS server. Check your connection and try again.')
  }
  if (!response.ok) throw toApiError(response.status, await parseBody(response))
  return response.blob()
}

/** Fetch with auth and save to disk. */
export async function downloadFile(path: string, filename: string, query?: RequestOptions['query']): Promise<void> {
  const blob = await requestBlob(path, query)
  saveBlob(blob, filename)
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export interface UploadHandle<T> {
  promise: Promise<T>
  abort: () => void
}

/** Multipart upload with real progress via XMLHttpRequest. A 401 refreshes the session once and re-sends. */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (fraction: number) => void,
): UploadHandle<T> {
  let current: XMLHttpRequest | null = null
  let aborted = false

  const send = (token: string | null) =>
    new Promise<{ status: number; data: unknown }>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      current = xhr
      xhr.open('POST', buildUrl(path))
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.setRequestHeader('Accept', 'application/json')
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total)
      }
      xhr.onload = () => resolve({ status: xhr.status, data: parseText(xhr.responseText) })
      xhr.onerror = () =>
        reject(new ApiError(0, 'network_error', 'The upload was interrupted. Check your connection and try again.'))
      xhr.onabort = () => reject(new ApiError(0, 'aborted', 'Upload cancelled.'))
      xhr.send(form)
    })

  const promise = (async () => {
    const sent = tokenStore.get()
    let result = await send(sent)
    if (result.status === 401 && !aborted) {
      const latest = tokenStore.get()
      const next = latest && latest !== sent ? latest : await refreshAccessToken()
      if (next) {
        onProgress(0)
        result = await send(next)
      }
      if (result.status === 401) expireSession()
    }
    if (result.status >= 200 && result.status < 300) return result.data as T
    throw toApiError(result.status, result.data)
  })()

  return {
    promise,
    abort: () => {
      aborted = true
      current?.abort()
    },
  }
}
