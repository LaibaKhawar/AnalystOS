import type { ReactNode } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function StatTile({
  label,
  value,
  hint,
  icon,
  loading,
  className,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  loading?: boolean
  className?: string
}) {
  return (
    <div className={cn('bg-card flex min-w-0 flex-col gap-2 rounded-lg border p-4', className)}>
      <div className="text-muted-foreground flex items-center justify-between gap-2 text-xs">
        <span className="truncate">{label}</span>
        {icon && <span className="text-muted-foreground [&_svg]:size-4">{icon}</span>}
      </div>
      {loading ? (
        <Skeleton className="h-7 w-20" />
      ) : (
        <div className="tabular text-foreground truncate text-2xl font-semibold tracking-[-0.02em]">{value}</div>
      )}
      {hint && !loading && <div className="text-muted-foreground truncate text-xs">{hint}</div>}
      {loading && <Skeleton className="h-3 w-24" />}
    </div>
  )
}

export function KeyValue({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex min-w-0 items-baseline justify-between gap-3 py-1.5 text-sm', className)}>
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd className="text-foreground min-w-0 truncate text-right">{children}</dd>
    </div>
  )
}
