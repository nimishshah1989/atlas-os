import { describe, it, expect } from 'vitest'

describe('ETFMetricHistoryRow shape', () => {
  it('type has all required fields', () => {
    const row: import('../etfs').ETFMetricHistoryRow = {
      date: new Date(),
      rs_pctile_3m: '0.75',
      ret_1m: '0.04',
      ret_3m: '0.12',
      ret_6m: '0.22',
      ema_10_ratio: '1.02',
      ema_20_ratio: '1.01',
      extension_pct: '0.05',
      vol_63: '0.18',
      drawdown: '-0.08',
    }
    expect(row.date).toBeDefined()
    expect(row.ret_6m).toBeDefined()
    expect(row.extension_pct).toBeDefined()
  })
})
