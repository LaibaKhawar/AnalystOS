import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MetricDefinition } from '@/api/types'
import { table } from '@/test/fixtures'
import { json, mockApi, renderWithProviders, sentBody, testUser } from '@/test/utils'
import { fieldForServerError } from '@/lib/metric-form'
import { MetricForm } from './MetricForm'

afterEach(() => vi.unstubAllGlobals())

const saved: MetricDefinition = {
  id: 'met_1',
  data_source_id: 'src_1',
  table_name: 'sales',
  name: 'avg_revenue',
  label: 'Average revenue',
  description: null,
  expression: 'SUM(revenue) / COUNT(*)',
  format: 'currency',
  filters: [],
  created_at: '2026-10-01T10:00:00Z',
}

function renderForm(onSaved = vi.fn()) {
  renderWithProviders(
    <MetricForm sourceId="src_1" tables={[table()]} metric={null} onSaved={onSaved} onCancel={vi.fn()} />,
    { user: testUser() },
  )
  return { user: userEvent.setup(), onSaved }
}

describe('MetricForm validation display', () => {
  it('checks snake_case names and required fields before calling the API', async () => {
    const fetchMock = mockApi({})
    const { user } = renderForm()
    await user.type(screen.getByLabelText('Name'), 'Average Revenue')
    await user.click(screen.getByTestId('metric-save'))
    expect(screen.getByText(/Use snake_case/)).toBeInTheDocument()
    expect(screen.getByText(/Add a human readable label/)).toBeInTheDocument()
    expect(screen.getByText(/Write an aggregate expression/)).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('suggests a name from the label and shows the server message under the expression', async () => {
    mockApi({
      'POST /api/sources/src_1/metrics': () =>
        json(422, {
          error: {
            code: 'validation_failed',
            message: 'A metric must aggregate, for example SUM(...), AVG(...) or COUNT(...)',
            details: {},
          },
        }),
    })
    const { user } = renderForm()
    await user.type(screen.getByLabelText('Label'), 'Average revenue')
    expect(screen.getByLabelText('Name')).toHaveValue('average_revenue')
    await user.type(screen.getByTestId('metric-expression'), 'revenue')
    await user.click(screen.getByTestId('metric-save'))
    const message = await screen.findByText(/A metric must aggregate/)
    const expression = screen.getByTestId('metric-expression')
    expect(expression).toHaveAttribute('aria-invalid', 'true')
    expect(expression.getAttribute('aria-describedby')).toBe(message.id)
  })

  it('sends a valid metric with its filters', async () => {
    const fetchMock = mockApi({ 'POST /api/sources/src_1/metrics': () => json(201, saved) })
    const { user, onSaved } = renderForm()
    await user.type(screen.getByLabelText('Label'), 'Average revenue')
    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'avg_revenue')
    await user.type(screen.getByTestId('metric-expression'), 'SUM(revenue) / COUNT(*)')
    await user.click(screen.getByRole('button', { name: 'Add filter' }))
    await user.click(screen.getByRole('combobox', { name: 'Filter 1 column' }))
    await user.click(await screen.findByRole('option', { name: 'region' }))
    await user.type(screen.getByLabelText('Filter 1 value'), 'North')
    await user.click(screen.getByTestId('metric-save'))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved))
    expect(sentBody(fetchMock, 'POST /api/sources/src_1/metrics')).toEqual({
      name: 'avg_revenue',
      label: 'Average revenue',
      description: null,
      table: 'sales',
      expression: 'SUM(revenue) / COUNT(*)',
      format: 'number',
      filters: [{ column: 'region', op: '=', value: 'North' }],
    })
  })

  it('maps server messages to the field they describe', () => {
    expect(fieldForServerError("A metric named 'x' already exists")).toBe('name')
    expect(fieldForServerError("Unknown table 'orders'")).toBe('table')
    expect(fieldForServerError('Unknown column(s) in metric: revnue')).toBe('expression')
    expect(fieldForServerError('name: String should have at least 2 characters')).toBe('name')
    expect(fieldForServerError('Something else')).toBe('form')
  })
})
