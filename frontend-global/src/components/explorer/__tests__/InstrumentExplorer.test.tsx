/**
 * The three defects this surface was rebuilt to fix, each with a test that fails if it returns.
 *
 *   1. Every fund name rendered as an ellipsis. The Name column was declared `width: 0` in a
 *      `table-layout: fixed` table, so it got the 160 px default leftover of a 1,324 px minimum.
 *      Asserted here on the arithmetic that produced it: the table's own min-width, minus every
 *      sized column, is the floor the name can never lose.
 *   2. The board listed all 5,655 funds alphabetically, ignoring `universe_snapshot.in_universe`.
 *      Asserted on the REAL verdicts of EOD 2026-09-03.
 *   3. Nothing was ranked, and a missing measurement risked reading as a zero.
 *
 * Every instrument row is a REAL `universe_snapshot` row of EOD 2026-09-03 (13,155 active
 * instruments, floor $1,000,000), copied verbatim out of the scratch database with the list query
 * of src/lib/queries/scores.ts. NO SCORE IS INVENTED: `etf_scores_daily` is empty in that database,
 * so every score column is null exactly as it is in life, and SPY additionally carries the
 * degenerate row `blend()` writes when no lens had data — BlendResult(None, 'BELOW_THRESHOLD', 0) —
 * which is what makes the "a null lens is an em dash, never a 0" assertion possible at all.
 * The lens weights are the seeds of scripts/global_market/seed_thresholds.py.
 *
 * Only the App Router surface Explorer reads (useSearchParams / usePathname) is stubbed.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { InstrumentExplorer } from '@/components/explorer/InstrumentExplorer'
import { packRows, toInstrumentRow, UNIVERSE_LABEL, type InstrumentDbRow } from '@/lib/facts'
import type { InstrumentList } from '@/lib/queries/scores'
import type { LensWeight } from '@/lib/scores'

const search = { current: new URLSearchParams() }
vi.mock('next/navigation', () => ({
  useSearchParams: () => search.current,
  usePathname: () => '/etfs',
}))

// select threshold_key, threshold_value from atlas_global.atlas_thresholds
// where is_active and threshold_key like 'etf_lens_weight_%'  — the seeds of plan.md §C.
const ETF_LENSES: LensWeight[] = [
  { key: 'technical', weight: 0.35 },
  { key: 'quality', weight: 0.3 },
  { key: 'cost_liquidity', weight: 0.2 },
  { key: 'flow', weight: 0.15 },
  { key: 'risk', weight: 0 },
]

const UNSCORED = {
  strategy: null, class_asset_class: null, leveraged: null, inverse: null, hedged: null,
  class_status: null, country: null, region: null,
  composite: null, technical: null, conviction_tier: null, peer_group: null, lenses_active: null,
  composite_decile: null, peer_rank: null, peer_n: null,
  rs_3m_spy: null, rs_6m_spy: null, rs_12m_spy: null, pos_52w: null, adv_usd: null,
  vol_ann: null, mdd_12m: null,
} as const
const BASE = { asset_class: 'etf', sector_gics: null, ...UNSCORED } as const

const ETFS: InstrumentDbRow[] = [
  // …and the score journal's degenerate row: no lens had data, so there is no composite, no
  // decile and no tier above the floor. Nothing here claims SPY is weak; it claims nothing.
  { ...BASE, symbol: 'SPY', name: 'State Street SPDR S&P 500 ETF Trust', in_universe: true, universe_exclusion: null, conviction_tier: 'BELOW_THRESHOLD', lenses_active: 0, peer_group: 'equity:broad_market' },
  { ...BASE, symbol: 'ILCB', name: 'iShares Morningstar Large-Cap ETF', in_universe: false, universe_exclusion: 'below_floor' },
  { ...BASE, symbol: 'TQQQ', name: 'ProShares UltraPro QQQ', in_universe: false, universe_exclusion: 'leveraged', leveraged: true, inverse: false, class_status: 'auto' },
  { ...BASE, symbol: 'SH', name: 'ProShares Short S&P500', in_universe: false, universe_exclusion: 'inverse', leveraged: false, inverse: true, class_status: 'auto' },
  { ...BASE, symbol: 'BOND', name: 'PIMCO Active Bond Exchange-Traded Fund Exchange-Traded Fund', in_universe: false, universe_exclusion: 'no_bars' },
  { ...BASE, symbol: 'ALA', name: 'Corgi ALAB 2x Daily ETF', in_universe: false, universe_exclusion: 'too_few_observations' },
  { ...BASE, symbol: 'VALG', name: 'Leverage Shares 2X Long VALE Daily ETF', in_universe: false, universe_exclusion: 'stale' },
]
const STOCKS: InstrumentDbRow[] = [
  { ...BASE, asset_class: 'stock', symbol: 'AA', name: 'Alcoa Corporation Common Stock', in_universe: false, universe_exclusion: 'not_sp500' },
  { ...BASE, asset_class: 'stock', symbol: 'AAPL', name: 'Apple Inc. - Common Stock', sector_gics: 'Information Technology', in_universe: true, universe_exclusion: null },
]

const list = (rows: InstrumentDbRow[]): InstrumentList => ({
  eod: '2026-09-03',
  as_of: '2026-09-03',
  scored_on: '2026-09-03',
  lenses: ETF_LENSES,
  ...packRows(rows.map(toInstrumentRow)),
})

const symbols = (c: HTMLElement) => [...c.querySelectorAll('.dt-symbol')].map((e) => e.textContent)
const cell = (c: HTMLElement, symbol: string, header: string) => {
  const i = [...c.querySelectorAll('.dt-table th')].findIndex((th) => th.textContent?.includes(header))
  expect(i).toBeGreaterThan(-1)
  const row = [...c.querySelectorAll<HTMLElement>('tr[data-row]')].find((tr) => tr.querySelector('.dt-symbol')?.textContent === symbol)
  return row?.querySelectorAll('td')[i]?.textContent ?? ''
}

describe('the default view is the universe, not the directory', () => {
  it('opens on the in-universe set only — the flag the nightly already writes', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(symbols(container)).toEqual(['SPY'])
    expect(screen.getByTestId('count').textContent).toContain('1 of 7 ETFs')
    // …and no column asking why a row is out, when every row shown is in.
    expect(container.textContent).not.toContain('Why it is out')
  })

  it('does the same for stocks: membership IS the universe, not a facet', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="stock" list={list(STOCKS)} />)
    expect(symbols(container)).toEqual(['AAPL'])
  })

  it('“Everything listed” reveals the rest with each row’s own reason, in English', () => {
    search.current = new URLSearchParams('universe=all&geared=on&inverse=on')
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(symbols(container)).toHaveLength(7)
    expect(cell(container, 'ILCB', 'Why it is out')).toBe('Below the floor')
    expect(cell(container, 'TQQQ', 'Why it is out')).toBe('Leveraged ETF')
    expect(cell(container, 'BOND', 'Why it is out')).toBe('No price bars')
    // No database token reaches the table. ("leveraged" and "inverse" are also plain English and
    // do appear in the rail's own toggles, so the check is scoped to the rows.)
    const body = container.querySelector('tbody')?.textContent ?? ''
    for (const token of ETFS.map((r) => r.universe_exclusion).filter(Boolean)) {
      expect(body).not.toContain(token)
      expect(body).toContain(UNIVERSE_LABEL[token as string])
    }
  })

  it('keeps geared and inverse funds out until their toggles are ticked, and says how many', () => {
    search.current = new URLSearchParams('universe=all')
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(symbols(container)).not.toContain('TQQQ')
    expect(symbols(container)).not.toContain('SH')
    const geared = screen.getByRole('group', { name: 'Leveraged funds' })
    expect(within(geared).getByRole('checkbox', { name: 'Include leveraged' })).not.toBeChecked()
    expect(geared.textContent).toContain('1')
  })
})

describe('a measurement nobody made is never a zero', () => {
  it('prints an em dash for the composite and the decile of a row with no lens', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(cell(container, 'SPY', 'Composite')).toBe('—')
    expect(cell(container, 'SPY', 'Technical')).toBe('—')
    expect(cell(container, 'SPY', 'Composite')).not.toContain('0')
  })

  it('says how many of the blend’s lenses the score was built from, from the weight table', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(cell(container, 'SPY', 'Lenses')).toBe('0/5')
    expect(container.querySelector('[title="0 of 5 lenses"]')?.textContent).toBe('0/5')
  })

  it('COUNTS the active lenses in its own sentence rather than asserting a number', () => {
    // The paragraph used to say "while one lens is active", which was true the day it was
    // written and false the day the risk and cost lenses landed — and it promised a MEDIUM cap
    // that no longer applied. The board was explaining its own methodology wrongly, on the live
    // site, which is the exact failure it exists to prevent. It now reads the count off the rows
    // and states the tier rule as a rule, so it stays true as each new lens lands.
    search.current = new URLSearchParams()
    const asIs = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(asIs.container.textContent).toContain('0 of 5 lenses') // every fixture row has none

    // Same component, a row that carries three: if the sentence were hardcoded it would still
    // say zero. This is the assertion that makes the paragraph impossible to leave stale.
    asIs.unmount()
    const richer = ETFS.map((r) => (r.symbol === 'SPY' ? { ...r, lenses_active: 3 } : r))
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(richer)} />)
    const text = container.textContent ?? ''
    expect(text).toContain('3 of 5 lenses')
    expect(text).not.toContain('0 of 5 lenses')
    expect(text).not.toContain('MEDIUM however strong')
    expect(text).toContain('several independent')
  })

  it('prints the tier the ladder actually returned, in words', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    expect(cell(container, 'SPY', 'Conviction')).toBe('Below threshold')
  })
})

describe('the name column can never lose its width', () => {
  it('reserves a floor for the name inside the table’s own minimum width', () => {
    search.current = new URLSearchParams()
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    const table = container.querySelector<HTMLElement>('.dt-table')
    const cols = [...container.querySelectorAll<HTMLElement>('col')]
    const sized = cols.reduce((w, c) => w + (parseInt(c.style.width, 10) || 0), 0)
    const min = parseInt(table?.style.minWidth ?? '0', 10)
    // The name column is the only unsized one; fixed layout hands it what the others do not use.
    expect(cols.filter((c) => !c.style.width)).toHaveLength(1)
    expect(min - sized).toBeGreaterThanOrEqual(280)
  })

  it('renders the whole fund name, and repeats it as the cell’s tooltip', () => {
    search.current = new URLSearchParams('universe=all')
    const { container } = render(<InstrumentExplorer assetClass="etf" list={list(ETFS)} />)
    const long = 'PIMCO Active Bond Exchange-Traded Fund Exchange-Traded Fund'
    expect(cell(container, 'BOND', 'Name')).toBe(long)
    expect(container.querySelector(`[title="${long}"]`)).not.toBeNull()
  })
})
