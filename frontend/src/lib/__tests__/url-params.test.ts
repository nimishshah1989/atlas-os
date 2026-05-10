import { describe, it, expect } from 'vitest'
import { validatePeriod, validateBenchmark, VALID_PERIODS, VALID_BENCHMARKS } from '@/lib/url-params'

describe('validatePeriod', () => {
  it('returns the period when in allowlist', () => {
    for (const p of VALID_PERIODS) {
      expect(validatePeriod(p)).toBe(p)
    }
  })

  it('returns default (3M) for unknown period', () => {
    expect(validatePeriod('99M')).toBe('3M')
    expect(validatePeriod('YTD')).toBe('3M')
  })

  it('returns default for undefined', () => {
    expect(validatePeriod(undefined)).toBe('3M')
  })

  it('returns default for empty string', () => {
    expect(validatePeriod('')).toBe('3M')
  })

  it('returns default for null', () => {
    expect(validatePeriod(null)).toBe('3M')
  })
})

describe('validateBenchmark', () => {
  it('returns the benchmark when in allowlist', () => {
    for (const b of VALID_BENCHMARKS) {
      expect(validateBenchmark(b)).toBe(b)
    }
  })

  it('returns default (NIFTY500) for invalid value', () => {
    expect(validateBenchmark('SENSEX')).toBe('NIFTY500')
    expect(validateBenchmark('INVALID')).toBe('NIFTY500')
  })

  it('returns default for undefined', () => {
    expect(validateBenchmark(undefined)).toBe('NIFTY500')
  })

  it('returns default for null', () => {
    expect(validateBenchmark(null)).toBe('NIFTY500')
  })
})
