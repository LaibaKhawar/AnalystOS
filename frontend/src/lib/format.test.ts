import { describe, expect, it } from 'vitest'
import {
  formatBytes,
  formatCell,
  formatCompact,
  formatCost,
  formatDuration,
  formatInteger,
  formatNumber,
  formatPercent,
  formatRelative,
  humanize,
  noDashes,
} from './format'

describe('number formatting', () => {
  it('formats numbers and integers', () => {
    expect(formatNumber(2581103.62)).toBe('2,581,103.62')
    expect(formatNumber(1.23456, 3)).toBe('1.235')
    expect(formatInteger(26457)).toBe('26,457')
    expect(formatNumber(Number.NaN)).toBe('-')
    expect(formatNumber(undefined)).toBe('-')
  })

  it('formats compact values', () => {
    expect(formatCompact(2581103.62)).toBe('2.6M')
    expect(formatCompact(1500)).toBe('1.5K')
    expect(formatCompact(4.5)).toBe('4.5')
  })

  it('formats LLM cost with four decimals, local models at zero', () => {
    expect(formatCost(0)).toBe('$0.0000')
    expect(formatCost(0.012345)).toBe('$0.0123')
    expect(formatCost(null)).toBe('$0.0000')
  })

  it('formats percents from ratios or percent values', () => {
    expect(formatPercent(0.4219)).toBe('42.2%')
    expect(formatPercent(0.5)).toBe('50%')
    expect(formatPercent(1.5, 1, true)).toBe('1.5%')
    expect(formatPercent(0, 0)).toBe('0%')
  })

  it('formats durations', () => {
    expect(formatDuration(850)).toBe('850 ms')
    expect(formatDuration(4200)).toBe('4.2 s')
    expect(formatDuration(42000)).toBe('42 s')
    expect(formatDuration(90643)).toBe('1m 31s')
    expect(formatDuration(3_900_000)).toBe('1h 5m')
    expect(formatDuration(null)).toBe('-')
  })

  it('formats bytes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2323874)).toBe('2.2 MB')
    expect(formatBytes(200 * 1024 * 1024)).toBe('200 MB')
  })

  it('formats cells and relative times', () => {
    expect(formatCell(null)).toBe('-')
    expect(formatCell(2581103.620000004)).toBe('2,581,103.62')
    expect(formatCell(true)).toBe('true')
    const now = new Date('2026-10-12T12:00:00Z')
    expect(formatRelative('2026-10-12T11:30:00Z', now)).toBe('30m ago')
    expect(formatRelative('2026-10-12T11:59:50Z', now)).toBe('just now')
  })

  it('never emits en or em dashes', () => {
    expect(noDashes('Revenue — by region – 2026')).toBe('Revenue, by region, 2026')
    expect(humanize('latency_p50_ms')).toBe('Latency p50 ms')
  })
})
