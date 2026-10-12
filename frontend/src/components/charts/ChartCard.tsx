import {
  DownloadSimpleIcon,
  SealCheckIcon,
  TableIcon,
  ChartBarIcon,
  WarningIcon,
  InfoIcon,
} from '@phosphor-icons/react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import type { Chart } from '@/api/types'
import { saveBlob } from '@/api/client'
import { DataTable } from '@/components/common/DataTable'
import { Pill } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { chartTable, selectRenderer, seriesKeys } from '@/lib/charts'
import { serializeSvg, slugify, svgToPngBlob } from '@/lib/chart-export'
import { noDashes } from '@/lib/format'
import { BoxPlot } from './BoxPlot'
import { CartesianChart } from './CartesianChart'
import { Heatmap } from './Heatmap'

export function ChartBody({ chart, height = 280 }: { chart: Chart; height?: number }) {
  const renderer = selectRenderer(chart)
  if (renderer === 'box') return <BoxPlot data={chart.data} height={height} yLabel={chart.spec.y_label} />
  if (renderer === 'heatmap')
    return <Heatmap data={chart.data} xLabel={chart.spec.x} yLabel={chart.spec.series ?? undefined} />
  if (renderer === 'table') {
    const table = chartTable(chart.data)
    return <DataTable columns={table.columns} rows={table.rows} caption={chart.title} />
  }
  return <CartesianChart chart={chart} renderer={renderer} height={height} />
}

export function ChartCard({ chart }: { chart: Chart }) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const container = useRef<HTMLDivElement>(null)
  const renderer = selectRenderer(chart)
  const { hidden } = seriesKeys(chart)
  const canExport = view === 'chart' && renderer !== 'table'

  const exportAs = async (format: 'svg' | 'png') => {
    const svg = container.current?.querySelector<SVGSVGElement>('svg.recharts-surface')
    if (!svg) {
      toast.error('The chart is not rendered yet.')
      return
    }
    const background = getComputedStyle(document.documentElement).getPropertyValue('--card').trim() || '#ffffff'
    const text = serializeSvg(svg, background)
    const name = slugify(chart.title)
    try {
      if (format === 'svg') {
        saveBlob(new Blob([text], { type: 'image/svg+xml' }), `${name}.svg`)
      } else {
        const width = Number(svg.getAttribute('width')) || svg.clientWidth
        const height = Number(svg.getAttribute('height')) || svg.clientHeight
        saveBlob(await svgToPngBlob(text, width, height), `${name}.png`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Export failed.')
    }
  }

  const table = chartTable(chart.data)

  return (
    <figure className="bg-card min-w-0 rounded-lg border" data-testid="chart-card" data-chart-type={chart.chart_type}>
      <div className="flex flex-wrap items-start justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          <figcaption className="text-foreground text-sm font-medium">{noDashes(chart.title)}</figcaption>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {chart.verified ? (
              <Pill tone="success" icon={<SealCheckIcon weight="fill" />}>
                Data verified against source
              </Pill>
            ) : (
              <Pill tone="warning" icon={<WarningIcon weight="fill" />}>
                Not verified
              </Pill>
            )}
            <span className="text-muted-foreground text-xs">{chart.chart_type.replace('_', ' ')}</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setView((v) => (v === 'chart' ? 'table' : 'chart'))}
            aria-label={view === 'chart' ? 'Show data table' : 'Show chart'}
            title={view === 'chart' ? 'Show data table' : 'Show chart'}
          >
            {view === 'chart' ? <TableIcon /> : <ChartBarIcon />}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Export chart" disabled={!canExport}>
                <DownloadSimpleIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => void exportAs('svg')}>Download SVG</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void exportAs('png')}>Download PNG</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <div ref={container} className="px-2 pt-3 pb-2 sm:px-3">
        {view === 'chart' ? (
          <ChartBody chart={chart} />
        ) : (
          <DataTable columns={table.columns} rows={table.rows} caption={`${chart.title} data`} />
        )}
      </div>
      {(chart.spec.note || hidden > 0 || chart.interpretation) && (
        <div className="text-muted-foreground flex flex-col gap-1.5 border-t px-4 py-2.5 text-xs">
          {chart.spec.note && (
            <p className="flex items-start gap-1.5">
              <InfoIcon className="mt-0.5 size-3.5 shrink-0" />
              {noDashes(chart.spec.note)}
            </p>
          )}
          {hidden > 0 && <p>Showing 6 series. {hidden} more are in the table view.</p>}
          {chart.interpretation && <p className="text-foreground/80">{noDashes(chart.interpretation)}</p>}
        </div>
      )}
    </figure>
  )
}
