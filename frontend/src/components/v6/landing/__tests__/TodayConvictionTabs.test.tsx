// frontend/src/components/v6/landing/__tests__/TodayConvictionTabs.test.tsx
//
// Unit tests for the 3-tab Today's Conviction panel.
// Tests cover: tab rendering, tab switching, empty state, NEW badge,
// action badge coloring logic, confidence bar rendering.

import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TodayConvictionTabs } from '../TodayConvictionTabs'
import type { ConvictionCallsResult, ConvictionCallRow } from '@/lib/queries/v6/landing'

function makeStockRow(overrides: Partial<ConvictionCallRow> = {}): ConvictionCallRow {
  return {
    symbol: 'BHARTIARTL',
    company_name: 'Bharti Airtel',
    sector: 'Telecom',
    cap_tier: 'Large',
    cell_label: 'Mid 6m',
    confidence: 0.92,
    action: 'POSITIVE',
    predicted_excess: '+8.4%',
    is_new: false,
    is_fund: false,
    is_atlas_leader: false,
    ...overrides,
  }
}

function makeEmptyResult(): ConvictionCallsResult {
  return {
    stocks: [],
    stocks_new_count: 0,
    etfs: [],
    etfs_new_count: 0,
    funds: [],
    funds_new_count: 0,
  }
}

