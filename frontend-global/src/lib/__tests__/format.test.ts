// Pure formatters. Inputs are dates and decimal STRINGS exercising the formatting rules — no
// market figure is invented here (rule #0); the values are format fixtures, not data.
import { describe, expect, it } from 'vitest'
import { formatAsOf, formatIsoDate, formatPct, formatShortDateTime, formatUsd } from '@/lib/format'

describe('formatAsOf', () => {
  it('renders the as-of stamp in New York time', () => {
    // 01:00 UTC on 4 Sep 2026 is 21:00 on Thu 3 Sep in New York (EDT, UTC−4).
    expect(formatAsOf(new Date('2026-09-04T01:00:00Z'), 'America/New_York')).toBe('Thu 3 Sep 2026, 21:00 ET')
  })

  it('defaults to New York', () => {
    expect(formatAsOf(new Date('2026-09-04T01:00:00Z'))).toBe('Thu 3 Sep 2026, 21:00 ET')
  })

  it('labels India and pads the hour', () => {
    expect(formatAsOf(new Date('2026-01-05T03:05:00Z'), 'Asia/Kolkata')).toBe('Mon 5 Jan 2026, 08:35 IST')
  })

  it('falls back to the zone id when it has no label', () => {
    expect(formatAsOf(new Date('2026-06-30T23:30:00Z'), 'Europe/London')).toBe('Wed 1 Jul 2026, 00:30 Europe/London')
  })

  it('has a compact table form', () => {
    expect(formatShortDateTime(new Date('2026-09-04T01:00:00Z'))).toBe('3 Sep 21:00')
  })

  it('formats an ISO date without any zone shift', () => {
    expect(formatIsoDate('2026-09-03')).toBe('3 Sep 2026')
    expect(() => formatIsoDate('yesterday')).toThrow(TypeError)
  })
})

describe('formatUsd', () => {
  it('groups thousands and pads cents', () => {
    expect(formatUsd('1234.5')).toBe('$1,234.50')
    expect(formatUsd('0')).toBe('$0.00')
    expect(formatUsd('1000000')).toBe('$1,000,000.00')
  })

  it('rounds half-up on the string, keeping precision a double would lose', () => {
    expect(formatUsd('2.345')).toBe('$2.35')
    expect(formatUsd('123456789012345678.905')).toBe('$123,456,789,012,345,678.91')
  })

  it('keeps the sign, but never prints negative zero', () => {
    expect(formatUsd('-1234.5')).toBe('-$1,234.50')
    expect(formatUsd('-0.001')).toBe('$0.00')
  })

  it('honours the decimals argument', () => {
    expect(formatUsd('1234.5', 0)).toBe('$1,235')
  })

  it('renders null as an em dash and refuses malformed input', () => {
    expect(formatUsd(null)).toBe('—')
    expect(formatUsd(undefined)).toBe('—')
    expect(() => formatUsd('1,234')).toThrow(TypeError)
    expect(() => formatUsd('abc')).toThrow(TypeError)
  })
})

describe('formatPct', () => {
  it('turns a fraction into a percentage', () => {
    expect(formatPct('0.1234')).toBe('12.3%')
    expect(formatPct('1')).toBe('100.0%')
    expect(formatPct('0.00123', 2)).toBe('0.12%')
  })

  it('accepts a number too', () => {
    expect(formatPct(0.5)).toBe('50.0%')
    expect(formatPct(1e-7, 5)).toBe('0.00001%')
  })

  it('keeps the sign and adds a plus on request', () => {
    expect(formatPct('-0.0005', 2)).toBe('-0.05%')
    expect(formatPct('0.02', 1, { sign: true })).toBe('+2.0%')
    expect(formatPct('0', 1, { sign: true })).toBe('0.0%')
  })

  it('renders null as an em dash', () => {
    expect(formatPct(null)).toBe('—')
  })
})
