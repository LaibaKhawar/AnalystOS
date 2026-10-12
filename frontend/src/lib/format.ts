/** Formatting helpers. All output avoids en and em dashes; missing values render as a hyphen. */

export const EMPTY = '-'

const isNum = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

export function formatNumber(value: unknown, maxFractionDigits = 2): string {
  if (!isNum(value)) return EMPTY
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: maxFractionDigits }).format(value)
}

export function formatInteger(value: unknown): string {
  if (!isNum(value)) return EMPTY
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Math.round(value))
}

/** Compact: 1.2K, 3.4M, 2.1B. Small values keep two decimals. */
export function formatCompact(value: unknown): string {
  if (!isNum(value)) return EMPTY
  const abs = Math.abs(value)
  if (abs < 1000) return formatNumber(value, abs < 10 ? 2 : 1)
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

/** LLM cost, always four decimals: $0.0000 for local models. */
export function formatCost(value: unknown): string {
  if (!isNum(value)) return '$0.0000'
  const sign = value < 0 ? '-' : ''
  return `${sign}$${Math.abs(value).toFixed(4)}`
}

export function formatCurrency(value: unknown, currency = 'USD'): string {
  if (!isNum(value)) return EMPTY
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
}

/**
 * Percent from a ratio (0.42 -> "42%"). Pass `alreadyPercent` when the value is 0..100.
 */
export function formatPercent(value: unknown, digits = 1, alreadyPercent = false): string {
  if (!isNum(value)) return EMPTY
  const pct = alreadyPercent ? value : value * 100
  const fixed = pct.toFixed(digits)
  const trimmed = digits > 0 ? fixed.replace(/\.0+$/, '') : fixed
  return `${trimmed}%`
}

/** 850 -> "850 ms", 4200 -> "4.2 s", 95000 -> "1m 35s", 3_900_000 -> "1h 5m". */
export function formatDuration(ms: unknown): string {
  if (!isNum(ms) || ms < 0) return EMPTY
  if (ms < 1000) return `${Math.round(ms)} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`
  const totalSeconds = Math.round(seconds)
  const minutes = Math.floor(totalSeconds / 60)
  if (minutes < 60) return `${minutes}m ${totalSeconds % 60}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

export function formatBytes(bytes: unknown): string {
  if (!isNum(bytes) || bytes < 0) return EMPTY
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`
}

export function formatTokens(value: unknown): string {
  if (!isNum(value)) return '0'
  return formatInteger(value)
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return EMPTY
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return EMPTY
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(date)
}

export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return EMPTY
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return EMPTY
  const diff = (now.getTime() - date.getTime()) / 1000
  if (diff < 45) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)}d ago`
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date)
}

/** Time until a future moment: "in 5m", "in 3h", "in 2d", or "due now" once it has passed. */
export function formatUntil(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return EMPTY
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return EMPTY
  const diff = (date.getTime() - now.getTime()) / 1000
  if (diff <= 30) return 'due now'
  if (diff < 3600) return `in ${Math.max(1, Math.round(diff / 60))}m`
  if (diff < 86400) return `in ${Math.round(diff / 3600)}h`
  if (diff < 86400 * 7) return `in ${Math.round(diff / 86400)}d`
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date)
}

/** Render any table cell value compactly. */
export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return EMPTY
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return String(value)
    return Number.isInteger(value) ? formatInteger(value) : formatNumber(value, 4)
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** snake_case or kebab to "Sentence case". */
export function humanize(key: string): string {
  const spaced = key.replace(/[_-]+/g, ' ').trim()
  if (!spaced) return key
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

/** Strip en/em dashes from any server-provided copy before display. */
export function noDashes(text: string): string {
  return text.replace(/\s*[–—]\s*/g, ', ')
}
