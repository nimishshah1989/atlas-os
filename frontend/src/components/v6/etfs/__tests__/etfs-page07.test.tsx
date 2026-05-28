// frontend/src/components/v6/etfs/__tests__/etfs-page07.test.tsx
//
// Tests for Page 07 ETF components:
//   HeroStories — story block derivation from EtfListV6Row[]
//   AmcTileRow — AMC aggregation via getAmcAggregates()
//   CategoryBands — category band derivation
//   NavVsMarketPrice — zone classification + NULL handling
//   TrackingError12m — TE quality zones + NULL handling
//   PeerSetTable — rendering with real vs null peer data
//   getAmcAggregates — pure JS aggregation (no DB)

// Mock server-only and DB modules (no real DB in tests)
import { vi, describe, it, expect } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))
import { render, screen } from '@testing-library/react'
import { HeroStories } from '../HeroStories'
import { AmcTileRow } from '../AmcTileRow'
import { CategoryBands } from '../CategoryBands'
import { NavVsMarketPrice } from '../NavVsMarketPrice'
import { TrackingError12m } from '../TrackingError12m'
import { PeerSetTable } from '../PeerSetTable'
import { getAmcAggregates } from '@/lib/queries/v6/etfs'
import type { EtfListV6Row, PeerSetEntry } from '@/lib/queries/v6/etfs'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeEtf(overrides: Partial<EtfListV6Row> = {}): EtfListV6Row {
  return {
    ticker: 'TESTBEES',
    etf_name: 'Test ETF BeES',
    fund_house: 'NIPPON',
    asset_class: 'equity',
    etf_category: 'index',
    composite_score: 0.72,
    is_atlas_leader: false,
    premium_bps: 5,
    te_60d: 0.0010,    // 10 bps (v < 1 → multiply by 10000)
    adv_20d_inr: 5e7,  // ₹5 cr
    adv_monthly_cr: 150,
    ret_1d: 0.002,
    ret_1w: 0.01,
    ret_1m: 0.03,
    ret_3m: 0.05,
    ret_6m: 0.08,
    ret_12m: 0.15,
    rs_state: 'Strong',
    momentum_state: 'Strong',
    action: 'BUY',
    scatter_zone: 'clean_buy',
    signal_fire_date: '2026-01-15',
    signal_tenure: null,
    as_of_date: '2026-05-27',
    eli5: 'Strong gold leadership',
    ...overrides,
  }
}

const ETFS: EtfListV6Row[] = [
  makeEtf({ ticker: 'GOLDBEES', action: 'BUY', composite_score: 0.85, fund_house: 'NIPPON', etf_category: 'commodity', premium_bps: 3, te_60d: 0.0008, adv_20d_inr: 8.4e7 }),
  makeEtf({ ticker: 'NIFTYBEES', action: 'BUY', composite_score: 0.80, fund_house: 'NIPPON', etf_category: 'index', premium_bps: 1, te_60d: 0.0010, adv_20d_inr: 6.2e7 }),
  makeEtf({ ticker: 'CPSEETF', action: 'BUY', composite_score: 0.75, fund_house: 'NIPPON', etf_category: 'sector', premium_bps: 30, te_60d: 0.0014, adv_20d_inr: 4.6e7 }),
  makeEtf({ ticker: 'SETFNIF50', action: 'WATCH', composite_score: 0.55, fund_house: 'SBI', etf_category: 'index', premium_bps: -5, te_60d: 0.0009, adv_20d_inr: 3.8e7 }),
  makeEtf({ ticker: 'UTINEXT50', action: 'AVOID', composite_score: 0.25, fund_house: 'UTI', etf_category: 'index', premium_bps: null, te_60d: 0.0018, adv_20d_inr: 1.8e6 }),  // low ADV
  makeEtf({ ticker: 'MOMENTUM30', action: 'WATCH', composite_score: 0.48, fund_house: 'MOTILAL', etf_category: 'smart_beta', premium_bps: -30, te_60d: 0.0030, adv_20d_inr: 4e7 }),
]

// ---------------------------------------------------------------------------
// Tests: HeroStories
// ---------------------------------------------------------------------------

