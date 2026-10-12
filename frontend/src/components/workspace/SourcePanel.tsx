import {
  ArrowCounterClockwiseIcon,
  CaretDownIcon,
  DatabaseIcon,
  PlusIcon,
  TableIcon,
  XIcon,
} from '@phosphor-icons/react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { Column, Conversation, DataSource, Table } from '@/api/types'
import { ErrorState } from '@/components/common/States'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useConversations, useCreateConversation, useResetContext } from '@/hooks/queries/conversations'
import { useTables } from '@/hooks/queries/sources'
import { formatCell, formatInteger, formatRelative, noDashes } from '@/lib/format'
import { cn } from '@/lib/utils'

const ROLE_ORDER = ['metric', 'dimension', 'time', 'identifier', 'text', 'other']
const ROLE_LABEL: Record<string, string> = {
  metric: 'Metrics',
  dimension: 'Dimensions',
  time: 'Time',
  identifier: 'Identifiers',
  text: 'Text',
  other: 'Other',
}

function TableTree({ table, defaultOpen }: { table: Table; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const groups = ROLE_ORDER.map((role) => ({
    role,
    columns: table.columns.filter((c: Column) => (ROLE_ORDER.includes(c.role) ? c.role : 'other') === role),
  })).filter((g) => g.columns.length)
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="hover:bg-muted/60 focus-visible:ring-ring/60 flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-sm outline-none focus-visible:ring-2"
      >
        <CaretDownIcon className={cn('text-muted-foreground size-3 transition-transform', !open && '-rotate-90')} />
        <TableIcon className="text-muted-foreground size-3.5" />
        <span className="text-foreground truncate font-medium">{table.display_name || table.name}</span>
        <span className="tabular text-muted-foreground ml-auto text-[11px]">{formatInteger(table.row_count)}</span>
      </button>
      {open && (
        <div className="mt-1 mb-2 ml-5 flex flex-col gap-2">
          {groups.map((g) => (
            <div key={g.role}>
              <p className="text-muted-foreground text-[10.5px] font-medium tracking-wide uppercase">
                {ROLE_LABEL[g.role]}
              </p>
              <ul className="mt-0.5">
                {g.columns.map((c) => (
                  <li
                    key={c.id}
                    className="flex items-center justify-between gap-2 py-0.5 text-xs"
                    title={c.original_name}
                  >
                    <span className="text-foreground/90 truncate font-mono">{c.name}</span>
                    <span className="text-muted-foreground shrink-0 text-[10.5px]">
                      {c.is_pii ? 'PII' : c.inferred_type}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </li>
  )
}

function contextChips(conversation: Conversation): { key: string; label: string }[] {
  const s = conversation.state ?? {}
  const chips: { key: string; label: string }[] = []
  if (s.metric) chips.push({ key: 'metric', label: `Metric: ${s.metric}` })
  if (s.dimension) chips.push({ key: 'dimension', label: `By: ${s.dimension}` })
  if (s.period) chips.push({ key: 'period', label: `Period: ${s.period}` })
  ;(s.filters ?? []).forEach((f, i) => {
    const value = Array.isArray(f.value) ? f.value.map((v) => formatCell(v)).join(' and ') : formatCell(f.value)
    chips.push({ key: `f${i}`, label: `${f.column ?? 'filter'} ${f.op ?? '='} ${value}` })
  })
  return chips
}

export function ContextChips({ conversation }: { conversation: Conversation }) {
  const reset = useResetContext()
  const chips = contextChips(conversation)
  return (
    <section aria-labelledby="ctx-title">
      <div className="mb-1.5 flex items-center justify-between">
        <h2 id="ctx-title" className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
          Active context
        </h2>
        <Button
          variant="ghost"
          size="xs"
          disabled={chips.length === 0 || reset.isPending}
          onClick={() =>
            reset.mutate(conversation.id, {
              onSuccess: () => toast('Context cleared. The next question starts fresh.'),
              onError: (e) => toast.error(errorMessage(e)),
            })
          }
        >
          <ArrowCounterClockwiseIcon data-icon="inline-start" />
          Reset context
        </Button>
      </div>
      {chips.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          Nothing carried over yet. Metrics, groupings and periods you ask about carry over to follow-up questions.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-1.5" data-testid="context-chips">
          {chips.map((c) => (
            <li
              key={c.key}
              className="bg-muted/50 text-foreground inline-flex max-w-full items-center gap-1 rounded-md border py-0.5 pr-1 pl-2 text-[11px]"
            >
              <span className="truncate">{c.label}</span>
              <XIcon className="text-muted-foreground size-3" aria-hidden="true" />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function SourcePanel({ source, conversation }: { source: DataSource | undefined; conversation: Conversation }) {
  const navigate = useNavigate()
  const tables = useTables(conversation.data_source_id)
  const conversations = useConversations(conversation.data_source_id)
  const create = useCreateConversation()

  const newConversation = () =>
    create.mutate(
      { sourceId: conversation.data_source_id },
      { onSuccess: (c) => navigate(`/workspace/${c.id}`), onError: (e) => toast.error(errorMessage(e)) },
    )

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="src-title">
        <h2 id="src-title" className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
          Data source
        </h2>
        {source ? (
          <Link
            to={`/sources/${source.id}`}
            className="bg-card hover:border-foreground/20 focus-visible:ring-ring/60 mt-1.5 flex items-center gap-2 rounded-lg border px-2.5 py-2 outline-none focus-visible:ring-2"
            data-testid="selected-source"
          >
            {source.kind === 'file' ? (
              <TableIcon className="text-brand size-4" />
            ) : (
              <DatabaseIcon className="text-brand size-4" />
            )}
            <span className="min-w-0">
              <span className="text-foreground block truncate text-sm font-medium">{source.name}</span>
              <span className="text-muted-foreground block text-[11px]">
                {source.kind === 'file' ? (source.file_type ?? 'file').toUpperCase() : source.kind},{' '}
                {formatInteger(source.row_count)} rows
              </span>
            </span>
          </Link>
        ) : (
          <Skeleton className="mt-1.5 h-12" />
        )}
        <div className="mt-3">
          {tables.isPending && <Skeleton className="h-24" />}
          {tables.isError && <ErrorState compact error={tables.error} onRetry={() => void tables.refetch()} />}
          {tables.data && (
            <ul className="flex flex-col">
              {tables.data.map((t, i) => (
                <TableTree key={t.id} table={t} defaultOpen={i === 0} />
              ))}
            </ul>
          )}
        </div>
      </section>

      <ContextChips conversation={conversation} />

      <section aria-labelledby="conv-title">
        <div className="mb-1.5 flex items-center justify-between">
          <h2 id="conv-title" className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
            Conversations
          </h2>
          <Button variant="ghost" size="xs" onClick={newConversation} disabled={create.isPending}>
            <PlusIcon data-icon="inline-start" />
            New
          </Button>
        </div>
        {conversations.isPending && <Skeleton className="h-20" />}
        {conversations.isError && (
          <ErrorState compact error={conversations.error} onRetry={() => void conversations.refetch()} />
        )}
        {conversations.data && (
          <ul className="flex flex-col gap-0.5">
            {conversations.data.map((c) => (
              <li key={c.id}>
                <Link
                  to={`/workspace/${c.id}`}
                  aria-current={c.id === conversation.id ? 'page' : undefined}
                  className={cn(
                    'focus-visible:ring-ring/60 block rounded-md px-2 py-1.5 text-sm outline-none focus-visible:ring-2',
                    c.id === conversation.id
                      ? 'bg-muted text-foreground font-medium'
                      : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                  )}
                >
                  <span className="block truncate">{noDashes(c.title)}</span>
                  <span className="text-muted-foreground block text-[11px]">{formatRelative(c.updated_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
