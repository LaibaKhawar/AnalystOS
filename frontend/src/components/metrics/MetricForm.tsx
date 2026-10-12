import { PlusIcon, XIcon } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { ApiError, errorMessage } from '@/api/client'
import type { MetricDefinition, MetricFormat, Table } from '@/api/types'
import { Field } from '@/components/forms/Field'
import { FormError } from '@/components/forms/FormError'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useSaveMetric } from '@/hooks/queries/metrics'
import {
  draftFromMetric,
  emptyDraft,
  fieldForServerError,
  FILTER_OPS,
  METRIC_FORMATS,
  newFilter,
  suggestName,
  toMetricInput,
  validateMetricDraft,
  type FilterDraft,
  type MetricDraft,
  type MetricErrors,
} from '@/lib/metric-form'

function FilterRow({
  filter,
  index,
  columns,
  onChange,
  onRemove,
}: {
  filter: FilterDraft
  index: number
  columns: string[]
  onChange: (next: FilterDraft) => void
  onRemove: () => void
}) {
  const needsValue = FILTER_OPS.find((o) => o.value === filter.op)?.needsValue ?? true
  const n = index + 1
  return (
    <li className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-center">
      <Select value={filter.column || undefined} onValueChange={(column) => onChange({ ...filter, column })}>
        <SelectTrigger aria-label={`Filter ${n} column`} className="w-full">
          <SelectValue placeholder="Column" />
        </SelectTrigger>
        <SelectContent>
          {columns.map((c) => (
            <SelectItem key={c} value={c}>
              <span className="font-mono text-xs">{c}</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={filter.op} onValueChange={(op) => onChange({ ...filter, op })}>
        <SelectTrigger aria-label={`Filter ${n} operator`} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {FILTER_OPS.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        aria-label={`Filter ${n} value`}
        value={filter.value}
        disabled={!needsValue}
        placeholder={needsValue ? (filter.op.endsWith('in') ? 'a, b, c' : 'Value') : 'No value needed'}
        onChange={(e) => onChange({ ...filter, value: e.target.value })}
      />
      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove filter ${n}`} onClick={onRemove}>
        <XIcon />
      </Button>
    </li>
  )
}

/** Create or edit a saved metric. Client checks run first; the API's precise messages land on the matching field. */
export function MetricForm({
  sourceId,
  tables,
  metric,
  onSaved,
  onCancel,
}: {
  sourceId: string
  tables: Table[]
  metric: MetricDefinition | null
  onSaved: (metric: MetricDefinition) => void
  onCancel: () => void
}) {
  const save = useSaveMetric(sourceId)
  const [draft, setDraft] = useState<MetricDraft>(() =>
    metric ? draftFromMetric(metric) : emptyDraft(tables.length === 1 ? tables[0].name : ''),
  )
  const [nameTouched, setNameTouched] = useState(Boolean(metric))
  const [errors, setErrors] = useState<MetricErrors>({})
  const table = tables.find((t) => t.name === draft.table)
  const columns = table ? [...table.columns].sort((a, b) => a.ordinal - b.ordinal).map((c) => c.name) : []

  const set = <K extends keyof MetricDraft>(key: K, value: MetricDraft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }))

  const setFilter = (key: string, next: FilterDraft) =>
    set(
      'filters',
      draft.filters.map((f) => (f.key === key ? next : f)),
    )

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const next = validateMetricDraft(draft)
    setErrors(next)
    if (Object.keys(next).length) return
    save.mutate(
      { metricId: metric?.id ?? null, input: toMetricInput(draft) },
      {
        onSuccess: (saved) => onSaved(saved),
        onError: (error) => {
          const message = errorMessage(error)
          const field = error instanceof ApiError && error.status === 422 ? fieldForServerError(message) : 'form'
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
      aria-label={metric ? 'Edit metric' : 'New metric'}
    >
      <FormError message={errors.form ?? null} error={errors.form ? save.error : undefined} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Label" error={errors.label}>
          {(p) => (
            <Input
              {...p}
              value={draft.label}
              placeholder="Average order value"
              maxLength={200}
              onChange={(e) => {
                const label = e.target.value
                setDraft((prev) => ({ ...prev, label, name: nameTouched ? prev.name : suggestName(label) }))
              }}
            />
          )}
        </Field>
        <Field label="Name" error={errors.name} hint="snake_case, used by the analyst to refer to it.">
          {(p) => (
            <Input
              {...p}
              value={draft.name}
              placeholder="avg_order_value"
              className="font-mono"
              spellCheck={false}
              autoComplete="off"
              maxLength={63}
              onChange={(e) => {
                setNameTouched(true)
                set('name', e.target.value)
              }}
            />
          )}
        </Field>
        <Field label="Table" error={errors.table}>
          {(p) => (
            <Select value={draft.table || undefined} onValueChange={(v) => set('table', v)}>
              <SelectTrigger
                id={p.id}
                aria-invalid={p['aria-invalid']}
                aria-describedby={p['aria-describedby']}
                className="w-full"
              >
                <SelectValue placeholder="Choose a table" />
              </SelectTrigger>
              <SelectContent>
                {tables.map((t) => (
                  <SelectItem key={t.id} value={t.name}>
                    {t.display_name || t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Format" error={errors.format}>
          {(p) => (
            <Select value={draft.format} onValueChange={(v) => set('format', v as MetricFormat)}>
              <SelectTrigger id={p.id} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {METRIC_FORMATS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>
                    {f.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field
          label="Expression"
          error={errors.expression}
          className="sm:col-span-2"
          hint={
            columns.length > 0 ? (
              <>
                One aggregate over this table. Columns:{' '}
                <span className="font-mono">{columns.slice(0, 12).join(', ')}</span>
                {columns.length > 12 ? ` and ${columns.length - 12} more` : ''}
              </>
            ) : (
              'One aggregate SQL expression, for example SUM(revenue) / COUNT(*).'
            )
          }
        >
          {(p) => (
            <Textarea
              {...p}
              rows={2}
              value={draft.expression}
              placeholder="SUM(revenue) / COUNT(*)"
              spellCheck={false}
              className="min-h-14 font-mono text-[13px] md:text-[13px]"
              data-testid="metric-expression"
              onChange={(e) => set('expression', e.target.value)}
            />
          )}
        </Field>
        <Field label="Description" optional error={errors.description} className="sm:col-span-2">
          {(p) => (
            <Textarea
              {...p}
              rows={2}
              value={draft.description}
              maxLength={2000}
              placeholder="Revenue per order, excluding refunds."
              onChange={(e) => set('description', e.target.value)}
            />
          )}
        </Field>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-foreground text-sm font-medium">
          Filters <span className="text-muted-foreground font-normal">(optional)</span>
        </legend>
        <p className="text-muted-foreground text-xs">Rows must match every filter before the expression is computed.</p>
        {draft.filters.length > 0 && (
          <ul className="flex flex-col gap-2">
            {draft.filters.map((f, i) => (
              <FilterRow
                key={f.key}
                filter={f}
                index={i}
                columns={columns}
                onChange={(next) => setFilter(f.key, next)}
                onRemove={() =>
                  set(
                    'filters',
                    draft.filters.filter((x) => x.key !== f.key),
                  )
                }
              />
            ))}
          </ul>
        )}
        {errors.filters && (
          <p className="text-danger text-xs" role="alert">
            {errors.filters}
          </p>
        )}
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!table}
            onClick={() => set('filters', [...draft.filters, newFilter()])}
          >
            <PlusIcon data-icon="inline-start" />
            Add filter
          </Button>
          {!table && <span className="text-muted-foreground ml-2 text-xs">Choose a table first.</span>}
        </div>
      </fieldset>

      <div className="flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending} data-testid="metric-save">
          {save.isPending ? 'Saving' : metric ? 'Save changes' : 'Create metric'}
        </Button>
      </div>
    </form>
  )
}
