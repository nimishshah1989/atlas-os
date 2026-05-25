// frontend/src/components/v6/__tests__/ScreenerClient.test.tsx
//
// 3 test cases:
//   1. Renders filter builder + empty-state when stocks=[]
//   2. Apply filter (action chip) triggers URL update via router.replace
//   3. URL updates on filter change — verifiable via router mock

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useState as _useState } from 'react'

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))

const replaceMock = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => '/v6/screening',
  useSearchParams: () => new URLSearchParams(),
}))

// PortfolioBadge — lightweight stub
vi.mock('@/components/v6/PortfolioBadge', () => ({
  PortfolioBadge: () => <span data-testid="portfolio-badge" />,
}))

// ConvictionTape — lightweight stub
vi.mock('@/components/v6/ConvictionTape', () => ({
  ConvictionTape: () => <span data-testid="conviction-tape" />,
}))

// ColumnChooser — lightweight stub
vi.mock('@/components/v6/ColumnChooser', () => ({
  ColumnChooser: () => <button data-testid="chooser-trigger">Columns</button>,
}))

// useColumnPreferences — stub
vi.mock('@/lib/v6/useColumnPreferences', () => ({
  useColumnPreferences: (_key: string, defaults: string[]) => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const [visible, setVisible] = _useState<string[]>(defaults)
    return { visible, setVisible, reset: () => setVisible(defaults) }
  },
}))

// @tanstack/react-virtual — minimal stub (virtualization threshold = 300, these tests have <300 rows)
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: () => ({
    getVirtualItems: () => [],
    getTotalSize: () => 0,
  }),
}))

import { ScreenerClient } from '../ScreenerClient'
import type { StockV6Row } from '@/lib/queries/v6/stocks'

// ── Fixtures ─────────────────────────────────────────────────────────────────

function makeVerdict(dir: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' = 'POSITIVE') {
  return { direction: dir, ic: dir === 'POSITIVE' ? 0.05 : null, rule_count: 1, top_rule_id: null }
}

function makeTape(dir: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' = 'POSITIVE') {
  const v = makeVerdict(dir)
  return { '1m': v, '3m': v, '6m': v, '12m': v }
}

function makeStock(overrides: Partial<StockV6Row> & { iid: string; symbol: string }): StockV6Row {
  return {
    iid: overrides.iid,
    symbol: overrides.symbol,
    company_name: overrides.company_name ?? `${overrides.symbol} Ltd`,
    sector: overrides.sector ?? 'Energy',
    tier: overrides.tier ?? 'Large',
    mcap_inr: null,
    rs_state: null,
    stage: null,
    conviction_tape: overrides.conviction_tape ?? makeTape(),
    ret_1d: null, ret_1w: null, ret_1m: null,
    ret_3m: null, ret_6m: null, ret_12m: null,
    rs_pctile_3m: overrides.rs_pctile_3m ?? 0.8,
    is_investable: overrides.is_investable ?? true,
  }
}

const SNAPSHOT_DATE = '2026-05-22'

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ScreenerClient', () => {
  beforeEach(() => {
    replaceMock.mockReset()
  })

  it('case 1: renders filter builder and empty state when stocks=[]', () => {
    render(
      <ScreenerClient
        stocks={[]}
        initialFilter={{}}
        heldIids={[]}
        snapshotDate={SNAPSHOT_DATE}
      />
    )

    // Filter builder panel visible
    expect(screen.getByTestId('screener-filter-builder')).toBeInTheDocument()
    // Filter sections rendered
    expect(screen.getByText('Filters')).toBeInTheDocument()

    // Empty state shown when no results
    expect(screen.getByTestId('screener-empty-state')).toBeInTheDocument()
    expect(screen.getByText('No stocks match the current filters.')).toBeInTheDocument()
  })

  it('case 2: clicking a filter chip triggers router.replace with updated URL', async () => {
    const stocks = [
      makeStock({ iid: 'iid-1', symbol: 'RELIANCE', tier: 'Large', conviction_tape: makeTape('POSITIVE') }),
      makeStock({ iid: 'iid-2', symbol: 'TCS',      tier: 'Large', conviction_tape: makeTape('NEUTRAL') }),
    ]

    render(
      <ScreenerClient
        stocks={stocks}
        initialFilter={{}}
        heldIids={[]}
        snapshotDate={SNAPSHOT_DATE}
      />
    )

    // Results panel shows 2 stocks in header (appears in filter panel + results header)
    const stockCounts = screen.getAllByText(/2 stocks/)
    expect(stockCounts.length).toBeGreaterThanOrEqual(1)

    // Click the "Large" cap tier chip
    const largeTierBtn = screen.getByTestId('cap-tier-Large')
    fireEvent.click(largeTierBtn)

    // router.replace called with cap_tiers=Large in the URL
    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledTimes(1)
    })
    const calledUrl: string = replaceMock.mock.calls[0][0] as string
    expect(calledUrl).toContain('cap_tiers=Large')
  })

  it('case 3: URL updates when filter changes — different filters produce different URLs', async () => {
    const stocks = [
      makeStock({ iid: 'iid-1', symbol: 'RELIANCE' }),
    ]

    render(
      <ScreenerClient
        stocks={stocks}
        initialFilter={{}}
        heldIids={[]}
        snapshotDate={SNAPSHOT_DATE}
      />
    )

    // Apply action filter: click POSITIVE chip
    const positiveBtn = screen.getByTestId('action-POSITIVE')
    fireEvent.click(positiveBtn)

    await waitFor(() => expect(replaceMock).toHaveBeenCalledTimes(1))
    const url1: string = replaceMock.mock.calls[0][0] as string
    expect(url1).toContain('actions=POSITIVE')

    // Apply drift filter: click drift_warn chip
    const driftBtn = screen.getByTestId('drift-drift_warn')
    fireEvent.click(driftBtn)

    await waitFor(() => expect(replaceMock).toHaveBeenCalledTimes(2))
    const url2: string = replaceMock.mock.calls[1][0] as string
    // Both filters should be present in the URL after second change
    // (filter state accumulates)
    expect(url2).toContain('drift_statuses=drift_warn')

    // The two URLs are different (different filters)
    expect(url1).not.toBe(url2)
  })
})
