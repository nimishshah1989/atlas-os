// The pure half of "create a basket": parsing the form and checking it against what the
// directory says. Limits are the seeded atlas_thresholds values as the query returns them
// (NUMERIC strings); symbols are real US-listed tickers; weights are the FM's inputs — shapes
// of a form submission, not market data (rule #0).
import { describe, expect, it } from 'vitest'
import {
  checkResolved,
  fracToMicro,
  microToFrac,
  microToPct,
  parseDraft,
  pctToMicro,
  type DraftLimits,
  type ResolvedInstrument,
} from '@/lib/basketDraft'

// scripts/global_market/seed_thresholds.py — the M2 rows, as numeric(18,6) comes back as text.
const LIMITS: DraftLimits = {
  defaultCapitalUsd: '100000.000000',
  maxPositionFrac: '0.250000',
  minWeightFrac: '0.010000',
}

const FOUR = [
  { symbol: 'SPY', weightPct: '25' },
  { symbol: 'QQQ', weightPct: '25' },
  { symbol: 'IWM', weightPct: '25' },
  { symbol: 'AGG', weightPct: '25' },
]

const resolved = (over: Partial<ResolvedInstrument> = {}, symbols = ['SPY', 'QQQ', 'IWM', 'AGG']): ResolvedInstrument[] =>
  symbols.map((symbol, i) => ({
    instrument_id: `00000000-0000-4000-8000-00000000000${i}`,
    symbol,
    asset_class: 'etf',
    name: null,
    is_active: true,
    fractionable: true,
    ...over,
  }))

describe('weights as integers', () => {
  it('turns a percentage into micro-fractions without a float deciding', () => {
    expect(pctToMicro('25')).toBe(250_000)
    expect(pctToMicro('33.33')).toBe(333_300)
    expect(pctToMicro('0.01')).toBe(100)
    expect(pctToMicro('12.3456')).toBe(123_456)
    expect(pctToMicro('12.34567')).toBeNull()
    expect(pctToMicro('abc')).toBeNull()
    expect(pctToMicro('')).toBeNull()
  })
  it('reads a threshold fraction and writes the numeric literal back', () => {
    expect(fracToMicro('0.250000')).toBe(250_000)
    expect(fracToMicro('0.01')).toBe(10_000)
    expect(fracToMicro('1')).toBe(1_000_000)
    expect(microToFrac(333_300)).toBe('0.333300')
    expect(microToFrac(1_000_000)).toBe('1.000000')
    expect(microToPct(333_300)).toBe('33.33')
    expect(microToPct(250_000)).toBe('25')
    expect(() => fracToMicro('0,25')).toThrow(TypeError)
  })
})

describe('parseDraft', () => {
  it('accepts four names at the cap summing to exactly 100', () => {
    const p = parseDraft({ name: '  Core four ', kind: 'etf', capital: '250,000', rows: FOUR }, LIMITS)
    expect(p.ok).toBe(true)
    if (!p.ok) return
    expect(p.draft.name).toBe('Core four')
    expect(p.draft.capital).toBe('250000')
    expect(p.draft.rows.map((r) => r.weightMicro)).toEqual([250_000, 250_000, 250_000, 250_000])
  })

  it('refuses a sum other than 100 — 33.3 three times is not a whole basket', () => {
    const p = parseDraft(
      { name: 'Thirds', kind: 'etf', capital: '100000', rows: [{ symbol: 'SPY', weightPct: '33.3' }, { symbol: 'QQQ', weightPct: '33.3' }, { symbol: 'IWM', weightPct: '33.3' }] },
      { ...LIMITS, maxPositionFrac: '0.500000' },
    )
    expect(p.ok).toBe(false)
    if (p.ok) return
    expect(p.errors).toEqual(['Weights sum to 99.9%; they must sum to exactly 100%.'])
  })

  it('holds each weight inside [floor, cap] and names the threshold', () => {
    const p = parseDraft(
      { name: 'Lopsided', kind: 'etf', capital: '100000', rows: [{ symbol: 'SPY', weightPct: '99.5' }, { symbol: 'QQQ', weightPct: '0.5' }] },
      LIMITS,
    )
    expect(p.ok).toBe(false)
    if (p.ok) return
    expect(p.errors).toContain('SPY: weight 99.5% is above the 25% cap (basket_max_position_pct).')
    expect(p.errors).toContain('QQQ: weight 0.5% is below the 1% floor (basket_min_weight_frac).')
  })

  it('refuses capital below the seeded default, a bad kind, a short name, a duplicate and a malformed weight', () => {
    const p = parseDraft(
      { name: 'x', kind: 'fund', capital: '99999', rows: [{ symbol: 'SPY', weightPct: '50' }, { symbol: 'spy', weightPct: '5x' }] },
      LIMITS,
    )
    expect(p.ok).toBe(false)
    if (p.ok) return
    expect(p.errors).toContain('Name must be 2–80 characters.')
    expect(p.errors).toContain('Kind must be one of etf, stock.')
    expect(p.errors).toContain('Capital must be at least $100,000 (basket_default_capital_usd).')
    expect(p.errors).toContain('SPY is listed twice.')
  })

  it('ignores blank rows and refuses an empty form', () => {
    const p = parseDraft({ name: 'Empty', kind: 'stock', capital: '100000', rows: [{ symbol: '', weightPct: '' }] }, LIMITS)
    expect(p.ok).toBe(false)
    if (p.ok) return
    expect(p.errors).toEqual(['Add at least one constituent.'])
  })
})

describe('checkResolved', () => {
  const draft = parseDraft({ name: 'Core four', kind: 'etf', capital: '100000', rows: FOUR }, LIMITS)
  if (!draft.ok) throw new Error('fixture draft must parse')

  it('maps every symbol to its active instrument and writes the fraction literal', () => {
    const c = checkResolved(draft.draft, resolved())
    expect(c.ok).toBe(true)
    if (!c.ok) return
    expect(c.constituents.map((x) => x.weight_frac)).toEqual(['0.250000', '0.250000', '0.250000', '0.250000'])
    expect(c.constituents[0].instrument_id).toBe('00000000-0000-4000-8000-000000000000')
    expect(c.notes).toEqual([])
  })

  it('refuses a symbol the directory does not have active, or of the other class', () => {
    const missing = checkResolved(draft.draft, resolved({}, ['SPY', 'QQQ', 'IWM']))
    expect(missing.ok).toBe(false)
    if (!missing.ok) expect(missing.errors).toEqual(['AGG: not an active instrument on this board.'])
    const stocks = checkResolved(draft.draft, resolved({ asset_class: 'stock' }))
    expect(stocks.ok).toBe(false)
    if (!stocks.ok) expect(stocks.errors[0]).toBe('SPY is a stock; this is a etf basket.')
  })

  it('notes, but does not refuse, a name the broker cannot fractionalise', () => {
    const c = checkResolved(draft.draft, resolved({ fractionable: false }))
    expect(c.ok).toBe(true)
    if (c.ok) expect(c.notes).toHaveLength(4)
  })
})