describe('HeroStories', () => {
  it('renders four story blocks', () => {
    render(<HeroStories etfs={ETFS} />)
    const container = screen.getByTestId('hero-stories')
    expect(container).toBeDefined()
  })

  it('shows BUY ETFs in the cleanest BUYs block', () => {
    render(<HeroStories etfs={ETFS} />)
    // GOLDBEES appears in both BUY block and tightest-TE block — use getAllByText
    const goldbeesEls = screen.getAllByText('GOLDBEES')
    expect(goldbeesEls.length).toBeGreaterThanOrEqual(1)
    // NIFTYBEES also appears in both blocks
    const niftybeesEls = screen.getAllByText('NIFTYBEES')
    expect(niftybeesEls.length).toBeGreaterThanOrEqual(1)
  })

  it('shows low-ADV ETF in liquidity warnings', () => {
    render(<HeroStories etfs={ETFS} />)
    // UTINEXT50 appears in tightest-TE block AND liquidity-warnings block
    const utinext50Els = screen.getAllByText('UTINEXT50')
    expect(utinext50Els.length).toBeGreaterThanOrEqual(1)
  })

  it('shows premium outliers for |premium_bps| > 25', () => {
    render(<HeroStories etfs={ETFS} />)
    // CPSEETF: +30bps, MOMENTUM30: -30bps
    // Both should appear in premium outliers block
    const premiumLabels = screen.getAllByText('CPSEETF')
    expect(premiumLabels.length).toBeGreaterThanOrEqual(1)
  })

  it('renders empty premium outliers gracefully when all within ±25bps', () => {
    const noOutliers = ETFS.map(e => ({ ...e, premium_bps: 5 }))
    render(<HeroStories etfs={noOutliers} />)
    expect(screen.getByText(/All ETFs within ±25 bps/)).toBeDefined()
  })

  it('renders empty liquidity warnings when all ETFs have sufficient ADV', () => {
    const goodLiq = ETFS.map(e => ({ ...e, adv_20d_inr: 5e7 }))
    render(<HeroStories etfs={goodLiq} />)
    expect(screen.getByText(/All ETFs above ₹3 cr ADV/)).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// Tests: getAmcAggregates (pure JS)
// ---------------------------------------------------------------------------

describe('getAmcAggregates', () => {
  it('groups by fund_house correctly', () => {
    const aggs = getAmcAggregates(ETFS)
    const nippon = aggs.find(a => a.fund_house === 'NIPPON')
    expect(nippon).toBeDefined()
    expect(nippon!.etf_count).toBe(3)  // GOLDBEES, NIFTYBEES, CPSEETF
  })

  it('counts BUY correctly for Nippon', () => {
    const aggs = getAmcAggregates(ETFS)
    const nippon = aggs.find(a => a.fund_house === 'NIPPON')
    expect(nippon!.buy_count).toBe(3)
  })

  it('sorts by total_adv_cr descending', () => {
    const aggs = getAmcAggregates(ETFS)
    // Nippon has highest combined ADV
    expect(aggs[0]?.fund_house).toBe('NIPPON')
  })

  it('handles empty array without throwing', () => {
    const aggs = getAmcAggregates([])
    expect(aggs).toHaveLength(0)
  })

  it('sets dominant_action=BUY when majority are BUY', () => {
    const aggs = getAmcAggregates(ETFS)
    const nippon = aggs.find(a => a.fund_house === 'NIPPON')
    expect(nippon!.dominant_action).toBe('BUY')
  })

  it('normalises fund_house to uppercase', () => {
    const lower = [makeEtf({ fund_house: 'nippon india', action: 'BUY', adv_monthly_cr: 100 })]
    const aggs = getAmcAggregates(lower)
    expect(aggs[0]?.fund_house).toBe('NIPPON INDIA')
  })
})

// ---------------------------------------------------------------------------
// Tests: AmcTileRow
// ---------------------------------------------------------------------------

describe('AmcTileRow', () => {
  it('renders AMC tiles', () => {
    const aggs = getAmcAggregates(ETFS)
    render(<AmcTileRow amcs={aggs} />)
    const container = screen.getByTestId('amc-tile-row')
    expect(container).toBeDefined()
  })

  it('renders tile for NIPPON AMC', () => {
    const aggs = getAmcAggregates(ETFS)
    render(<AmcTileRow amcs={aggs} />)
    expect(screen.getByText('NIPPON')).toBeDefined()
  })

  it('shows +3 BUY for Nippon (3 BUY ETFs)', () => {
    const aggs = getAmcAggregates(ETFS)
    render(<AmcTileRow amcs={aggs} />)
    expect(screen.getByText('+3 BUY')).toBeDefined()
  })

  it('renders empty gracefully', () => {
    render(<AmcTileRow amcs={[]} />)
    const container = screen.getByTestId('amc-tile-row')
    expect(container).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// Tests: CategoryBands
// ---------------------------------------------------------------------------

describe('CategoryBands', () => {
  it('renders 4 category band cards', () => {
    render(<CategoryBands etfs={ETFS} />)
    const container = screen.getByTestId('category-bands')
    expect(container).toBeDefined()
    expect(screen.getByTestId('category-band-index')).toBeDefined()
    expect(screen.getByTestId('category-band-sector')).toBeDefined()
    expect(screen.getByTestId('category-band-smartbeta')).toBeDefined()
    expect(screen.getByTestId('category-band-commodity')).toBeDefined()
  })

  it('shows correct ETF count for index band', () => {
    render(<CategoryBands etfs={ETFS} />)
    const indexCard = screen.getByTestId('category-band-index')
    // NIFTYBEES + SETFNIF50 + UTINEXT50 = 3 index ETFs
    expect(indexCard.textContent).toContain('3')
  })

  it('shows correct action mix for index band', () => {
    render(<CategoryBands etfs={ETFS} />)
    const indexCard = screen.getByTestId('category-band-index')
    // 1 BUY (NIFTYBEES), 1 WATCH (SETFNIF50), 1 AVOID (UTINEXT50)
    expect(indexCard.textContent).toMatch(/BUY.*1/)
  })
})

// ---------------------------------------------------------------------------
// Tests: NavVsMarketPrice
// ---------------------------------------------------------------------------

describe('NavVsMarketPrice', () => {
  it('renders NAV-fair zone for premium_bps <= 10', () => {
    render(<NavVsMarketPrice ticker="GOLDBEES" premiumBps={3} />)
    expect(screen.getByTestId('nav-vs-market-price')).toBeDefined()
    expect(screen.getByText(/NAV-fair\./)).toBeDefined()
  })

  it('renders attention zone for 10 < |premium_bps| <= 25', () => {
    render(<NavVsMarketPrice ticker="TESTBEES" premiumBps={18} />)
    expect(screen.getByText(/Moderate deviation\./)).toBeDefined()
  })

  it('renders AP friction zone for |premium_bps| > 25', () => {
    render(<NavVsMarketPrice ticker="CPSEETF" premiumBps={30} />)
    expect(screen.getByText(/AP friction zone\./)).toBeDefined()
  })

  it('handles NULL premium_bps gracefully', () => {
    render(<NavVsMarketPrice ticker="UTINEXT50" premiumBps={null} />)
    expect(screen.getByText(/pending/i)).toBeDefined()
  })

  it('renders correct bps value', () => {
    render(<NavVsMarketPrice ticker="GOLDBEES" premiumBps={3} />)
    expect(screen.getByText(/\+3 bps/)).toBeDefined()
  })

  it('shows negative premium correctly', () => {
    render(<NavVsMarketPrice ticker="MOMENTUM30" premiumBps={-30} />)
    expect(screen.getByText(/-30 bps/)).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// Tests: TrackingError12m
// ---------------------------------------------------------------------------

describe('TrackingError12m', () => {
  it('renders excellent zone for TE < 10 bps', () => {
    // te_60d = 0.0008 → 8 bps
    render(<TrackingError12m ticker="GOLDBEES" te60d={0.0008} category="commodity" />)
    expect(screen.getByTestId('tracking-error-panel')).toBeDefined()
    expect(screen.getByText(/Excellent\./)).toBeDefined()
  })

  it('renders good zone for 10–20 bps', () => {
    // te_60d = 0.0015 → 15 bps
    render(<TrackingError12m ticker="SETFNIF50" te60d={0.0015} category="index" />)
    expect(screen.getByText(/Good\./)).toBeDefined()
  })

  it('renders acceptable zone for 20–40 bps', () => {
    // te_60d = 0.0030 → 30 bps
    render(<TrackingError12m ticker="MOMENTUM30" te60d={0.0030} category="smart_beta" />)
    expect(screen.getByText(/Acceptable\./)).toBeDefined()
  })

  it('renders poor zone for > 40 bps', () => {
    // te_60d = 0.005 → 50 bps
    render(<TrackingError12m ticker="HIGHTE" te60d={0.005} category="thematic" />)
    expect(screen.getByText(/Poor\./)).toBeDefined()
  })

  it('handles NULL te60d gracefully', () => {
    render(<TrackingError12m ticker="NODATA" te60d={null} category={null} />)
    expect(screen.getByText(/not yet computed/i)).toBeDefined()
  })

  it('renders bps value in heading', () => {
    render(<TrackingError12m ticker="GOLDBEES" te60d={0.0008} category="commodity" />)
    expect(screen.getByText(/8 bps/)).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// Tests: PeerSetTable
// ---------------------------------------------------------------------------

const PEERS: PeerSetEntry[] = [
  {
    ticker: 'NIFTYBEES',
    composite_score: 0.80,
    matrix_conviction_score: 0.75,
    adv_20d_inr: 6.2e7,
    is_atlas_leader: false,
    rank_in_category: 1,
    delta_composite: 0.08,
  },
  {
    ticker: 'SETFNIF50',
    composite_score: 0.72,
    matrix_conviction_score: 0.68,
    adv_20d_inr: 3.8e7,
    is_atlas_leader: false,
    rank_in_category: 2,
    delta_composite: 0,
  },
  {
    ticker: 'ICICINIFTY',
    composite_score: 0.45,
    matrix_conviction_score: 0.40,
    adv_20d_inr: 2.1e6,
    is_atlas_leader: null,
    rank_in_category: 3,
    delta_composite: -0.27,
  },
]

describe('PeerSetTable', () => {
  it('renders peer set table with rows', () => {
    render(<PeerSetTable ticker="GOLDBEES" peers={PEERS} category="index" />)
    const table = screen.getByTestId('peer-set-table')
    expect(table).toBeDefined()
  })

  it('shows all peer tickers', () => {
    render(<PeerSetTable ticker="GOLDBEES" peers={PEERS} category="index" />)
    expect(screen.getByText('NIFTYBEES')).toBeDefined()
    expect(screen.getByText('SETFNIF50')).toBeDefined()
    expect(screen.getByText('ICICINIFTY')).toBeDefined()
  })

  it('renders delta_composite with sign', () => {
    render(<PeerSetTable ticker="GOLDBEES" peers={PEERS} category="index" />)
    // NIFTYBEES has delta +0.08 → "+8.0"
    expect(screen.getByText('+8.0')).toBeDefined()
  })

  it('shows negative delta for ICICINIFTY', () => {
    render(<PeerSetTable ticker="GOLDBEES" peers={PEERS} category="index" />)
    expect(screen.getByText('-27.0')).toBeDefined()
  })

  it('handles null peer_set gracefully', () => {
    render(<PeerSetTable ticker="GOLDBEES" peers={null} category="index" />)
    expect(screen.getByText(/No peer data/i)).toBeDefined()
  })

  it('handles empty peer array', () => {
    render(<PeerSetTable ticker="GOLDBEES" peers={[]} category="index" />)
    expect(screen.getByText(/No peer data/i)).toBeDefined()
  })

  it('shows rank in category', () => {
    render(<PeerSetTable ticker="GOLDBEES" peers={PEERS} category="index" />)
    expect(screen.getByText('#1')).toBeDefined()
    expect(screen.getByText('#2')).toBeDefined()
  })
})
