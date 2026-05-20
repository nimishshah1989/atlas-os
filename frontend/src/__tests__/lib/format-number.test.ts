// Tests for src/lib/format-number.ts
// Covers formatThreshold (existing), formatPct (A2), formatRank (A2).

import { describe, it, expect } from 'vitest'
import { formatThreshold, formatPct, formatRank } from '@/lib/format-number'

describe('formatThreshold (existing)', () => {
  it('trims trailing zeros but keeps at least 2 decimals', () => {
    expect(formatThreshold('0.200000')).toBe('0.20')
    expect(formatThreshold('8.000000')).toBe('8.00')
    expect(formatThreshold('0.005000')).toBe('0.005')
  })

  it('returns "—" for null/undefined', () => {
    expect(formatThreshold(null)).toBe('—')
    expect(formatThreshold(undefined)).toBe('—')
  })
})

describe('formatPct (A2)', () => {
  it('trims trailing zeros and adds % suffix', () => {
    expect(formatPct('5.0000')).toBe('5%')
    expect(formatPct('15.0000')).toBe('15%')
    expect(formatPct('30.0000')).toBe('30%')
    expect(formatPct('8.0000')).toBe('8%')
  })

  it('preserves one decimal when non-zero', () => {
    expect(formatPct('8.5000')).toBe('8.5%')
    expect(formatPct('12.5')).toBe('12.5%')
  })

  it('handles numeric input', () => {
    expect(formatPct(5)).toBe('5%')
    expect(formatPct(8.5)).toBe('8.5%')
  })

  it('returns "—" for null/undefined', () => {
    expect(formatPct(null)).toBe('—')
    expect(formatPct(undefined)).toBe('—')
  })
})

describe('formatRank (A2)', () => {
  it('formats rank to exactly 2 decimal places', () => {
    expect(formatRank('0.600000')).toBe('0.60')
    expect(formatRank('0.700000')).toBe('0.70')
    expect(formatRank('0.60')).toBe('0.60')
  })

  it('handles numeric input', () => {
    expect(formatRank(0.6)).toBe('0.60')
    expect(formatRank(0.7)).toBe('0.70')
  })

  it('returns "—" for null/undefined', () => {
    expect(formatRank(null)).toBe('—')
    expect(formatRank(undefined)).toBe('—')
  })
})
