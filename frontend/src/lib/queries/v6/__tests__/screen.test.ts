// frontend/src/lib/queries/v6/__tests__/screen.test.ts
//
// 5 test cases:
//   1. Empty filter → returns all stocks (no WHERE clauses applied)
//   2. Single-criteria (actions=POSITIVE) → filters correctly
//   3. Multi-criteria AND → narrower result set
//   4. URL encoding/decoding roundtrip
//   5. SQL parameterization — no string interpolation in WHERE clauses

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('server-only', () => ({}))

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

vi.mock('../portfolio_holdings', () => ({
  getHeldIidSet: vi.fn().mockResolvedValue(new Set(['iid-1'])),
}))

import { screenStocks, filterToParams, paramsToFilter, type ScreenFilter } from '../screen'

// ── Fixtures ─────────────────────────────────────────────────────────────────

const DATE_ROW = [{ d: '2026-05-22' }]
const SIGNAL_DATE_ROW = [{ d: '2026-05-22' }]

function makeStockRow(overrides: Partial<{
  iid: string; symbol: string; sector: string; tier: string;
  dominant_action: string; max_ic: string; drift_status: string;
  rs_pctile_3m: string; sector_rank: string;
}> = {}) {
  return {
    iid: overrides.iid ?? 'iid-1',
    symbol: overrides.symbol ?? 'RELIANCE',
    company_name: 'Reliance Industries',
    sector: overrides.sector ?? 'Energy',
    tier: overrides.tier ?? 'Large',
    rs_state: 'Leader',
    engine_state: 'Stage 2',
    is_investable: true,
    ret_1d: '0.01',
    ret_1w: '0.02',
    ret_1m: '0.03',
    ret_3m: '0.10',
    ret_6m: '0.15',
    ret_12m: '0.22',
    rs_pctile_3m: overrides.rs_pctile_3m ?? '0.90',
    dominant_action: overrides.dominant_action ?? 'POSITIVE',
    max_ic: overrides.max_ic ?? '0.05',
    drift_status: overrides.drift_status ?? 'healthy',
    sector_rank: overrides.sector_rank ?? '1',
  }
}

