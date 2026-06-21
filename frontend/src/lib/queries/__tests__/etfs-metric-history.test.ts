import { describe, it, expect, vi, beforeEach } from 'vitest'

// Hoisted mocks — no top-level variable references inside vi.mock factories
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import sql from '@/lib/db'
import { getETFMetricHistory } from '@/lib/queries/etfs'

// Capture the SQL text from the most recent tagged-template call to `sql`.
function capturedSql(): string {
  const mock = sql as unknown as { mock: { calls: unknown[][] } }
  const strings = mock.mock.calls[0][0] as readonly string[]
  return strings.join('?')
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(sql as unknown as { mockReturnValue: (v: unknown) => void }).mockReturnValue(
    Promise.resolve([]),
  )
})

describe('ETFMetricHistoryRow shape', () => {
  it('type has all required fields incl ret_1w', () => {
    // Drift guard: this literal must satisfy the full ETFMetricHistoryRow type.
    // Previously it omitted rs_3m_benchmark / ret_12m / volume_expansion /
    // above_30w_ma, masking type drift under tsc.
    const row: import('../etfs').ETFMetricHistoryRow = {
      date: new Date(),
      rs_pctile_3m: '0.75',
      rs_3m_benchmark: '0.61',
      ret_1w: '0.012',
      ret_1m: '0.04',
      ret_3m: '0.12',
      ret_6m: '0.22',
      ret_12m: '0.31',
      ema_10_ratio: '1.02',
      ema_20_ratio: '1.01',
      extension_pct: '0.05',
      vol_63: '0.18',
      drawdown: '-0.08',
      volume_expansion: '1.3',
      above_30w_ma: true,
    }
    expect(row.date).toBeDefined()
    expect(row.ret_1w).toBeDefined()
    expect(row.ret_6m).toBeDefined()
    expect(row.extension_pct).toBeDefined()
  })
})

describe('getETFMetricHistory', () => {
  it('selects ret_1w so the 1W row in ETFReturnsTable is populated, not em-dash', async () => {
    // Regression: ETFReturnsTable has a 1W row reading latest.ret_1w, but the
    // history query omitted ret_1w from its SELECT, so 1W always rendered "—".
    await getETFMetricHistory('NIFTYBEES', 365)
    expect(capturedSql()).toMatch(/ret_1w/)
  })

  it('still selects the existing horizons (1m/3m/6m/12m)', async () => {
    await getETFMetricHistory('NIFTYBEES', 365)
    const text = capturedSql()
    expect(text).toMatch(/ret_1m/)
    expect(text).toMatch(/ret_3m/)
    expect(text).toMatch(/ret_6m/)
    expect(text).toMatch(/ret_12m/)
  })
})
