import type { CellValue, ResultColumn } from '@/api/types'
import { formatCell } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Compact scrollable result table used for previews, result rows and evidence. */
export function DataTable({
  columns,
  rows,
  maxRows,
  masked = [],
  className,
  caption,
  maxHeight = 'max-h-80',
}: {
  columns: (string | ResultColumn)[]
  rows: CellValue[][]
  maxRows?: number
  masked?: string[]
  className?: string
  caption?: string
  maxHeight?: string
}) {
  const names = columns.map((c) => (typeof c === 'string' ? c : c.name))
  const visible = maxRows ? rows.slice(0, maxRows) : rows
  return (
    <div className={cn('min-w-0 overflow-auto rounded-lg border', maxHeight, className)}>
      <table className="w-full border-collapse text-left text-xs">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-surface-2 sticky top-0 z-10">
          <tr>
            {names.map((name) => (
              <th
                key={name}
                scope="col"
                className="text-muted-foreground border-b px-3 py-2 font-medium whitespace-nowrap"
              >
                {name}
                {masked.includes(name) && <span className="text-warning ml-1 text-[10px]">masked</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row, i) => (
            <tr key={i} className="hover:bg-muted/40 border-b last:border-b-0">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={cn(
                    'text-foreground max-w-72 truncate px-3 py-1.5 whitespace-nowrap',
                    typeof cell === 'number' && 'tabular text-right font-mono text-[11.5px]',
                    cell === null && 'text-muted-foreground',
                  )}
                  title={typeof cell === 'string' && cell.length > 40 ? cell : undefined}
                >
                  {formatCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {visible.length === 0 && <p className="text-muted-foreground px-3 py-6 text-center text-xs">No rows</p>}
    </div>
  )
}
