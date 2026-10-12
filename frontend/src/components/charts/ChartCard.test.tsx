import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Chart } from '@/api/types'
import { renderWithProviders } from '@/test/utils'
import { ChartCard } from './ChartCard'

const chart: Chart = {
  id: 'c1',
  title: 'Revenue by region',
  chart_type: 'bar',
  spec: { x: 'region', y: ['revenue'], note: 'Values vary by less than 5%' },
  data: [
    { region: 'Karachi', revenue: 2581103.62 },
    { region: 'Lahore', revenue: 1923494.92 },
  ],
  data_hash: 'h',
  interpretation: null,
  verified: true,
  result_table_id: 'r1',
}

describe('ChartCard', () => {
  it('shows the verified flag, note and a table view toggle', async () => {
    renderWithProviders(<ChartCard chart={chart} />)
    expect(screen.getByText('Data verified against source')).toBeInTheDocument()
    expect(screen.getByText('Values vary by less than 5%')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show data table' }))
    expect(screen.getByRole('table', { name: 'Revenue by region data' })).toBeInTheDocument()
    expect(screen.getByText('Karachi')).toBeInTheDocument()
  })

  it('falls back to a table for unrenderable specs and flags unverified data', () => {
    renderWithProviders(<ChartCard chart={{ ...chart, chart_type: 'pie', verified: false }} />)
    expect(screen.getByText('Not verified')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Revenue by region' })).toBeInTheDocument()
  })
})
