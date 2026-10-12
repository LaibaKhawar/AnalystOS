import { useId, useState, type FormEvent } from 'react'
import { ApiError, errorMessage } from '@/api/client'
import type { DataSource, Schedule, Severity } from '@/api/types'
import { Field } from '@/components/forms/Field'
import { FormError } from '@/components/forms/FormError'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useSaveSchedule } from '@/hooks/queries/schedules'
import {
  CUSTOM_INTERVAL,
  draftFromSchedule,
  emptyScheduleDraft,
  INTERVAL_PRESETS,
  MIN_INTERVAL_MINUTES,
  scheduleFieldForError,
  SEVERITIES,
  toScheduleInput,
  validateScheduleDraft,
  type ScheduleDraft,
  type ScheduleErrors,
} from '@/lib/schedules'

/** Create or edit a schedule. `sources` must already be limited to sources the user may ask questions about. */
export function ScheduleForm({
  sources,
  schedule,
  onSaved,
  onCancel,
}: {
  sources: DataSource[]
  schedule: Schedule | null
  onSaved: (schedule: Schedule) => void
  onCancel: () => void
}) {
  const save = useSaveSchedule()
  const enabledId = useId()
  const [draft, setDraft] = useState<ScheduleDraft>(() =>
    schedule ? draftFromSchedule(schedule) : emptyScheduleDraft(sources.length === 1 ? sources[0].id : ''),
  )
  const [errors, setErrors] = useState<ScheduleErrors>({})
  const set = <K extends keyof ScheduleDraft>(key: K, value: ScheduleDraft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }))
  const severityHint = SEVERITIES.find((s) => s.value === draft.alert_min_severity)?.hint

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const next = validateScheduleDraft(draft)
    setErrors(next)
    if (Object.keys(next).length) return
    save.mutate(
      { id: schedule?.id ?? null, input: toScheduleInput(draft) },
      {
        onSuccess: (saved) => onSaved(saved),
        onError: (error) => {
          const message = errorMessage(error)
          const field = error instanceof ApiError && error.status === 422 ? scheduleFieldForError(message) : 'form'
          setErrors({ [field]: message })
        },
      },
    )
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      className="flex flex-col gap-4"
      aria-label={schedule ? 'Edit schedule' : 'New schedule'}
    >
      <FormError message={errors.form ?? null} error={errors.form ? save.error : undefined} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Data source"
          error={errors.data_source_id}
          hint={schedule ? 'The data source of a schedule cannot be changed.' : 'Sources you can ask questions about.'}
          className="sm:col-span-2"
        >
          {(p) => (
            <Select
              value={draft.data_source_id || undefined}
              onValueChange={(v) => set('data_source_id', v)}
              disabled={Boolean(schedule)}
            >
              <SelectTrigger
                id={p.id}
                aria-invalid={p['aria-invalid']}
                aria-describedby={p['aria-describedby']}
                className="w-full"
                data-testid="schedule-source"
              >
                <SelectValue placeholder="Choose a data source" />
              </SelectTrigger>
              <SelectContent>
                {sources.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Name" error={errors.name} className="sm:col-span-2">
          {(p) => (
            <Input
              {...p}
              value={draft.name}
              maxLength={200}
              placeholder="Weekly revenue check"
              onChange={(e) => set('name', e.target.value)}
            />
          )}
        </Field>
        <Field
          label="Question"
          error={errors.question}
          hint="Asked on every run, exactly as written."
          className="sm:col-span-2"
        >
          {(p) => (
            <Textarea
              {...p}
              rows={2}
              value={draft.question}
              maxLength={4000}
              placeholder="Which region had the highest revenue last week, and is anything unusual?"
              onChange={(e) => set('question', e.target.value)}
            />
          )}
        </Field>
        <Field label="Runs" error={errors.interval} hint={`The shortest interval is ${MIN_INTERVAL_MINUTES} minutes.`}>
          {(p) => (
            <div className="flex flex-col gap-2">
              <Select value={draft.interval} onValueChange={(v) => set('interval', v)}>
                <SelectTrigger
                  id={p.id}
                  aria-invalid={p['aria-invalid']}
                  aria-describedby={p['aria-describedby']}
                  className="w-full"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INTERVAL_PRESETS.map((preset) => (
                    <SelectItem key={preset.value} value={preset.value}>
                      {preset.label}
                    </SelectItem>
                  ))}
                  <SelectItem value={CUSTOM_INTERVAL}>Custom interval</SelectItem>
                </SelectContent>
              </Select>
              {draft.interval === CUSTOM_INTERVAL && (
                <div className="flex items-center gap-2">
                  <Input
                    aria-label="Interval in minutes"
                    inputMode="numeric"
                    value={draft.custom_minutes}
                    onChange={(e) => set('custom_minutes', e.target.value)}
                    className="w-28"
                  />
                  <span className="text-muted-foreground text-sm">minutes</span>
                </div>
              )}
            </div>
          )}
        </Field>
        <Field label="Alert when" hint={severityHint}>
          {(p) => (
            <Select value={draft.alert_min_severity} onValueChange={(v) => set('alert_min_severity', v as Severity)}>
              <SelectTrigger id={p.id} aria-describedby={p['aria-describedby']} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SEVERITIES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field
          label="Webhook URL"
          optional
          error={errors.webhook_url}
          hint="Alerts are also sent here as JSON. https only; private and loopback hosts are blocked."
          className="sm:col-span-2"
        >
          {(p) => (
            <Input
              {...p}
              type="url"
              inputMode="url"
              spellCheck={false}
              autoComplete="off"
              value={draft.webhook_url}
              placeholder="https://hooks.example.com/analystos"
              onChange={(e) => set('webhook_url', e.target.value)}
            />
          )}
        </Field>
      </div>
      <div className="flex items-start gap-3 rounded-lg border p-3">
        <Switch id={enabledId} checked={draft.enabled} onCheckedChange={(v) => set('enabled', v)} className="mt-0.5" />
        <label htmlFor={enabledId} className="cursor-pointer text-sm">
          <span className="text-foreground block font-medium">Enabled</span>
          <span className="text-muted-foreground block text-xs">
            Paused schedules keep their history and can still be run manually.
          </span>
        </label>
      </div>
      <div className="flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending} data-testid="schedule-save">
          {save.isPending ? 'Saving' : schedule ? 'Save changes' : 'Create schedule'}
        </Button>
      </div>
    </form>
  )
}
