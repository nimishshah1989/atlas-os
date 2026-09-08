/**
 * The Universe column: the snapshot's reason reaches the screen, in English.
 *
 * Every row is a REAL `universe_snapshot` row of EOD 2026-09-03 (13,155 active instruments,
 * floor $1,000,000), copied verbatim out of the scratch database with the list query of
 * src/lib/queries/instruments.ts — the SELECT is quoted below and nothing is invented
 * (rule #0). Between them the ETFs carry six of the seven reasons plus the in-universe NULL,
 * and Alcoa carries the seventh: `not_sp500`, which only a stock can have.
 *
 * Only the App Router surface Explorer reads (useSearchParams / usePathname) is stubbed;
 * no row, value or label is.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { InstrumentExplorer } from '@/components/explorer/InstrumentExplorer'
import { packRows, toInstrumentRow, UNIVERSE_LABEL, type InstrumentDbRow } from '@/lib/facts'
import type { InstrumentList } from '@/lib/queries/instruments'

const search = { current: new URLSearchParams() }
vi.mock('next/navigation', () => ({
  useSearchParams: () => search.current,
  usePathname: () => '/etfs',
}))

// WITH … a AS (the SPY anchor of instruments.ts) SELECT m.symbol, m.name, m.exchange,
// m.asset_class, m.listing_date, m.cik, m.series_id, m.class_id, m.sector_gics, <sp500 EXISTS>,
// <open ssga weight_frac>, u.in_universe, u.exclusion_reason AS universe_exclusion
// FROM atlas_global.instrument_master m CROSS JOIN a
// LEFT JOIN atlas_global.universe_snapshot u ON … AND u.date = a.as_of_d WHERE m.is_active …
const NULL_PRICES = {
  price_adj: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null, rs_3m_spy: null,
  pos_52w: null, adv_usd: null,
} as const
const BASE = { asset_class: 'etf', series_id: null, class_id: null, sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES } as const

const ETFS: InstrumentDbRow[] = [
  { ...BASE, symbol: 'SPY', name: 'State Street SPDR S&P 500 ETF Trust', exchange: 'NYSEARCA', listing_date: '1993-01-29', cik: '0000884394', in_universe: true, universe_exclusion: null },
  { ...BASE, symbol: 'ILCB', name: 'iShares Morningstar Large-Cap ETF', exchange: 'NYSEARCA', listing_date: '2004-07-02', cik: '0001100663', series_id: 'S000004367', class_id: 'C000012097', in_universe: false, universe_exclusion: 'below_floor' },
  { ...BASE, symbol: 'TQQQ', name: 'ProShares UltraPro QQQ', exchange: 'NASDAQ', listing_date: '2010-02-11', cik: '0001174610', series_id: 'S000024908', class_id: 'C000074098', in_universe: false, universe_exclusion: 'leveraged' },
  { ...BASE, symbol: 'SH', name: 'ProShares Short S&P500', exchange: 'NYSEARCA', listing_date: '2006-06-21', cik: '0001174610', series_id: 'S000006828', class_id: 'C000018466', in_universe: false, universe_exclusion: 'inverse' },
  { ...BASE, symbol: 'BOND', name: 'PIMCO Active Bond Exchange-Traded Fund Exchange-Traded Fund', exchange: 'NYSE', listing_date: '2012-03-01', cik: '0001450011', series_id: 'S000033233', class_id: 'C000102215', in_universe: false, universe_exclusion: 'no_bars' },
  { ...BASE, symbol: 'ALA', name: 'Corgi ALAB 2x Daily ETF', exchange: 'BATS', listing_date: '2026-07-10', cik: null, in_universe: false, universe_exclusion: 'too_few_observations' },
  { ...BASE, symbol: 'VALG', name: 'Leverage Shares 2X Long VALE Daily ETF', exchange: 'NASDAQ', listing_date: '2025-12-18', cik: null, in_universe: false, universe_exclusion: 'stale' },
]
const STOCKS: InstrumentDbRow[] = [
  { ...BASE, asset_class: 'stock', symbol: 'AA', name: 'Alcoa Corporation Common Stock', exchange: 'NYSE', listing_date: '2016-10-18', cik: '0001675149', in_universe: false, universe_exclusion: 'not_sp500' },
  { ...BASE, asset_class: 'stock', symbol: 'AAPL', name: 'Apple Inc. - Common Stock', exchange: 'NASDAQ', listing_date: '1980-12-12', cik: '0000320193', sector_gics: 'Information Technology', sp500: true, spy_weight: '0.07219673', in_universe: true, universe_exclusion: null },
]

const list = (rows: InstrumentDbRow[]): InstrumentList => ({
  eod: '2026-09-03', as_of: '2026-09-03', ...packRows(rows.map(toInstrumentRow)),
})

/** The Universe cell of each rendered row, by symbol. */
function universeCells(container: HTMLElement): Record<string, string> {
  const index = [...container.querySelectorAll('.dt-table th')].findIndex((th) => th.textContent?.includes('Universe'))
  expect(index).toBeGreaterThan(-1)
  return Object.fromEntries(
    [...container.querySelectorAll<HTMLElement>('tr[data-row]')].map((tr) => [
      tr.querySelector('.dt-symbol')?.textContent ?? '',
      tr.querySelectorAll('td')[index]?.textContent ?? '',
    ]),
  )
}

describe('the Universe column', () => {
  it('shows the snapshot’s reason for every ETF it left out, and nothing for one it kept', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(universeCells(container)).toEqual({
      SPY: 'In universe',
      ILCB: 'Below the floor',
      TQQQ: 'Leveraged ETF',
      SH: 'Inverse ETF',
      BOND: 'No price bars',
      ALA: 'Too few sessions',
      VALG: 'Not traded lately',
    })
  })

  it('shows the one reason only a stock can carry', () => {
    search.current = new URLSearchParams('sp500=all') // the rail defaults to members only
    const { container } = render(<InstrumentExplorer assetClass="stock" list={list(STOCKS)} />)
    expect(universeCells(container)).toEqual({ AA: 'Not in the S&P 500', AAPL: 'In universe' })
  })

  it('never puts a database token on the screen, in the table or in the facet rail', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    for (const token of ETFS.map((r) => r.universe_exclusion).filter((r) => r !== null)) {
      expect(container.textContent).not.toContain(token)
      expect(container.textContent).toContain(UNIVERSE_LABEL[token])
    }
    // …and the facet offers the same words, with a count beside each.
    const rail = screen.getByRole('group', { name: 'Universe' })
    expect(rail.textContent).toContain('Below the floor')
    expect(rail.querySelectorAll('input[type="checkbox"]')).toHaveLength(7)
  })
})
