import { describe, expect, it } from 'vitest'
import { defaultDatasetName, fileExtension, MAX_UPLOAD_BYTES, validateUpload } from './upload'

describe('validateUpload', () => {
  it('accepts csv and xlsx regardless of case', () => {
    expect(validateUpload({ name: 'sales.csv', size: 10 })).toEqual({ ok: true })
    expect(validateUpload({ name: 'Q3.XLSX', size: 10 })).toEqual({ ok: true })
  })

  it('rejects other extensions with a helpful message', () => {
    const r = validateUpload({ name: 'report.pdf', size: 10 })
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.message).toBe('report.pdf is not supported. Upload a .csv or .xlsx file.')
    expect(validateUpload({ name: 'noext', size: 10 }).ok).toBe(false)
    expect(validateUpload({ name: 'old.xls', size: 10 }).ok).toBe(false)
  })

  it('enforces the 200 MB limit and rejects empty files', () => {
    expect(validateUpload({ name: 'a.csv', size: MAX_UPLOAD_BYTES }).ok).toBe(true)
    const big = validateUpload({ name: 'a.csv', size: MAX_UPLOAD_BYTES + 1 })
    expect(big.ok).toBe(false)
    if (!big.ok) expect(big.message).toMatch(/limit is 200 MB/)
    expect(validateUpload({ name: 'a.csv', size: 0 }).ok).toBe(false)
  })

  it('derives names and extensions', () => {
    expect(fileExtension('a.b.CSV')).toBe('csv')
    expect(defaultDatasetName('q3_sales-2026.csv')).toBe('q3 sales 2026')
  })
})
