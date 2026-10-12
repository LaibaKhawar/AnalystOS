import { ArrowClockwiseIcon, DatabaseIcon, LockKeyIcon, ShieldCheckIcon } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { ConnectionKind, DataSource } from '@/api/types'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { SourceStatusBadge } from '@/components/common/StatusBadge'
import { Field } from '@/components/forms/Field'
import { FormError } from '@/components/forms/FormError'
import { DeleteSourceButton } from '@/components/sources/DeleteSourceButton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useCreateConnection, useRefreshSource, useSources } from '@/hooks/queries/sources'
import { formatDateTime, formatInteger } from '@/lib/format'

const DEFAULT_PORT: Record<ConnectionKind, string> = { postgresql: '5432', mysql: '3306', sqlite: '' }
const KIND_LABEL: Record<ConnectionKind, string> = { postgresql: 'PostgreSQL', mysql: 'MySQL', sqlite: 'SQLite' }

interface FormState {
  name: string
  kind: ConnectionKind
  host: string
  port: string
  database: string
  username: string
  password: string
  db_schema: string
  allowed_tables: string
  restricted_columns: string
}

const EMPTY: FormState = {
  name: '',
  kind: 'postgresql',
  host: '',
  port: '5432',
  database: '',
  username: '',
  password: '',
  db_schema: '',
  allowed_tables: '',
  restricted_columns: '',
}

const splitList = (value: string) =>
  value
    .split(/[\n,]/)
    .map((v) => v.trim())
    .filter(Boolean)

function validateConnection(f: FormState): Partial<Record<keyof FormState, string>> {
  const e: Partial<Record<keyof FormState, string>> = {}
  if (!f.name.trim()) e.name = 'Give the connection a name.'
  if (!f.database.trim())
    e.database = f.kind === 'sqlite' ? 'Enter the path to the SQLite file on the server.' : 'Enter the database name.'
  if (f.kind !== 'sqlite' && !f.host.trim()) e.host = 'Enter the host name or IP address.'
  if (f.port && (!/^\d+$/.test(f.port) || Number(f.port) < 1 || Number(f.port) > 65535))
    e.port = 'Use a port between 1 and 65535.'
  const bad = splitList(f.restricted_columns).filter((c) => !/^[^.\s]+\.[^.\s]+$/.test(c))
  if (bad.length) e.restricted_columns = `Use table.column format. Check: ${bad.slice(0, 3).join(', ')}`
  return e
}

