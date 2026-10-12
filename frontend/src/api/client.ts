import type { ApiErrorBody } from './types'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'
const TOKEN_KEY = 'analystos.token'

/* ---------- token storage ---------- */
export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(token: string): void {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      /* storage unavailable: session lasts until reload */
    }
  },
  clear(): void {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
}

type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler | null = null
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler
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

export function errorMessage(error: unknown): string {
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

function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return headers
}

function handleUnauthorized(status: number, path: string): void {
  if (status === 401 && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
    tokenStore.clear()
    onUnauthorized?.()
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
  const headers = authHeaders({ Accept: 'application/json' })
  let payload: BodyInit | undefined
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json')
    payload = JSON.stringify(body)
  }
  let response: Response
  try {
    response = await fetch(buildUrl(path, query), { method, headers, body: payload, signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', 'Cannot reach the AnalystOS server. Check your connection and try again.')
  }
  if (response.status === 204) return undefined as T
  const data = await parseBody(response)
  if (!response.ok) {
    handleUnauthorized(response.status, path)
    throw toApiError(response.status, data)
  }
  return data as T
}

/** Authenticated binary fetch (artifacts, report HTML, exports). */
export async function requestBlob(path: string, query?: RequestOptions['query']): Promise<Blob> {
  let response: Response
  try {
    response = await fetch(buildUrl(path, query), { headers: authHeaders() })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the AnalystOS server. Check your connection and try again.')
  }
  if (!response.ok) {
    handleUnauthorized(response.status, path)
    throw toApiError(response.status, await parseBody(response))
  }
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

/** Multipart upload with real progress via XMLHttpRequest. */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (fraction: number) => void,
): UploadHandle<T> {
  const xhr = new XMLHttpRequest()
  const promise = new Promise<T>((resolve, reject) => {
    xhr.open('POST', buildUrl(path))
    const token = tokenStore.get()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      const data = parseText(xhr.responseText)
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as T)
      } else {
        handleUnauthorized(xhr.status, path)
        reject(toApiError(xhr.status, data))
      }
    }
    xhr.onerror = () =>
      reject(new ApiError(0, 'network_error', 'The upload was interrupted. Check your connection and try again.'))
    xhr.onabort = () => reject(new ApiError(0, 'aborted', 'Upload cancelled.'))
    xhr.send(form)
  })
  return { promise, abort: () => xhr.abort() }
}
