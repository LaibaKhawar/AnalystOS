import { TrophyIcon } from '@phosphor-icons/react'
import { Link } from 'react-router'
import type { EvaluationRun } from '@/api/types'
import { bestIndices, COMPARE_ROWS, compareValue } from '@/lib/compare'
import { formatDateTime } from '@/lib/format'
import { formatMetric } from '@/lib/metrics'
import { cn } from '@/lib/utils'

/** Key metrics of 2 to 4 runs side by side, with the best value of each row highlighted. */
export function CompareTable({ runs }: { runs: EvaluationRun[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border" data-testid="compare-table">
      <table className="w-full min-w-[640px] text-left text-sm">
        <caption className="sr-only">Evaluation runs compared. The best value in each row is marked as best.</caption>
        <thead className="bg-surface-2 text-xs">
          <tr>
            <th scope="col" className="text-muted-foreground w-56 border-b px-3 py-2.5 font-medium">
              Metric
            </th>
            {runs.map((run) => (
              <th key={run.id} scope="col" className="border-b px-3 py-2.5 align-bottom font-medium">
                <Link to={`/evaluations/${run.id}`} className="text-foreground block hover:underline">
                  {run.suite}
                </Link>
                <span className="text-muted-foreground block font-normal">{formatDateTime(run.created_at)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {COMPARE_ROWS.map((row) => {
            const values = runs.map((run) => compareValue(run, row.key))
            const best = bestIndices(values, row.better)
            return (
              <tr key={row.key} className="border-b last:border-b-0" data-testid={`compare-row-${row.key}`}>
                <th scope="row" className="px-3 py-2 font-normal">
                  <span className="text-foreground block text-sm">{row.label}</span>
                  {row.better && (
                    <span className="text-muted-foreground block text-[11px]">
                      {row.better === 'higher' ? 'Higher is better' : 'Lower is better'}
                    </span>
                  )}
                </th>
                {values.map((value, i) => {
                  const isBest = best.has(i)
                  return (
                    <td
                      key={runs[i].id}
                      data-best={isBest || undefined}
                      className={cn(
                        'px-3 py-2',
                        row.key === 'model' ? 'text-foreground text-xs' : 'tabular font-mono text-xs',
                        isBest ? 'bg-brand-soft text-brand-text font-semibold' : 'text-foreground/90',
                      )}
                    >
                      <span className="inline-flex items-center gap-1.5">
                        {row.key === 'model'
                          ? typeof value === 'string'
                            ? value
                            : 'unknown'
                          : formatMetric(row.key, value)}
                        {isBest && (
                          <>
                            <TrophyIcon className="size-3.5" weight="fill" aria-hidden="true" />
                            <span className="sr-only">(best)</span>
                          </>
                        )}
                      </span>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
