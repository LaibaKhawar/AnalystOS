import { useState } from 'react'
import type { ChartDatum } from '@/api/types'
import { useElementWidth } from '@/hooks/useElementWidth'
import { toNumber } from '@/lib/charts'
import { formatCompact, formatNumber } from '@/lib/format'

interface Box {
  group: string
  min: number
  q1: number
  median: number
  q3: number
  max: number
  n: number | null
  outliers: number | null
}

function toBoxes(data: ChartDatum[]): Box[] {
  return data.flatMap((row) => {
    const nums = ['min', 'q1', 'median', 'q3', 'max'].map((k) => toNumber(row[k]))
    if (nums.some((v) => v === null)) return []
    const [min, q1, median, q3, max] = nums as number[]
    return [
      { group: String(row.group), min, q1, median, q3, max, n: toNumber(row.n), outliers: toNumber(row.outliers) },
    ]
  })
}

/** Box plot drawn as SVG: whiskers (min/max within 1.5 IQR), IQR box, median line. */
export function BoxPlot({ data, height = 280, yLabel }: { data: ChartDatum[]; height?: number; yLabel?: string }) {
  const [ref, width] = useElementWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const boxes = toBoxes(data)
  const margin = { top: 12, right: 12, bottom: 28, left: 56 }
  const innerW = Math.max(40, width - margin.left - margin.right)
  const innerH = height - margin.top - margin.bottom
  const lo = Math.min(...boxes.map((b) => b.min))
  const hi = Math.max(...boxes.map((b) => b.max))
  const pad = (hi - lo) * 0.05 || 1
  const y0 = lo - pad
  const y1 = hi + pad
  const sy = (v: number) => margin.top + innerH - ((v - y0) / (y1 - y0)) * innerH
  const band = innerW / Math.max(1, boxes.length)
  const boxW = Math.min(48, band * 0.5)
  const ticks = Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4)

  return (
    <div ref={ref} className="relative w-full">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Box plot${yLabel ? ` of ${yLabel}` : ''}`}
        className="recharts-surface"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={margin.left} x2={width - margin.right} y1={sy(t)} y2={sy(t)} stroke="var(--chart-grid)" />
            <text x={margin.left - 8} y={sy(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--chart-axis)">
              {formatCompact(t)}
            </text>
          </g>
        ))}
        {boxes.map((b, i) => {
          const cx = margin.left + band * i + band / 2
          return (
            <g
              key={b.group}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              tabIndex={0}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              aria-label={`${b.group}: median ${formatNumber(b.median)}, quartiles ${formatNumber(b.q1)} to ${formatNumber(b.q3)}`}
              className="outline-none"
            >
              <rect
                x={cx - band / 2}
                y={margin.top}
                width={band}
                height={innerH}
                fill={hover === i ? 'var(--muted)' : 'transparent'}
                opacity={0.5}
              />
              <line x1={cx} x2={cx} y1={sy(b.max)} y2={sy(b.q3)} stroke="var(--chart-axis)" strokeWidth={1.5} />
              <line x1={cx} x2={cx} y1={sy(b.q1)} y2={sy(b.min)} stroke="var(--chart-axis)" strokeWidth={1.5} />
              <line
                x1={cx - boxW / 4}
                x2={cx + boxW / 4}
                y1={sy(b.max)}
                y2={sy(b.max)}
                stroke="var(--chart-axis)"
                strokeWidth={1.5}
              />
              <line
                x1={cx - boxW / 4}
                x2={cx + boxW / 4}
                y1={sy(b.min)}
                y2={sy(b.min)}
                stroke="var(--chart-axis)"
                strokeWidth={1.5}
              />
              <rect
                x={cx - boxW / 2}
                y={sy(b.q3)}
                width={boxW}
                height={Math.max(1, sy(b.q1) - sy(b.q3))}
                rx={4}
                fill="var(--chart-1)"
                fillOpacity={0.22}
                stroke="var(--chart-1)"
                strokeWidth={1.5}
              />
              <line
                x1={cx - boxW / 2}
                x2={cx + boxW / 2}
                y1={sy(b.median)}
                y2={sy(b.median)}
                stroke="var(--chart-1)"
                strokeWidth={2.5}
              />
              <text x={cx} y={height - 8} textAnchor="middle" fontSize={11} fill="var(--chart-axis)">
                {b.group.length > 14 ? `${b.group.slice(0, 13)}...` : b.group}
              </text>
            </g>
          )
        })}
      </svg>
      {hover !== null && boxes[hover] && (
        <div className="bg-popover pointer-events-none absolute top-2 right-2 rounded-lg border px-3 py-2 text-xs shadow-md">
          <p className="text-foreground mb-1 font-medium">{boxes[hover].group}</p>
          {(['max', 'q3', 'median', 'q1', 'min'] as const).map((k) => (
            <p key={k} className="text-muted-foreground flex justify-between gap-4">
              <span>{k}</span>
              <span className="tabular text-foreground font-mono">{formatNumber(boxes[hover][k])}</span>
            </p>
          ))}
          {boxes[hover].n !== null && (
            <p className="text-muted-foreground mt-1">n = {formatNumber(boxes[hover].n, 0)}</p>
          )}
        </div>
      )}
    </div>
  )
}
