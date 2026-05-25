// frontend/src/components/v6/SectorDetailClient.tsx
// D.4 — Sector detail page client component.
// Hero + HeroBookBand + SectorBookStrip + SectorBreadthPanel + SectorBubbleChart
// + Constituent table (ColumnChooser + PortfolioBadge per held iid).

'use client'

import { useState, useMemo } from 'react'
import { SectorBookStrip } from './SectorBookStrip'
import { SectorBreadthPanel } from './SectorBreadthPanel'
import { BubbleRiskReturnChart } from './BubbleRiskReturnChart'
import { PortfolioBadge } from './PortfolioBadge'
import { ConvictionTape } from './ConvictionTape'
import { StateBadge } from '@/components/ui/StateBadge'
import { LinkedTicker } from '@/components/ui/LinkedToken'
import { ColumnChooser } from './ColumnChooser'
import type { ScreenSector } from '@/lib/api/v1'
import type { StockV6Row } from '@/lib/queries/v6/stocks'
import type { SectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'
import type { SectorBreadth } from '@/lib/queries/v6/sector_breadth'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { ColumnDef } from './ColumnChooser'
import type { BubbleDatum } from './BubbleRiskReturnChart'

// ---------------------------------------------------------------------------
// Column config
// ---------------------------------------------------------------------------

type ConstituentColKey =
  | 'symbol' | 'name' | 'stage' | 'tape'
  | 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m'
  | 'rs_pctile' | 'portfolio'

const ALL_COLUMNS: ColumnDef<ConstituentColKey>[] = [
  { key: 'symbol',    label: 'Symbol',    group: 'atlas' },
  { key: 'name',      label: 'Name',      group: 'atlas' },
  { key: 'stage',     label: 'Stage',     group: 'atlas' },
  { key: 'tape',      label: 'Conviction',group: 'atlas' },
  { key: 'ret_1m',    label: '1M',        group: 'returns' },
  { key: 'ret_3m',    label: '3M',        group: 'returns' },
  { key: 'ret_6m',    label: '6M',        group: 'returns' },
  { key: 'ret_12m',   label: '12M',       group: 'returns' },
  { key: 'rs_pctile', label: 'RS %ile',   group: 'benchmarks' },
  { key: 'portfolio', label: 'Book',      group: 'atlas' },
]

const DEFAULT_VISIBLE: ConstituentColKey[] = [
  'symbol', 'name', 'stage', 'tape', 'ret_1m', 'ret_3m', 'portfolio',
]

// Return columns with metadata for DRY rendering
const RET_COLS: Array<{ key: ConstituentColKey; label: string; getter: (r: StockV6Row) => number | null }> = [
  { key: 'ret_1m',  label: '1M',  getter: (r) => r.ret_1m },
  { key: 'ret_3m',  label: '3M',  getter: (r) => r.ret_3m },
  { key: 'ret_6m',  label: '6M',  getter: (r) => r.ret_6m },
  { key: 'ret_12m', label: '12M', getter: (r) => r.ret_12m },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type WeightClass = 'OVERWEIGHT' | 'UNDERWEIGHT' | 'NEUTRAL'

function classifyWeight(deltaPp: string): WeightClass {
  const n = parseFloat(deltaPp)
  if (!Number.isFinite(n) || Math.abs(n) < 0.005) return 'NEUTRAL'
  return n > 0 ? 'OVERWEIGHT' : 'UNDERWEIGHT'
}

const CHIP_CLS: Record<WeightClass, string> = {
  OVERWEIGHT:  'bg-signal-pos/15 text-signal-pos border border-signal-pos/30',
  UNDERWEIGHT: 'bg-signal-neg/15 text-signal-neg border border-signal-neg/30',
  NEUTRAL:     'bg-paper-deep text-ink-tertiary border border-paper-rule',
}

function fmtPp(s: string): string {
  const n = parseFloat(s)
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : '—'
}

function signedPct(v: number | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  return {
    text: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`,
    cls:  pct >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function actionVerbFor(state: string): string {
  if (state === 'Overweight') return 'OVERWEIGHT'
  if (state === 'Underweight') return 'UNDERWEIGHT'
  if (state === 'Avoid') return 'AVOID'
  if (state === 'Neutral') return 'HOLD'
  return 'WATCH'
}

function holdingStateStub(): HoldingState {
  return { portfolio_count: 1, weight_range: ['0.00', '0.00'], aggregate_weight: '0.00', last_add_date: null }
}

// ---------------------------------------------------------------------------
// BubbleData mapper
// ---------------------------------------------------------------------------

function toBubbleDatum(row: StockV6Row): BubbleDatum {
  const rs = (row.rs_state ?? '').toUpperCase()
  const state: BubbleDatum['state'] =
    rs === 'POSITIVE' || rs.includes('LEADER') || rs.includes('ACCEL') ? 'POSITIVE'
    : rs === 'NEGATIVE' || rs.includes('LAGG') ? 'NEGATIVE'
    : 'NEUTRAL'
  return {
    id:    row.iid,
    label: row.symbol,
    risk:  row.rs_pctile_3m != null ? String(1 - row.rs_pctile_3m) : '0.5',
    ret:   row.ret_3m != null ? String(row.ret_3m) : '0',
    size:  '1',
    state,
  }
}

// ---------------------------------------------------------------------------
// Bullet renderer — inline **bold** markdown
// ---------------------------------------------------------------------------

function BulletText({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/)
  return (
    <span>
      {parts.map((p, i) =>
        i % 2 === 1
          ? <strong key={i} className="font-semibold text-ink-primary">{p}</strong>
          : <span key={i}>{p}</span>
      )}
    </span>
  )
}

function thesisFor(s: ScreenSector): string[] {
  const r1 = s.ret_1m  != null ? `${(s.ret_1m  * 100).toFixed(1)}%` : null
  const r3 = s.ret_3m  != null ? `${(s.ret_3m  * 100).toFixed(1)}%` : null
  const rs = s.rs_pct_cross_sector  != null ? `${Math.round(s.rs_pct_cross_sector  * 100)}%` : null
  const br = s.breadth_pct_stage_2  != null ? `${Math.round(s.breadth_pct_stage_2  * 100)}%` : null
  const bullets: string[] = []
  if (r1 && r3) bullets.push(`1M return **${r1}**, 3M return **${r3}** vs Nifty 500`)
  else if (r1)  bullets.push(`1M return **${r1}** vs Nifty 500`)
  if (rs) bullets.push(`Cross-sector RS percentile: **${rs}**`)
  if (br) bullets.push(`Stage-2 breadth: **${br}** of constituents in uptrend`)
  if (s.vol_regime) bullets.push(`Vol regime: **${s.vol_regime}**`)
  if (!bullets.length) bullets.push(`Sector ranked **#${s.rank}** in the universe`)
  return bullets
}

// ---------------------------------------------------------------------------
// HeroBookBand
// ---------------------------------------------------------------------------

function HeroBookBand({ exposure }: { exposure: SectorBookExposure | null }) {
  if (!exposure) return null
  const book = parseFloat(exposure.book_weight)
  const bench = parseFloat(exposure.benchmark_weight)
  if (!Number.isFinite(book) && !Number.isFinite(bench)) return null
  const wc = classifyWeight(exposure.delta_pp)
  return (
    <div
      className="px-6 py-2.5 border-b border-paper-rule bg-paper-deep/30 flex items-center gap-2 flex-wrap"
      aria-label={`Your book in this sector: ${fmtPp(exposure.book_weight)} vs Nifty 500 weight ${fmtPp(exposure.benchmark_weight)}`}
      data-testid="hero-book-band"
    >
      <span className="font-sans text-[11px] text-ink-secondary">Your book in this sector:</span>
      <span className="font-mono text-[12px] font-semibold tabular-nums text-ink-primary">
        {fmtPp(exposure.book_weight)}
      </span>
      <span className="font-sans text-[11px] text-ink-tertiary">
        vs Nifty 500 weight {fmtPp(exposure.benchmark_weight)}
      </span>
      <span
        className={`inline-flex items-center font-sans font-semibold uppercase rounded-[2px] px-[7px] py-[3px] text-[10px] shrink-0 ${CHIP_CLS[wc]}`}
        style={{ letterSpacing: '0.12em' }}
        aria-label={`Position: ${wc}`}
        data-testid="book-weight-chip"
      >
        {wc}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ConstituentTable
// ---------------------------------------------------------------------------

const TH_BASE = 'px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary'

function ConstituentTable({ stocks, heldIidSet }: { stocks: StockV6Row[]; heldIidSet: Set<string> }) {
  const [visibleCols, setVisibleCols] = useState<ConstituentColKey[]>(DEFAULT_VISIBLE)
  const [chooserOpen, setChooserOpen] = useState(false)
  const visible = useMemo(() => new Set(visibleCols), [visibleCols])

  if (stocks.length === 0) {
    return (
      <p className="font-sans text-sm text-ink-secondary py-6" role="status" aria-live="polite" data-testid="empty-constituents">
        No constituents found in the current universe.
      </p>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider" aria-label="Constituent stocks table">
          Constituents ({stocks.length})
        </h2>
        <ColumnChooser columns={ALL_COLUMNS} visible={visibleCols} onVisibleChange={setVisibleCols}
          onReset={() => setVisibleCols(DEFAULT_VISIBLE)} open={chooserOpen} onOpenChange={setChooserOpen} />
      </div>
      <div className="overflow-x-auto border border-paper-rule rounded-[2px]">
        <table className="w-full border-collapse" aria-label="Sector constituents" role="table">
          <thead>
            <tr className="border-b border-paper-rule bg-paper-deep/40">
              {visible.has('symbol')    && <th className={`${TH_BASE} text-left`} scope="col" aria-label="Symbol">Symbol</th>}
              {visible.has('name')      && <th className={`${TH_BASE} text-left`} scope="col" aria-label="Company name">Name</th>}
              {visible.has('stage')     && <th className={`${TH_BASE} text-left`} scope="col" aria-label="Atlas stage">Stage</th>}
              {visible.has('tape')      && <th className={`${TH_BASE} text-left`} scope="col" aria-label="Conviction tape">Conviction</th>}
              {RET_COLS.filter(c => visible.has(c.key)).map(c => (
                <th key={c.key} className={`${TH_BASE} text-right`} scope="col" aria-label={`${c.label} return`}>{c.label}</th>
              ))}
              {visible.has('rs_pctile') && <th className={`${TH_BASE} text-right`} scope="col" aria-label="Relative strength percentile">RS %ile</th>}
              {visible.has('portfolio') && <th className={`${TH_BASE} text-left`}  scope="col" aria-label="Portfolio book position">Book</th>}
            </tr>
          </thead>
          <tbody>
            {stocks.map((row) => {
              const held = heldIidSet.has(row.iid)
              const hs: HoldingState | null = held ? holdingStateStub() : null
              return (
                <tr key={row.iid} className="border-b border-paper-rule last:border-b-0 hover:bg-paper-deep/30 transition-colors" aria-label={`${row.symbol} constituent row`}>
                  {visible.has('symbol') && (
                    <td className="px-3 py-2 font-mono text-[12px] text-teal" aria-label={`Symbol: ${row.symbol}`}>
                      <LinkedTicker symbol={row.symbol} />
                    </td>
                  )}
                  {visible.has('name') && (
                    <td className="px-3 py-2 font-sans text-[12px] text-ink-primary max-w-[160px] truncate" aria-label={`Company: ${row.company_name ?? row.symbol}`}>
                      {row.company_name ?? row.symbol}
                    </td>
                  )}
                  {visible.has('stage') && (
                    <td className="px-3 py-2 font-sans text-[11px] text-ink-secondary" aria-label={`Stage: ${row.stage ?? '—'}`}>
                      {row.stage ?? '—'}
                    </td>
                  )}
                  {visible.has('tape') && (
                    <td className="px-3 py-2" aria-label="Conviction tape">
                      <ConvictionTape tape={row.conviction_tape} compact />
                    </td>
                  )}
                  {RET_COLS.filter(c => visible.has(c.key)).map(c => {
                    const { text, cls } = signedPct(c.getter(row))
                    return (
                      <td key={c.key} className={`px-3 py-2 font-mono text-[11px] tabular-nums text-right ${cls}`} aria-label={`${c.label} return: ${text}`}>
                        {text}
                      </td>
                    )
                  })}
                  {visible.has('rs_pctile') && (
                    <td className="px-3 py-2 font-mono text-[11px] tabular-nums text-right text-ink-secondary"
                      aria-label={`RS percentile: ${row.rs_pctile_3m != null ? `${Math.round(row.rs_pctile_3m * 100)}%` : '—'}`}>
                      {row.rs_pctile_3m != null ? `${Math.round(row.rs_pctile_3m * 100)}%` : '—'}
                    </td>
                  )}
                  {visible.has('portfolio') && (
                    <td className="px-3 py-2" aria-label={held ? `${row.symbol} held in book` : `${row.symbol} not in book`}>
                      <PortfolioBadge state={hs} variant="compact" />
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SectorDetailClient (exported)
// ---------------------------------------------------------------------------

export interface SectorDetailClientProps {
  sector: ScreenSector
  sectorName: string
  stocks: StockV6Row[]
  exposure: SectorBookExposure | null
  breadth: SectorBreadth | null
  heldIidSet: Set<string>
  snapshotDate: string
}

export function SectorDetailClient({
  sector, sectorName, stocks, exposure, breadth, heldIidSet, snapshotDate,
}: SectorDetailClientProps) {
  const actionVerb = actionVerbFor(sector.sector_state)
  const bullets    = thesisFor(sector)
  const bubbleData = useMemo(() => stocks.map(toBubbleDatum), [stocks])

  return (
    <div className="max-w-[1400px] mx-auto">

      {/* Hero */}
      <header className="px-6 py-5 border-b border-paper-rule" aria-label={`Sector detail hero for ${sectorName}`}>
        <div className="flex items-baseline gap-3 flex-wrap mb-2">
          <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">{sectorName}</h1>
          <StateBadge state={sector.sector_state} />
          <span className="font-sans text-[11px] text-ink-tertiary" aria-label={`Rank ${sector.rank}`}>Rank {sector.rank}</span>
        </div>
        <div className="mb-3">
          <span className="font-sans text-[12px] font-bold uppercase tracking-wider text-ink-primary" aria-label={`Action: ${actionVerb}`}>
            {actionVerb}
          </span>
        </div>
        <ul className="space-y-1" aria-label="Sector thesis">
          {bullets.map((b, i) => (
            <li key={i} className="font-sans text-[12px] text-ink-secondary flex items-start gap-1.5">
              <span className="mt-0.5 shrink-0 text-ink-tertiary">·</span>
              <BulletText text={b} />
            </li>
          ))}
        </ul>
      </header>

      {/* Hero book band */}
      <HeroBookBand exposure={exposure} />

      {/* SectorBookStrip (single variant) */}
      {exposure && (
        <section className="px-6 py-4 border-b border-paper-rule" aria-label="Book vs benchmark exposure">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2">Book exposure</h2>
          <SectorBookStrip exposures={[exposure]} variant="single" />
        </section>
      )}

      {/* SectorBreadthPanel */}
      {breadth && (
        <section className="px-6 py-4 border-b border-paper-rule" aria-label="Sector breadth panel">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2">Breadth</h2>
          <SectorBreadthPanel breadth={breadth} />
        </section>
      )}

      {/* SectorBubbleChart */}
      {bubbleData.length > 0 && (
        <section className="px-6 py-4 border-b border-paper-rule" aria-label="Constituent risk-return chart">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2">
            Risk vs return (3M, {snapshotDate})
          </h2>
          <BubbleRiskReturnChart
            data={bubbleData} xLabel="Risk (inv RS %ile)" yLabel="3M Return"
            sizeLabel="Uniform" className="h-[340px]"
          />
        </section>
      )}

      {/* Constituent table */}
      <section className="px-6 py-4" aria-label="Constituent stocks">
        <ConstituentTable stocks={stocks} heldIidSet={heldIidSet} />
      </section>
    </div>
  )
}

export default SectorDetailClient
