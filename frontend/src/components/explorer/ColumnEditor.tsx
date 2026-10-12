import { PencilSimpleIcon } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { Column, ColumnRole } from '@/api/types'
import { Field } from '@/components/forms/Field'
import { FormError } from '@/components/forms/FormError'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { usePatchColumn } from '@/hooks/queries/sources'

const ROLES: ColumnRole[] = ['metric', 'dimension', 'time', 'identifier', 'text', 'other']

export function ColumnEditor({ sourceId, column }: { sourceId: string; column: Column }) {
  const [open, setOpen] = useState(false)
  const [semantic, setSemantic] = useState(column.semantic_type ?? '')
  const [role, setRole] = useState<string>(column.role)
  const [pii, setPii] = useState(column.is_pii)
  const [error, setError] = useState<string | null>(null)
  const patch = usePatchColumn(sourceId)

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) {
      setSemantic(column.semantic_type ?? '')
      setRole(column.role)
      setPii(column.is_pii)
      setError(null)
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const body: { semantic_type?: string; role?: ColumnRole; is_pii?: boolean } = {}
    if (semantic.trim() && semantic.trim() !== column.semantic_type) body.semantic_type = semantic.trim()
    if (role !== column.role) body.role = role as ColumnRole
    if (pii !== column.is_pii) body.is_pii = pii
    if (Object.keys(body).length === 0) {
      setOpen(false)
      return
    }
    patch.mutate(
      { columnId: column.id, patch: body },
      {
        onSuccess: () => {
          toast.success(`Updated ${column.name}`)
          setOpen(false)
        },
        onError: (e) => setError(errorMessage(e)),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon-xs" aria-label={`Edit ${column.name}`}>
          <PencilSimpleIcon />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Edit column {column.name}</DialogTitle>
            <DialogDescription>
              Corrections are used by the planner on the next question. Your edits are marked as user-confirmed.
            </DialogDescription>
          </DialogHeader>
          <FormError message={error} />
          <Field label="Semantic type" hint="For example currency_metric, date, customer_id.">
            {(p) => <Input {...p} value={semantic} onChange={(e) => setSemantic(e.target.value)} spellCheck={false} />}
          </Field>
          <Field label="Role">
            {(p) => (
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger id={p.id} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
          <div className="flex items-center justify-between gap-4 rounded-lg border px-3 py-2.5">
            <div>
              <label htmlFor={`pii-${column.id}`} className="text-foreground text-sm font-medium">
                Personal data (PII)
              </label>
              <p className="text-muted-foreground text-xs">
                PII columns are masked in previews and hidden from analysis.
              </p>
            </div>
            <Switch id={`pii-${column.id}`} checked={pii} onCheckedChange={setPii} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={patch.isPending}>
              {patch.isPending ? 'Saving' : 'Save changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