function ConnectionForm() {
  const create = useCreateConnection()
  const [f, setF] = useState<FormState>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const set = (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF((prev) => ({ ...prev, [key]: e.target.value }))
  const sqlite = f.kind === 'sqlite'

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const next = validateConnection(f)
    setErrors(next)
    if (Object.keys(next).length) return
    setFormError(null)
    create.mutate(
      {
        name: f.name.trim(),
        kind: f.kind,
        host: sqlite ? null : f.host.trim(),
        port: f.port ? Number(f.port) : null,
        database: f.database.trim(),
        username: sqlite ? null : f.username.trim() || null,
        password: sqlite ? null : f.password || null,
        db_schema: f.db_schema.trim() || null,
        allowed_tables: splitList(f.allowed_tables).length ? splitList(f.allowed_tables) : null,
        restricted_columns: splitList(f.restricted_columns),
      },
      {
        onSuccess: (source) => {
          toast.success(`Connected to ${source.name}: ${source.table_count} tables found`)
          setF(EMPTY)
        },
        onError: (error) => {
          setFormError(errorMessage(error))
          setF((prev) => ({ ...prev, password: '' }))
        },
      },
    )
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      className="bg-card flex flex-col gap-4 rounded-lg border p-4 sm:p-5"
      aria-labelledby="new-conn"
    >
      <h2 id="new-conn" className="text-foreground text-sm font-medium">
        New connection
      </h2>
      <FormError message={formError} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Name" error={errors.name}>
          {(p) => <Input {...p} value={f.name} onChange={set('name')} />}
        </Field>
        <Field label="Database type">
          {(p) => (
            <Select
              value={f.kind}
              onValueChange={(v) =>
                setF((prev) => ({ ...prev, kind: v as ConnectionKind, port: DEFAULT_PORT[v as ConnectionKind] }))
              }
            >
              <SelectTrigger id={p.id} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(KIND_LABEL) as ConnectionKind[]).map((k) => (
                  <SelectItem key={k} value={k}>
                    {KIND_LABEL[k]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        {!sqlite && (
          <Field label="Host" error={errors.host}>
            {(p) => <Input {...p} value={f.host} onChange={set('host')} autoComplete="off" spellCheck={false} />}
          </Field>
        )}
        {!sqlite && (
          <Field label="Port" error={errors.port}>
            {(p) => <Input {...p} inputMode="numeric" value={f.port} onChange={set('port')} />}
          </Field>
        )}
        <Field
          label={sqlite ? 'File path on the server' : 'Database'}
          error={errors.database}
          className={sqlite ? 'sm:col-span-2' : undefined}
        >
          {(p) => <Input {...p} value={f.database} onChange={set('database')} spellCheck={false} />}
        </Field>
        {!sqlite && (
          <Field label="Schema" optional>
            {(p) => <Input {...p} value={f.db_schema} onChange={set('db_schema')} spellCheck={false} />}
          </Field>
        )}
        {!sqlite && (
          <Field label="Username" optional>
            {(p) => (
              <Input {...p} value={f.username} onChange={set('username')} autoComplete="off" spellCheck={false} />
            )}
          </Field>
        )}
        {!sqlite && (
          <Field label="Password" optional hint="Encrypted at rest and never shown again.">
            {(p) => (
              <Input {...p} type="password" value={f.password} onChange={set('password')} autoComplete="new-password" />
            )}
          </Field>
        )}
        <Field
          label="Allowed tables"
          optional
          hint="Comma separated. Leave empty to allow every table."
          className="sm:col-span-2"
        >
          {(p) => <Input {...p} value={f.allowed_tables} onChange={set('allowed_tables')} spellCheck={false} />}
        </Field>
        <Field
          label="Restricted columns"
          optional
          hint="Comma separated table.column entries, hidden from the analyst as PII."
          error={errors.restricted_columns}
          className="sm:col-span-2"
        >
          {(p) => <Input {...p} value={f.restricted_columns} onChange={set('restricted_columns')} spellCheck={false} />}
        </Field>
      </div>
      <div className="flex justify-end">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? 'Testing connection' : 'Test and save'}
        </Button>
      </div>
    </form>
  )
}

function ConnectionRow({ source }: { source: DataSource }) {
  const refresh = useRefreshSource()
  return (
    <li className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <DatabaseIcon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
        <div className="min-w-0">
          <Link
            to={`/sources/${source.id}`}
            className="text-foreground block truncate text-sm font-medium hover:underline"
          >
            {source.name}
          </Link>
          <p className="text-muted-foreground truncate text-xs">
            {KIND_LABEL[source.kind as ConnectionKind] ?? source.kind}
            {source.host ? `, ${source.username ? `${source.username}@` : ''}${source.host}:${source.port ?? ''}` : ''}
            {source.database ? `/${source.database}` : ''}, {formatInteger(source.table_count)} tables
          </p>
          <p className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px]">
            <span>Last checked {formatDateTime(source.last_checked_at)}</span>
            {source.has_password && (
              <span className="inline-flex items-center gap-1">
                <LockKeyIcon className="size-3" /> Password stored encrypted
              </span>
            )}
            {source.restricted_columns.length > 0 && <span>{source.restricted_columns.length} restricted columns</span>}
          </p>
          {source.error && <p className="text-danger mt-1 text-xs">{source.error}</p>}
          {refresh.isError && refresh.variables === source.id && (
            <p className="text-danger mt-1 text-xs" role="alert">
              {errorMessage(refresh.error)}
            </p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 pl-7 sm:pl-0">
        <SourceStatusBadge status={source.status} />
        <Button
          variant="outline"
          size="sm"
          disabled={refresh.isPending}
          onClick={() => refresh.mutate(source.id, { onSuccess: () => toast.success(`${source.name} refreshed`) })}
        >
          <ArrowClockwiseIcon
            data-icon="inline-start"
            className={refresh.isPending ? 'motion-safe:animate-spin' : undefined}
          />
          {refresh.isPending ? 'Checking' : 'Refresh'}
        </Button>
        <DeleteSourceButton source={source} />
      </div>
    </li>
  )
}

export default function Connections() {
  const sources = useSources()
  const connections = sources.data?.filter((s) => s.kind !== 'file') ?? []
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Connections"
        description="Query PostgreSQL, MySQL or SQLite in place. AnalystOS reads schema and runs validated, read-only SELECT queries."
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <ConnectionForm />
        <aside className="bg-muted/30 flex flex-col gap-4 self-start rounded-lg border p-5 text-sm">
          <div className="flex items-start gap-3">
            <LockKeyIcon className="text-brand mt-0.5 size-4 shrink-0" />
            <p className="text-muted-foreground">
              <span className="text-foreground font-medium">Credentials are encrypted.</span> Passwords are stored with
              symmetric encryption, never returned by the API and never shown in this interface.
            </p>
          </div>
          <div className="flex items-start gap-3">
            <ShieldCheckIcon className="text-brand mt-0.5 size-4 shrink-0" />
            <p className="text-muted-foreground">
              <span className="text-foreground font-medium">Connections are read-only.</span> Every query is parsed and
              validated before it runs: single SELECT statements only, a row limit and a timeout. Writes and DDL are
              rejected.
            </p>
          </div>
          <p className="text-muted-foreground text-xs">
            Tip: use a database user with read-only grants and list restricted columns for anything personal.
          </p>
        </aside>
      </div>
      <section aria-labelledby="conn-list" className="flex flex-col gap-3">
        <h2 id="conn-list" className="text-foreground text-sm font-medium">
          Saved connections
        </h2>
        {sources.isPending && <Skeleton className="h-28" />}
        {sources.isError && <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />}
        {sources.data && connections.length === 0 && (
          <EmptyState
            icon={<DatabaseIcon className="size-4" />}
            title="No connections yet"
            description="Fill in the form above. The connection is tested and its schema is profiled before it is saved."
          />
        )}
        {connections.length > 0 && (
          <ul className="bg-card divide-y rounded-lg border">
            {connections.map((s) => (
              <ConnectionRow key={s.id} source={s} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