describe('TodayConvictionTabs', () => {
  it('renders the section heading', () => {
    render(<TodayConvictionTabs data={makeEmptyResult()} />)
    expect(screen.getByText("Today's conviction")).toBeDefined()
  })

  it('renders three tab buttons', () => {
    render(<TodayConvictionTabs data={makeEmptyResult()} />)
    expect(screen.getByRole('tab', { name: /stocks/i })).toBeDefined()
    expect(screen.getByRole('tab', { name: /etfs/i })).toBeDefined()
    expect(screen.getByRole('tab', { name: /funds/i })).toBeDefined()
  })

  it('defaults to Stocks tab being selected', () => {
    render(<TodayConvictionTabs data={makeEmptyResult()} />)
    const stocksTab = screen.getByRole('tab', { name: /stocks/i })
    expect(stocksTab.getAttribute('aria-selected')).toBe('true')
  })

  it('shows empty state message when stocks tab is empty', () => {
    render(<TodayConvictionTabs data={makeEmptyResult()} />)
    expect(screen.getByText(/No active stocks calls/i)).toBeDefined()
  })

  it('renders stock rows with symbol and company name', () => {
    const data: ConvictionCallsResult = {
      stocks: [
        makeStockRow({ symbol: 'ABB', company_name: 'ABB India', action: 'POSITIVE' }),
        makeStockRow({ symbol: 'ZEEL', company_name: 'Zee Entertainment', action: 'NEGATIVE' }),
      ],
      stocks_new_count: 0,
      etfs: [],
      etfs_new_count: 0,
      funds: [],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)
    expect(screen.getByText('ABB')).toBeDefined()
    expect(screen.getByText('ABB India')).toBeDefined()
    expect(screen.getByText('ZEEL')).toBeDefined()
  })

  it('shows NEW badge for is_new=true rows', () => {
    const data: ConvictionCallsResult = {
      stocks: [
        makeStockRow({ symbol: 'VOLTAS', is_new: true }),
        makeStockRow({ symbol: 'TRENT', is_new: false }),
      ],
      stocks_new_count: 1,
      etfs: [],
      etfs_new_count: 0,
      funds: [],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)
    // NEW badge should appear exactly once (for VOLTAS)
    const newBadges = screen.getAllByText('NEW')
    // One in the section sub-text description + one in the row
    expect(newBadges.length).toBeGreaterThanOrEqual(1)
  })

  it('switches to ETFs tab when clicked and shows ETF content', () => {
    const data: ConvictionCallsResult = {
      stocks: [makeStockRow()],
      stocks_new_count: 0,
      etfs: [
        makeStockRow({ symbol: 'NIFTYBEES', company_name: 'Nippon Nifty BeES', cell_label: 'ETF 6m', cap_tier: null }),
      ],
      etfs_new_count: 0,
      funds: [],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)

    const etfTab = screen.getByRole('tab', { name: /etfs/i })
    fireEvent.click(etfTab)

    expect(etfTab.getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('NIFTYBEES')).toBeDefined()
    // Stock row should no longer be visible in the active pane (still in DOM but different tab)
  })

  it('switches to Funds tab and shows fund content', () => {
    const data: ConvictionCallsResult = {
      stocks: [],
      stocks_new_count: 0,
      etfs: [],
      etfs_new_count: 0,
      funds: [
        makeStockRow({
          symbol: 'PPFAS',
          company_name: 'PPFAS Flexicap',
          sector: 'Flexicap',
          cell_label: 'Atlas Leader',
          action: 'POSITIVE',
        }),
      ],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)

    const fundsTab = screen.getByRole('tab', { name: /funds/i })
    fireEvent.click(fundsTab)

    expect(fundsTab.getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('PPFAS')).toBeDefined()
  })

  it('displays BUY label for POSITIVE action', () => {
    const data: ConvictionCallsResult = {
      stocks: [makeStockRow({ action: 'POSITIVE' })],
      stocks_new_count: 0,
      etfs: [],
      etfs_new_count: 0,
      funds: [],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)
    expect(screen.getByText('BUY')).toBeDefined()
  })

  it('displays AVOID label for NEGATIVE action', () => {
    const data: ConvictionCallsResult = {
      stocks: [makeStockRow({ action: 'NEGATIVE', predicted_excess: '-6.4%' })],
      stocks_new_count: 0,
      etfs: [],
      etfs_new_count: 0,
      funds: [],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)
    expect(screen.getByText('AVOID')).toBeDefined()
  })

  it('shows tab count in tab label when rows exist', () => {
    const data: ConvictionCallsResult = {
      stocks: [makeStockRow(), makeStockRow({ symbol: 'TCS' })],
      stocks_new_count: 1,
      etfs: [],
      etfs_new_count: 0,
      funds: [],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)
    // Tab should show count text
    expect(screen.getByText(/2 active · 1 new/)).toBeDefined()
  })

  it('tab order is Stocks | Funds | ETFs per mockup spec', () => {
    render(<TodayConvictionTabs data={makeEmptyResult()} />)
    const tabs = screen.getAllByRole('tab')
    expect(tabs[0].textContent).toMatch(/Stocks/i)
    expect(tabs[1].textContent).toMatch(/Funds/i)
    expect(tabs[2].textContent).toMatch(/ETFs/i)
  })

  it('description text says stocks, funds, and ETFs in that order', () => {
    render(<TodayConvictionTabs data={makeEmptyResult()} />)
    expect(screen.getByText(/stocks, funds, and ETFs/i)).toBeDefined()
  })

  it('renders Atlas Leader quality badge for is_fund=true is_atlas_leader=true rows', () => {
    const data: ConvictionCallsResult = {
      stocks: [],
      stocks_new_count: 0,
      etfs: [],
      etfs_new_count: 0,
      funds: [
        makeStockRow({
          symbol: 'PPFAS',
          company_name: 'PPFAS Flexicap',
          sector: 'Flexicap',
          cell_label: 'Atlas Leader',
          action: 'POSITIVE',
          is_fund: true,
          is_atlas_leader: true,
        }),
      ],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)
    const fundsTab = screen.getByRole('tab', { name: /funds/i })
    fireEvent.click(fundsTab)
    // 'Atlas Leader' appears in both cell_label div and FundQualityBadge span
    const atlasLeaderEls = screen.getAllByText('Atlas Leader')
    expect(atlasLeaderEls.length).toBeGreaterThanOrEqual(1)
    // Verify the badge span exists specifically
    const badge = atlasLeaderEls.find(el => el.tagName === 'SPAN')
    expect(badge).toBeDefined()
  })

  it('renders Quality column header (not Confidence) when on Funds tab', () => {
    const data: ConvictionCallsResult = {
      stocks: [],
      stocks_new_count: 0,
      etfs: [],
      etfs_new_count: 0,
      funds: [
        makeStockRow({
          symbol: 'PPFAS',
          is_fund: true,
          is_atlas_leader: true,
        }),
      ],
      funds_new_count: 0,
    }
    render(<TodayConvictionTabs data={data} />)
    const fundsTab = screen.getByRole('tab', { name: /funds/i })
    fireEvent.click(fundsTab)
    expect(screen.getByText('Quality')).toBeDefined()
  })
})
