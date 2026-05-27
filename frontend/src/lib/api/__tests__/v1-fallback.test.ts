import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  getScreenStocks,
  getCellDefinitions,
  getMarketRegime,
  getScreenSectors,
  getScreenEtfs,
  getScreenFunds,
} from '../v1'

const originalFetch = global.fetch

beforeEach(() => {
  // Default: 404 — exercises the fallback.
  global.fetch = vi.fn(async () => new Response('', { status: 404 })) as never
})

afterEach(() => {
  global.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('/v1 API client — graceful fallback', () => {
  it('getScreenStocks falls back to demo when endpoint 404s', async () => {
    const res = await getScreenStocks()
    expect(res.source_kind).toBe('demo')
    expect(res.data.length).toBeGreaterThan(0)
    expect(res.data[0]).toHaveProperty('symbol')
    expect(res.data[0]).toHaveProperty('conviction_tape')
  })

  it('getCellDefinitions falls back and returns 24 cells', async () => {
    const res = await getCellDefinitions()
    expect(res.source_kind).toBe('demo')
    expect(res.data).toHaveLength(24)
  })

  it('getMarketRegime falls back and returns 252d history', async () => {
    const res = await getMarketRegime()
    expect(res.source_kind).toBe('demo')
    expect(res.data.history).toHaveLength(252)
    expect(res.data.cells_favored.length).toBeGreaterThan(0)
  })

  it('getScreenSectors falls back and returns 30 sectors', async () => {
    const res = await getScreenSectors()
    expect(res.source_kind).toBe('demo')
    expect(res.data).toHaveLength(30)
  })

  it('falls back when fetch throws (network failure)', async () => {
    global.fetch = vi.fn(async () => { throw new Error('ECONNREFUSED') }) as never
    const res = await getScreenEtfs()
    expect(res.source_kind).toBe('demo')
    expect(res.data.length).toBeGreaterThan(0)
  })

  it('uses live data when endpoint returns 200', async () => {
    const livePayload = {
      data: [{ iid: 'X', code: 'X', name: 'Live Fund', category: 'Test', aum_inr: 1, style_box: null, conviction_tape: null, ret_1m: 0.01, ret_3m: 0.02, ret_6m: 0.03, ret_12m: 0.04, rs_state: 'Strong' }],
      meta: { data_as_of: '2026-05-25T09:00:00+05:30', fetched_at: '2026-05-25T09:00:00+05:30', source: 'live_db' },
    }
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify(livePayload), { status: 200, headers: { 'content-type': 'application/json' } })
    ) as never
    const res = await getScreenFunds()
    expect(res.source_kind).toBe('live')
    expect(res.data).toHaveLength(1)
    expect(res.data[0].name).toBe('Live Fund')
  })
})
