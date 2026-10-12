import { ShareNetworkIcon, TrashIcon, UsersIcon } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { DataSource, ShareRole, SourceShare } from '@/api/types'
import { ErrorState } from '@/components/common/States'
import { Field } from '@/components/forms/Field'
import { FormError } from '@/components/forms/FormError'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useShareSource, useShares, useUnshareSource } from '@/hooks/queries/sources'
import { isEmail } from '@/lib/validation'

const SHARE_ROLES: { value: ShareRole; label: string; hint: string }[] = [
  { value: 'viewer', label: 'Viewer', hint: 'Reads the schema, profile, preview and metrics.' },
  { value: 'analyst', label: 'Analyst', hint: 'Also asks questions and schedules analyses.' },
]

function RoleSelect({
  id,
  value,
  onChange,
  disabled,
  label,
}: {
  id?: string
  value: string
  onChange: (role: ShareRole) => void
  disabled?: boolean
  label?: string
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as ShareRole)} disabled={disabled}>
      <SelectTrigger id={id} aria-label={label} className="w-full sm:w-32">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {SHARE_ROLES.map((r) => (
          <SelectItem key={r.value} value={r.value}>
            {r.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function ShareRow({ sourceId, share }: { sourceId: string; share: SourceShare }) {
  const update = useShareSource(sourceId)
  const remove = useUnshareSource(sourceId)
  const busy = update.isPending || remove.isPending
  return (
    <li className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:gap-3" data-testid="share-row">
      <div className="min-w-0 flex-1">
        <p className="text-foreground truncate text-sm font-medium">{share.name}</p>
        <p className="text-muted-foreground truncate text-xs">{share.email}</p>
        {(update.isError || remove.isError) && (
          <p className="text-danger mt-1 text-xs" role="alert">
            {errorMessage(update.error ?? remove.error)}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2">
        <RoleSelect
          label={`Access for ${share.email}`}
          value={share.role}
          disabled={busy}
          onChange={(role) =>
            update.mutate(
              { email: share.email, role },
              { onSuccess: () => toast(`${share.name} is now ${role === 'analyst' ? 'an analyst' : 'a viewer'}`) },
            )
          }
        />
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Remove access for ${share.email}`}
          disabled={busy}
          onClick={() => remove.mutate(share.id, { onSuccess: () => toast(`Access removed for ${share.email}`) })}
        >
          <TrashIcon />
        </Button>
      </div>
    </li>
  )
}

function ShareForm({ sourceId }: { sourceId: string }) {
  const share = useShareSource(sourceId)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<ShareRole>('viewer')
  const [emailError, setEmailError] = useState<string | null>(null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const value = email.trim()
    if (!isEmail(value)) {
      setEmailError('Enter the email address of an existing AnalystOS account.')
      return
    }
    setEmailError(null)
    share.mutate(
      { email: value, role },
      {
        onSuccess: (s) => {
          toast.success(`Shared with ${s.name}`)
          setEmail('')
        },
      },
    )
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3" aria-label="Share with someone">
      {share.isError && <FormError error={share.error} />}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <Field label="Email" error={emailError} className="flex-1">
          {(p) => (
            <Input
              {...p}
              type="email"
              autoComplete="off"
              spellCheck={false}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@company.com"
            />
          )}
        </Field>
        <Field label="Access">{(p) => <RoleSelect id={p.id} value={role} onChange={setRole} />}</Field>
      </div>
      <p className="text-muted-foreground text-xs">{SHARE_ROLES.find((r) => r.value === role)?.hint}</p>
      <div className="flex justify-end">
        <Button type="submit" disabled={share.isPending}>
          {share.isPending ? 'Sharing' : 'Share'}
        </Button>
      </div>
    </form>
  )
}

function ShareList({ sourceId, enabled }: { sourceId: string; enabled: boolean }) {
  const shares = useShares(sourceId, enabled)
  if (shares.isPending)
    return (
      <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading people with access">
        <Skeleton className="h-10" />
        <Skeleton className="h-10" />
      </div>
    )
  if (shares.isError) return <ErrorState compact error={shares.error} onRetry={() => void shares.refetch()} />
  if (shares.data.length === 0)
    return (
      <p className="text-muted-foreground flex items-center gap-2 text-sm">
        <UsersIcon className="size-4" />
        Not shared with anyone yet. Only you and admins can see it.
      </p>
    )
  return (
    <ul className="divide-y" aria-label="People with access">
      {shares.data.map((s) => (
        <ShareRow key={s.id} sourceId={sourceId} share={s} />
      ))}
    </ul>
  )
}

/** Owner-only dialog to share a data source by email as viewer or analyst, and to change or revoke access. */
export function ShareDialog({ source }: { source: Pick<DataSource, 'id' | 'name'> }) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" data-testid="share-source">
          <ShareNetworkIcon data-icon="inline-start" />
          Share
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg" data-testid="share-dialog">
        <DialogHeader>
          <DialogTitle>Share {source.name}</DialogTitle>
          <DialogDescription>
            People you add see this source in their list. You stay the owner: only you can edit columns, metrics and
            sharing, or delete it.
          </DialogDescription>
        </DialogHeader>
        <ShareForm sourceId={source.id} />
        <section aria-labelledby="share-list-title" className="flex flex-col gap-2 border-t pt-3">
          <h3 id="share-list-title" className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
            People with access
          </h3>
          <ShareList sourceId={source.id} enabled={open} />
        </section>
      </DialogContent>
    </Dialog>
  )
}
