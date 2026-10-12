import type { Schedule, ScheduleInput, Severity } from '@/api/types'

export const MIN_INTERVAL_MINUTES = 15

export const INTERVAL_PRESETS: { value: string; minutes: number; label: string }[] = [
  { value: '60', minutes: 60, label: 'Hourly' },
  { value: '360', minutes: 360, label: 'Every 6 hours' },
  { value: '1440', minutes: 1440, label: 'Daily' },
  { value: '10080', minutes: 10080, label: 'Weekly' },
]
export const CUSTOM_INTERVAL = 'custom'

export const SEVERITIES: { value: Severity; label: string; hint: string }[] = [
  { value: 'low', label: 'Low and above', hint: 'Alert on every anomaly the run finds.' },
  { value: 'medium', label: 'Medium and above', hint: 'Skip minor anomalies.' },
  { value: 'high', label: 'High only', hint: 'Alert only on the largest anomalies and on failed runs.' },
]

export function intervalLabel(minutes: number): string {
  const preset = INTERVAL_PRESETS.find((p) => p.minutes === minutes)
  if (preset) return preset.label
  if (minutes % 1440 === 0) return `Every ${minutes / 1440} days`
  if (minutes % 60 === 0) return `Every ${minutes / 60} hours`
  return `Every ${minutes} minutes`
}

export interface ScheduleDraft {
  data_source_id: string
  name: string
  question: string
  interval: string
  custom_minutes: string
  alert_min_severity: Severity
  webhook_url: string
  enabled: boolean
}

export type ScheduleField = 'data_source_id' | 'name' | 'question' | 'interval' | 'webhook_url'
export type ScheduleErrors = Partial<Record<ScheduleField | 'form', string>>

export function emptyScheduleDraft(sourceId = ''): ScheduleDraft {
  return {
    data_source_id: sourceId,
    name: '',
    question: '',
    interval: '1440',
    custom_minutes: '',
    alert_min_severity: 'medium',
    webhook_url: '',
    enabled: true,
  }
}

export function draftFromSchedule(s: Schedule): ScheduleDraft {
  const preset = INTERVAL_PRESETS.find((p) => p.minutes === s.interval_minutes)
  const severity = (['low', 'medium', 'high'] as const).find((v) => v === s.alert_min_severity) ?? 'medium'
  return {
    data_source_id: s.data_source_id,
    name: s.name,
    question: s.question,
    interval: preset ? preset.value : CUSTOM_INTERVAL,
    custom_minutes: preset ? '' : String(s.interval_minutes),
    alert_min_severity: severity,
    webhook_url: s.webhook_url ?? '',
    enabled: s.enabled,
  }
}

export function draftMinutes(d: ScheduleDraft): number {
  return d.interval === CUSTOM_INTERVAL ? Number(d.custom_minutes) : Number(d.interval)
}

/** Client checks that mirror the API. The API still has the final word (15 minute minimum, public https hosts). */
export function validateScheduleDraft(d: ScheduleDraft): ScheduleErrors {
  const e: ScheduleErrors = {}
  if (!d.data_source_id) e.data_source_id = 'Choose the data source to analyze.'
  if (!d.name.trim()) e.name = 'Give the schedule a name, for example Weekly revenue check.'
  if (d.question.trim().length < 3) e.question = 'Write the question to ask on every run.'
  const minutes = draftMinutes(d)
  if (d.interval === CUSTOM_INTERVAL && !/^\d+$/.test(d.custom_minutes.trim()))
    e.interval = 'Enter the interval as a whole number of minutes.'
  else if (!Number.isFinite(minutes) || minutes < MIN_INTERVAL_MINUTES)
    e.interval = `Schedules can run at most every ${MIN_INTERVAL_MINUTES} minutes.`
  else if (minutes > 60 * 24 * 31) e.interval = 'Use an interval of 31 days or less.'
  const url = d.webhook_url.trim()
  if (url) {
    const parsed = URL.canParse(url) ? new URL(url) : null
    if (!parsed || parsed.protocol !== 'https:' || !parsed.hostname) e.webhook_url = 'Webhook URLs must use https://'
  }
  return e
}

export function toScheduleInput(d: ScheduleDraft): ScheduleInput {
  return {
    data_source_id: d.data_source_id,
    name: d.name.trim(),
    question: d.question.trim(),
    interval_minutes: draftMinutes(d),
    alert_min_severity: d.alert_min_severity,
    webhook_url: d.webhook_url.trim() || null,
    enabled: d.enabled,
  }
}

export function scheduleFieldForError(message: string): ScheduleField | 'form' {
  if (/webhook/i.test(message)) return 'webhook_url'
  if (/^interval_minutes|at most every|interval/i.test(message)) return 'interval'
  if (/^question/i.test(message)) return 'question'
  if (/^name/i.test(message)) return 'name'
  if (/data source|^data_source_id/i.test(message)) return 'data_source_id'
  return 'form'
}
