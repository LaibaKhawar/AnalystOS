import { describe, expect, it } from 'vitest'
import type { Chart } from '@/api/types'
import { chartTable, selectRenderer, seriesKeys, zeroBasedDomain } from './charts'

const base = (over: Partial<Chart>): Chart => ({
  id: 'c',
  title: 't',
  chart_type: 'bar',
  spec: { x: 'region', y: ['revenue'] },
  data: [{ region: 'A', revenue: 1 }],
  data_hash: '',
  interpretation: null,
  verified: true,
  result_table_id: null,
  ...over,
})

describe('selectRenderer', () => {
  it('maps cartesian chart types when x and y exist in the data', () => {
    for (const type of ['line', 'area', 'bar', 'stacked_bar', 'scatter'] as const) {
      expect(selectRenderer(base({ chart_type: type }))).toBe(type)
    }
  })

  it('requires label/count for histograms', () => {
    expect(selectRenderer(base({ chart_type: 'histogram', data: [{ label: '0 to 10', count: 4 }] }))).toBe('histogram')
    expect(selectRenderer(base({ chart_type: 'histogram' }))).toBe('table')
  })

  it('requires the five-number summary for box plots', () => {
    const box = { group: 'all', min: 1, q1: 2, median: 3, q3: 4, max: 5 }
    expect(selectRenderer(base({ chart_type: 'box', data: [box] }))).toBe('box')
    expect(selectRenderer(base({ chart_type: 'box', data: [{ group: 'all', median: 3 }] }))).toBe('table')
  })

  it('requires x/y/value cells for heatmaps', () => {
    expect(selectRenderer(base({ chart_type: 'heatmap', data: [{ x: 'Mon', y: 'North', value: 3 }] }))).toBe('heatmap')
  })

  it('falls back to a table for unknown types, empty data or missing columns', () => {
    expect(selectRenderer(base({ chart_type: 'pie' }))).toBe('table')
    expect(selectRenderer(base({ data: [] }))).toBe('table')
    expect(selectRenderer(base({ spec: { x: 'missing', y: ['revenue'] } }))).toBe('table')
  })
})

describe('chart helpers', () => {
  it('caps series at the validated palette size', () => {
    const y = Array.from({ length: 9 }, (_, i) => `s${i}`)
    const row = Object.fromEntries([['x', 'a'], ...y.map((k) => [k, 1])])
    expect(seriesKeys({ spec: { x: 'x', y }, data: [row] })).toEqual({ keys: y.slice(0, 6), hidden: 3 })
  })

  it('always includes zero in bar domains', () => {
    expect(zeroBasedDomain([5, 10])).toEqual([0, 10])
    expect(zeroBasedDomain([-3, 4])).toEqual([-3, 4])
    expect(zeroBasedDomain([])).toEqual([0, 1])
  })

  it('builds a table view from chart data', () => {
    expect(chartTable([{ a: 1, b: 'x' }, { a: 2 }])).toEqual({
      columns: ['a', 'b'],
      rows: [
        [1, 'x'],
        [2, null],
      ],
    })
  })
})
