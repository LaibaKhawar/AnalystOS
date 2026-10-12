import { useState } from 'react'
import type { ChartDatum } from '@/api/types'
import { useElementWidth } from '@/hooks/useElementWidth'
import { toNumber } from '@/lib/charts'
import { formatCompact, formatNumber } from '@/lib/format'

/** Heatmap grid: one teal ramp (sequential), light to dark, with a min/max legend. */
export function Heatmap({ data, xLabel, yLabel }: { data: ChartDatum[]; xLabel?: string; yLabel?: string }) {
  const [ref, width] = useElementWidth<HTMLDivElement>()
  const [hover, setHover] = useState<{ x: string; y: string; v: number | null } | null>(null)
  const xs = Array.from(new Set(data.map((d) => String(d.x))))
  const ys = Array.from(new Set(data.map((d) => String(d.y))))
  const lookup = new Map(data.map((d) => [`${String(d.x)}\u0000${String(d.y)}`, toNumber(d.value)]))
  const values = [...lookup.values()].filter((v): v is number => v !== null)
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const margin = { top: 8, right: 8, bottom: 40, left: 96 }
  const cell = Math.max(14, Math.min(44, (width - margin.left - margin.right) / Math.max(1, xs.length)))
  const cellH = Math.min(32, Math.max(16, cell * 0.75))
  const height = margin.top + ys.length * cellH + margin.bottom
  const svgWidth = Math.max(width, margin.left + xs.length * cell + margin.right)
  const shade = (v: number | null) => {
    if (v === null) return 'var(--muted)'
    const t = max === min ? 1 : (v - min) / (max - min)
    return `color-mix(in oklab, var(--chart-1) ${Math.round(12 + t * 88)}%, var(--card))`
  }
  return (
    <div ref={ref} className="relative w-full overflow-x-auto">
      <svg
        width={svgWidth}
        height={height}
        role="img"
        aria-label={`Heatmap of ${yLabel ?? 'rows'} by ${xLabel ?? 'columns'}`}
        className="recharts-surface"
      >
        {ys.map((y, yi) => (
          <text
            key={y}
            x={margin.left - 8}
            y={margin.top + yi * cellH + cellH / 2}
            dy="0.32em"
            textAnchor="end"
            fontSize={11}
            fill="var(--chart-axis)"
          >
            {y.length > 14 ? `${y.slice(0, 13)}...` : y}
          </text>
        ))}
        {xs.map((x, xi) => (
          <text
            key={x}
            x={margin.left + xi * cell + cell / 2}
            y={margin.top + ys.length * cellH + 14}
            textAnchor="middle"
            fontSize={11}
            fill="var(--chart-axis)"
          >
            {x.length > 8 ? `${x.slice(0, 7)}...` : x}
          </text>
        ))}
        {ys.map((y, yi) =>
          xs.map((x, xi) => {
            const v = lookup.get(`${x}\u0000${y}`) ?? null
            return (
              <rect
                key={`${x}-${y}`}
                x={margin.left + xi * cell + 1}
                y={margin.top + yi * cellH + 1}
                width={cell - 2}
                height={cellH - 2}
                rx={3}
                fill={shade(v)}
                onMouseEnter={() => setHover({ x, y, v })}
                onMouseLeave={() => setHover(null)}
              />
            )
          }),
        )}
      </svg>
      <div className="text-muted-foreground mt-1 flex items-center gap-2 text-[11px]">
        <span className="tabular">{formatCompact(min)}</span>
        <span
          className="h-2 w-28 rounded-xs"
          style={{
            background:
              'linear-gradient(to right, color-mix(in oklab, var(--chart-1) 12%, var(--card)), var(--chart-1))',
          }}
          aria-hidden="true"
        />
        <span className="tabular">{formatCompact(max)}</span>
      </div>
      {hover && (
        <div className="bg-popover pointer-events-none absolute top-2 right-2 rounded-lg border px-3 py-2 text-xs shadow-md">
          <p className="text-muted-foreground">
            {xLabel ?? 'x'}: <span className="text-foreground">{hover.x}</span>
          </p>
          <p className="text-muted-foreground">
            {yLabel ?? 'y'}: <span className="text-foreground">{hover.y}</span>
          </p>
          <p className="tabular text-foreground font-mono">{formatNumber(hover.v)}</p>
        </div>
      )}
    </div>
  )
}
