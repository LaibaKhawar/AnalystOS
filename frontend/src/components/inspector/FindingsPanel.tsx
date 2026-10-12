import { ErrorState } from '@/components/common/States'
import { Skeleton } from '@/components/ui/skeleton'
import { useFindings } from '@/hooks/queries/analyses'
import { formatCell, noDashes } from '@/lib/format'

export function FindingsPanel({ analysisId }: { analysisId: string }) {
  const findings = useFindings(analysisId)
  if (findings.isPending)
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    )
  if (findings.isError) return <ErrorState compact error={findings.error} onRetry={() => void findings.refetch()} />
  if (findings.data.length === 0)
    return (
      <p className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
        Findings are values computed by tools. They appear here as each step completes.
      </p>
    )
  return (
    <ul className="flex flex-col gap-2" aria-label="Findings">
      {findings.data.map((f) => (
        <li key={f.id} className="bg-card rounded-lg border p-3">
          <p className="text-foreground text-sm">
            <span className="text-brand-text mr-1.5 font-mono text-xs font-semibold">{f.label}</span>
            {noDashes(f.statement)}
          </p>
          {Object.keys(f.values).length > 0 && (
            <p className="text-muted-foreground mt-1 font-mono text-[11px]">
              {Object.entries(f.values)
                .map(([k, v]) => `${k} = ${formatCell(v)}`)
                .join('; ')}
            </p>
          )}
          {f.formula && <p className="text-muted-foreground mt-1 font-mono text-[11px] break-words">{f.formula}</p>}
        </li>
      ))}
    </ul>
  )
}