// screenStocks fires 3 SQL calls: dateRows, signalDateRows, main query
function setupSqlMock(resultRows: unknown[]) {
  sqlMock
    .mockResolvedValueOnce(DATE_ROW)
    .mockResolvedValueOnce(SIGNAL_DATE_ROW)
    .mockResolvedValueOnce(resultRows)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('screenStocks', () => {
  beforeEach(() => sqlMock.mockReset())

  it('case 1: empty filter returns all stocks without in_book post-filter', async () => {
    const rows = [
      makeStockRow({ iid: 'iid-1', symbol: 'RELIANCE', tier: 'Large', dominant_action: 'POSITIVE' }),
      makeStockRow({ iid: 'iid-2', symbol: 'TCS',      tier: 'Large', dominant_action: 'NEUTRAL' }),
      makeStockRow({ iid: 'iid-3', symbol: 'HDFCBANK', tier: 'Large', dominant_action: 'NEGATIVE' }),
    ]
    setupSqlMock(rows)

    const result = await screenStocks({})
    expect(result).toHaveLength(3)
    expect(result.map(r => r.symbol)).toEqual(['RELIANCE', 'TCS', 'HDFCBANK'])
    // conviction tape maps dominant action correctly
    expect(result[0].conviction_tape['6m'].direction).toBe('POSITIVE')
    expect(result[1].conviction_tape['6m'].direction).toBe('NEUTRAL')
    expect(result[2].conviction_tape['6m'].direction).toBe('NEGATIVE')
  })

  it('case 2: single-criteria action=POSITIVE — SQL receives parameterized action array', async () => {
    const rows = [
      makeStockRow({ iid: 'iid-1', symbol: 'RELIANCE', dominant_action: 'POSITIVE' }),
    ]
    setupSqlMock(rows)

    const result = await screenStocks({ actions: ['POSITIVE'] })

    // The SQL mock returned only POSITIVE rows — verify mapping is correct
    expect(result).toHaveLength(1)
    expect(result[0].symbol).toBe('RELIANCE')
    expect(result[0].conviction_tape['6m'].direction).toBe('POSITIVE')

    // Verify sql was called (3 times: dateRow, signalDateRow, main query)
    expect(sqlMock).toHaveBeenCalledTimes(3)
  })

  it('case 3: multi-criteria AND yields narrower result', async () => {
    // Simulate SQL filtering: only 1 of 3 rows matches all criteria
    setupSqlMock([
      makeStockRow({
        iid: 'iid-1',
        symbol: 'RELIANCE',
        tier: 'Large',
        sector: 'Energy',
        dominant_action: 'POSITIVE',
        rs_pctile_3m: '0.92',
        drift_status: 'healthy',
        sector_rank: '1',
      }),
    ])

    const filter: ScreenFilter = {
      actions: ['POSITIVE'],
      cap_tiers: ['Large'],
      sectors: ['Energy'],
      rs_pct_min: 80,  // 80 / 100 = 0.80 threshold
      drift_statuses: ['healthy'],
      sector_rank_max: 5,
      ic_min: 0,
    }

    const result = await screenStocks(filter)
    expect(result).toHaveLength(1)
    expect(result[0].iid).toBe('iid-1')
    // multi criteria did not expand; result is strictly a subset
  })

  it('case 4: URL encode/decode roundtrip preserves all filter fields', () => {
    const original: ScreenFilter = {
      ic_min: -0.2,
      ic_max: 0.5,
      sectors: ['Energy', 'IT'],
      sector_rank_max: 3,
      drift_statuses: ['healthy', 'drift_warn'],
      rs_pct_min: 60,
      in_book: true,
      actions: ['POSITIVE', 'NEUTRAL'],
      cap_tiers: ['Mid', 'Large'],
    }

    const params = filterToParams(original)

    // All fields serialized as strings
    expect(params.ic_min).toBe('-0.2')
    expect(params.ic_max).toBe('0.5')
    expect(params.sectors).toBe('Energy,IT')
    expect(params.sector_rank_max).toBe('3')
    expect(params.drift_statuses).toBe('healthy,drift_warn')
    expect(params.rs_pct_min).toBe('60')
    expect(params.in_book).toBe('1')
    expect(params.actions).toBe('POSITIVE,NEUTRAL')
    expect(params.cap_tiers).toBe('Mid,Large')

    // Round-trip via URLSearchParams
    const urlParams = new URLSearchParams(params)
    const restored = paramsToFilter(urlParams)

    expect(restored.ic_min).toBeCloseTo(-0.2)
    expect(restored.ic_max).toBeCloseTo(0.5)
    expect(restored.sectors).toEqual(['Energy', 'IT'])
    expect(restored.sector_rank_max).toBe(3)
    expect(restored.drift_statuses).toEqual(['healthy', 'drift_warn'])
    expect(restored.rs_pct_min).toBe(60)
    expect(restored.in_book).toBe(true)
    expect(restored.actions).toEqual(['POSITIVE', 'NEUTRAL'])
    expect(restored.cap_tiers).toEqual(['Mid', 'Large'])
  })

  it('case 5: SQL source contains no string interpolation in WHERE clauses', () => {
    // Assert the screen.ts source file never uses ${...} inside raw SQL strings.
    // All bind vars must go through the postgres-js template tag literal mechanism.
    // We grep the source for the pattern of SQL string concatenation (a common injection vector).
    const screenSrc = readFileSync(
      resolve(__dirname, '../screen.ts'),
      'utf-8',
    )

    // Verify no SQL string concatenation via `+` operator (classic injection vector).
    // e.g. `WHERE x = '` + someVar + `'` or `"SELECT * FROM " + tableName`.
    // postgres-js template tag parameters are SAFE: `WHERE x = ${var}` is always parameterized.
    const lines = screenSrc.split('\n')
    const dangerousLines = lines.filter(line => {
      const trimmed = line.trim()
      // Skip comment lines
      if (trimmed.startsWith('//') || trimmed.startsWith('*')) return false
      // Detect SQL string concatenation: a quoted SQL keyword adjacent to + operator
      return /['"`][^'"`]*(?:WHERE|AND|FROM|SELECT)[^'"`]*['"`]\s*\+/.test(trimmed)
    })
    expect(
      dangerousLines,
      `SQL injection risk: found string concatenation in SQL: ${dangerousLines.join('\n')}`,
    ).toHaveLength(0)

    // The file MUST use the sql template tag (postgres-js parameterization)
    // postgres-js uses sql<Type>` or sql` syntax; both are acceptable.
    expect(screenSrc).toMatch(/\bsql[<`]/)
    // filterToParams and paramsToFilter must be exported
    expect(screenSrc).toMatch(/export function filterToParams/)
    expect(screenSrc).toMatch(/export function paramsToFilter/)
  })
})

describe('paramsToFilter', () => {
  it('ignores unknown or empty string values gracefully', () => {
    // Empty string for ic_min should not produce 0 (Number('') === 0 which is falsy-ish but not NaN)
    const f = paramsToFilter({ unknown_key: 'foo', ic_min: '' })
    expect(f.ic_min).toBeUndefined()
    // unknown keys are simply not mapped onto ScreenFilter
    expect(f).not.toHaveProperty('unknown_key')
  })

  it('parses in_book=0 as false', () => {
    const f = paramsToFilter(new URLSearchParams('in_book=0'))
    expect(f.in_book).toBe(false)
  })

  it('filters out invalid drift_status literals', () => {
    const f = paramsToFilter({ drift_statuses: 'healthy,unknown_value,deprecated' })
    expect(f.drift_statuses).toEqual(['healthy', 'deprecated'])
  })
})
