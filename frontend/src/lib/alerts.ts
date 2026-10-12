import type { Tone } from '@/components/common/StatusBadge'

export function severityTone(severity: string): Tone {
  if (severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  return 'neutral'
}

export function severityLabel(severity: string): string {
  if (severity === 'high' || severity === 'medium' || severity === 'low')
    return severity.charAt(0).toUpperCase() + severity.slice(1)
  return severity
}

/** Human text for Alert.delivery_status: sent, not_configured, "failed: ..." or "blocked: ...". */
export function deliveryLabel(status: string): { text: string; ok: boolean | null } {
  if (status === 'sent') return { text: 'Webhook delivered', ok: true }
  if (status === 'not_configured' || !status) return { text: 'In app only', ok: null }
  if (status.startsWith('failed')) return { text: `Webhook failed${status.slice(6)}`, ok: false }
  if (status.startsWith('blocked')) return { text: `Webhook blocked${status.slice(7)}`, ok: false }
  if (status === 'pending') return { text: 'Delivering', ok: null }
  return { text: status.replace(/_/g, ' '), ok: null }
}
