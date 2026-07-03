import { describe, it, expect } from 'vitest'
import { toNumber, toNumberOr, formatINR, formatPct, signedPct } from '../decimal'

// ---------------------------------------------------------------------------
// toNumber
// ---------------------------------------------------------------------------

describe('toNumber', () => {
  it('converts a valid numeric string to number', () => {
    expect(toNumber('123.45')).toBe(123.45)
  })

  it('returns null for null input', () => {
    expect(toNumber(null)).toBeNull()
  })

  it('returns null for undefined input', () => {
    expect(toNumber(undefined)).toBeNull()
  })

  it('throws TypeError for a non-numeric string', () => {
    expect(() => toNumber('not-a-number')).toThrow(TypeError)
  })

  it('returns null for an empty string (treated as no-data)', () => {
    expect(toNumber('')).toBeNull()
  })

  it('trims whitespace before parsing', () => {
    expect(toNumber('  42.5  ')).toBe(42.5)
  })

  it('handles zero correctly', () => {
    expect(toNumber('0')).toBe(0)
  })

  it('handles negative values', () => {
    expect(toNumber('-99.99')).toBe(-99.99)
  })

  it('returns null for the "NaN" sentinel string (no-data)', () => {
    expect(toNumber('NaN')).toBeNull()
  })

  it('throws TypeError for a genuinely non-numeric string', () => {
    expect(() => toNumber('abc')).toThrow(TypeError)
  })

  it('throws TypeError for Infinity string', () => {
    expect(() => toNumber('Infinity')).toThrow(TypeError)
  })
})

// ---------------------------------------------------------------------------
// toNumberOr
// ---------------------------------------------------------------------------

describe('toNumberOr', () => {
  it('returns fallback for null', () => {
    expect(toNumberOr(null, 0)).toBe(0)
  })

  it('returns fallback for undefined', () => {
    expect(toNumberOr(undefined, -1)).toBe(-1)
  })

  it('returns parsed value when string is valid', () => {
    expect(toNumberOr('42.5', 0)).toBe(42.5)
  })

  it('still throws TypeError for invalid strings', () => {
    expect(() => toNumberOr('bad', 0)).toThrow(TypeError)
  })
})

// ---------------------------------------------------------------------------
// formatINR
// ---------------------------------------------------------------------------

describe('formatINR', () => {
  it('formats a standard amount with en-IN grouping', () => {
    // ₹12,345.67 — en-IN places commas per Indian numbering system
    expect(formatINR('12345.67')).toBe('₹12,345.67')
  })

  it('returns em-dash for null', () => {
    expect(formatINR(null)).toBe('—')
  })

  it('returns em-dash for undefined', () => {
    expect(formatINR(undefined)).toBe('—')
  })

  it('compact: true — formats crore amount', () => {
    // 12500000 = 1.25 Cr
    expect(formatINR('12500000', { compact: true })).toBe('₹1.25 Cr')
  })

  it('compact: true — formats lakh amount', () => {
    // 250000 = 2.5 L
    expect(formatINR('250000', { compact: true })).toBe('₹2.5 L')
  })

  it('compact: true — falls back to standard for amounts below 1L', () => {
    const result = formatINR('12345.67', { compact: true })
    expect(result).toBe('₹12,345.67')
  })

  it('compact: true — formats exact crore with no decimals', () => {
    expect(formatINR('10000000', { compact: true })).toBe('₹1 Cr')
  })

  it('formats large crore amounts', () => {
    // 1,23,45,678 — Indian grouping
    expect(formatINR('12345678', { compact: false })).toBe('₹1,23,45,678.00')
  })
})

// ---------------------------------------------------------------------------
// formatPct
// ---------------------------------------------------------------------------

describe('formatPct', () => {
  it('formats positive decimal fraction with + sign (default)', () => {
    expect(formatPct('0.183')).toBe('+18.3%')
  })

  it('formats negative decimal fraction without + sign', () => {
    expect(formatPct('-0.146')).toBe('-14.6%')
  })

  it('returns em-dash for null', () => {
    expect(formatPct(null)).toBe('—')
  })

  it('returns em-dash for undefined', () => {
    expect(formatPct(undefined)).toBe('—')
  })

  it('respects custom decimals option', () => {
    expect(formatPct('0.183', { decimals: 2 })).toBe('+18.30%')
  })

  it('suppresses + sign when signed: false', () => {
    expect(formatPct('0.183', { signed: false })).toBe('18.3%')
  })

  it('formats zero without + sign (zero is not positive)', () => {
    expect(formatPct('0')).toBe('0.0%')
  })

  it('renders small values correctly', () => {
    expect(formatPct('0.001')).toBe('+0.1%')
  })
})

// ---------------------------------------------------------------------------
// signedPct
// ---------------------------------------------------------------------------

describe('signedPct', () => {
  it('formats positive fraction with + sign and 2 decimals', () => {
    expect(signedPct('0.183', { decimals: 2 })).toBe('+18.30%')
  })

  it('formats negative fraction with - sign', () => {
    expect(signedPct('-0.146')).toBe('-14.6%')
  })

  it('formats zero with + prefix', () => {
    // zero is treated as non-negative, gets + prefix
    expect(signedPct('0')).toBe('+0.0%')
  })

  it('returns em-dash for null', () => {
    expect(signedPct(null)).toBe('—')
  })

  it('returns em-dash for undefined', () => {
    expect(signedPct(undefined)).toBe('—')
  })

  it('defaults to 1 decimal place', () => {
    expect(signedPct('0.183')).toBe('+18.3%')
  })

  it('respects decimals option', () => {
    expect(signedPct('0.05', { decimals: 2 })).toBe('+5.00%')
  })
})
