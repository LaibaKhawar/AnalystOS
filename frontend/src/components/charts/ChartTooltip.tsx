import { formatCell } from '@/lib/format'

interface TooltipEntry {
  name?: string | number
  value?: unknown
  color?: string
  dataKey?: string | number
}

/** Token-styled tooltip for Recharts. Text uses ink tokens; the swatch carries identity. */
export function ChartTooltip({
  active,
  payload,
  label,
  labelKey,
}: {
  active?: boolean
  payload?: readonly TooltipEntry[]
  label?: unknown
  labelKey?: string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="bg-popover min-w-36 rounded-lg border px-3 py-2 text-xs shadow-md">
      {label !== undefined && label !== null && label !== '' && (
        <p className="text-foreground mb-1.5 font-medium">
          {labelKey && <span className="text-muted-foreground mr-1">{labelKey}</span>}
          {formatCell(label)}
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {payload.map((entry, i) => (
          <li key={`${entry.dataKey ?? i}`} className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground flex items-center gap-1.5">
              <span className="size-2 rounded-xs" style={{ background: entry.color }} aria-hidden="true" />
              {String(entry.name ?? entry.dataKey ?? '')}
            </span>
            <span className="tabular text-foreground font-mono">{formatCell(entry.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
