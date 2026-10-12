import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Chart } from '@/api/types'
import { SERIES_COLORS, seriesKeys, toNumber, zeroBasedDomain, type ChartRenderer } from '@/lib/charts'
import { formatCompact, formatCell } from '@/lib/format'
import { ChartTooltip } from './ChartTooltip'

const AXIS = { stroke: 'var(--chart-grid)', tick: { fill: 'var(--chart-axis)', fontSize: 11 }, tickLine: false }
const GRID = <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="0" vertical={false} />

function truncateTick(value: unknown): string {
  const text = formatCell(value)
  return text.length > 14 ? `${text.slice(0, 13)}...` : text
}

export function CartesianChart({
  chart,
  renderer,
  height = 280,
}: {
  chart: Chart
  renderer: ChartRenderer
  height?: number
}) {
  const { keys } = seriesKeys(chart)
  const x = chart.spec.x
  const yLabel = chart.spec.y_label
  const multi = keys.length > 1
  const legend = multi ? (
    <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 11, color: 'var(--chart-axis)' }} />
  ) : null
  const tooltip = (
    <Tooltip
      content={<ChartTooltip labelKey={chart.spec.x_label ?? x} />}
      cursor={{ fill: 'var(--muted)', opacity: 0.5 }}
    />
  )
  const values = chart.data.flatMap((row) => keys.map((k) => toNumber(row[k]) ?? 0))
  const yAxis = (domain?: [number, number]) => (
    <YAxis
      {...AXIS}
      axisLine={false}
      width={56}
      tickFormatter={(v: number) => formatCompact(v)}
      domain={domain ?? ['auto', 'auto']}
      label={
        yLabel && !multi
          ? { value: yLabel, angle: -90, position: 'insideLeft', fill: 'var(--chart-axis)', fontSize: 11, dy: 30 }
          : undefined
      }
    />
  )
  const xAxis = <XAxis {...AXIS} dataKey={x} tickFormatter={truncateTick} minTickGap={12} />

  let body: React.ReactElement
  if (renderer === 'line') {
    body = (
      <LineChart data={chart.data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        {GRID}
        {xAxis}
        {yAxis()}
        {tooltip}
        {legend}
        {keys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={SERIES_COLORS[i]}
            strokeWidth={2}
            dot={chart.data.length <= 24 ? { r: 3, strokeWidth: 0, fill: SERIES_COLORS[i] } : false}
            activeDot={{ r: 4, stroke: 'var(--card)', strokeWidth: 2 }}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    )
  } else if (renderer === 'area') {
    body = (
      <AreaChart data={chart.data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        {GRID}
        {xAxis}
        {yAxis(zeroBasedDomain(values))}
        {tooltip}
        {legend}
        {keys.map((key, i) => (
          <Area
            key={key}
            type="monotone"
            dataKey={key}
            stroke={SERIES_COLORS[i]}
            fill={SERIES_COLORS[i]}
            fillOpacity={0.15}
            strokeWidth={2}
            stackId={multi ? 'a' : undefined}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    )
  } else if (renderer === 'bar' || renderer === 'stacked_bar' || renderer === 'histogram') {
    const stacked = renderer === 'stacked_bar'
    const barKeys = renderer === 'histogram' ? ['count'] : keys
    const totals = stacked ? chart.data.map((row) => barKeys.reduce((s, k) => s + (toNumber(row[k]) ?? 0), 0)) : values
    body = (
      <BarChart
        data={chart.data}
        margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
        barCategoryGap={renderer === 'histogram' ? 1 : '20%'}
      >
        {GRID}
        <XAxis {...AXIS} dataKey={renderer === 'histogram' ? 'label' : x} tickFormatter={truncateTick} minTickGap={8} />
        {yAxis(zeroBasedDomain(renderer === 'histogram' ? chart.data.map((r) => toNumber(r.count) ?? 0) : totals))}
        {tooltip}
        {barKeys.length > 1 ? legend : null}
        {barKeys.map((key, i) => (
          <Bar
            key={key}
            dataKey={key}
            name={renderer === 'histogram' ? 'count' : key}
            fill={SERIES_COLORS[i]}
            stackId={stacked ? 's' : undefined}
            radius={stacked && i < barKeys.length - 1 ? 0 : [4, 4, 0, 0]}
            stroke="var(--card)"
            strokeWidth={stacked ? 1 : 0}
            maxBarSize={56}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    )
  } else {
    const yKey = keys[0]
    body = (
      <ScatterChart margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" />
        <XAxis
          {...AXIS}
          type="number"
          dataKey={x}
          name={x}
          tickFormatter={(v: number) => formatCompact(v)}
          domain={['auto', 'auto']}
        />
        <YAxis
          {...AXIS}
          axisLine={false}
          width={56}
          type="number"
          dataKey={yKey}
          name={yKey}
          tickFormatter={(v: number) => formatCompact(v)}
          domain={['auto', 'auto']}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ strokeDasharray: '3 3', stroke: 'var(--chart-axis)' }} />
        <Scatter
          data={chart.data}
          fill={SERIES_COLORS[0]}
          stroke="var(--card)"
          strokeWidth={1}
          isAnimationActive={false}
        />
      </ScatterChart>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      {body}
    </ResponsiveContainer>
  )
}
