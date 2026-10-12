import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartTooltip } from '@/components/charts/ChartTooltip'
import type { CategoryRate } from '@/lib/metrics'

const AXIS = { stroke: 'var(--chart-grid)', tick: { fill: 'var(--chart-axis)', fontSize: 11 }, tickLine: false }

export function PassRateChart({ data }: { data: CategoryRate[] }) {
  const rows = data.map((d) => ({ category: d.category, 'pass rate %': Math.round(d.pass_rate * 1000) / 10 }))
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          {...AXIS}
          dataKey="category"
          interval={0}
          tickFormatter={(v: string) => (v.length > 12 ? `${v.slice(0, 11)}...` : v)}
        />
        <YAxis {...AXIS} axisLine={false} width={40} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--muted)', opacity: 0.5 }} />
        <Bar
          dataKey="pass rate %"
          fill="var(--chart-1)"
          radius={[4, 4, 0, 0]}
          maxBarSize={48}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function LatencyChart({ data }: { data: { label: string; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis {...AXIS} dataKey="label" />
        <YAxis {...AXIS} axisLine={false} width={32} allowDecimals={false} />
        <Tooltip content={<ChartTooltip labelKey="from" />} cursor={{ fill: 'var(--muted)', opacity: 0.5 }} />
        <Bar dataKey="count" name="cases" fill="var(--chart-1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}
