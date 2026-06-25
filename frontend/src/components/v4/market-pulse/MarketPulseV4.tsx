// ── MARKET PULSE (pilot of the "Graphite Terminal" language) ──
// Native foundation_staging only (no atlas.* reads — the Weinstein verdict/
// scorecard/worklist of §3.a are dropped). Leads with highlighted real numbers,
// clickable stat tiles, sector leadership, and the signature Decile Ladder fed
// by the day's highest-conviction stock. Server component; data batched into
// ≤3 Promise.all groups for the session pooler.
import Link from 'next/link'
import { getCurrentRegime } from '@/lib/queries/regime'
import { getBreadthSeries } from '@/lib/queries/v6/breadth'
import { getTierReturns, getMacroContext, getBreadthTable } from '@/lib/queries/v6/market_pulse'
import { getStocksDecileList, getStockDecile, getStockEvidence } from '@/lib/queries/v6/stock_lens'
import { StatCard, type Tone } from '../ui/StatCard'
import { Panel } from '../ui/Panel'
import { DecileLadder } from '../ui/DecileLadder'
import { stockToLadder } from '../adapters/stockToLadder'
import { RegimeChip, BreadthTablePanel, TierReturnsPanel, MacroPanel, SectorLeadershipPanel, type SectorRollup } from './MarketPulsePanels'
import { MarketPulseBreadthCharts } from './MarketPulseBreadthCharts'

const fmtInt = (n: number | null | undefined) => (n == null ? '—' : Math.round(n).toLocaleString('en-IN'))
const fmtSigned = (n: number | null | undefined) => (n == null ? '—' : `${n >= 0 ? '+' : ''}${Math.round(n).toLocaleString('en-IN')}`)
const pctTone = (pct: number | null): Tone => (pct == null ? 'neutral' : pct >= 50 ? 'pos' : 'neg')
function fmtDate(d: unknown): string | null {
  if (!d) return null
  return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10)
}

export async function MarketPulseV4() {
  // Group A — regime + latest breadth counts + scored universe (for spotlight + sectors)
  const [regime, breadthSeries, stocksList] = await Promise.all([
    getCurrentRegime().catch(() => null),
    getBreadthSeries(1).catch(() => []),
    getStocksDecileList().catch(() => []),
  ])

  if (!regime) {
    return (
      <div className="min-h-screen bg-surface-base font-sans text-txt-1">
        <div className="mx-auto max-w-[1280px] px-6 py-10">
          <Panel title="No regime data"><p className="font-sans text-[13px] text-txt-2">Run the nightly pipeline first.</p></Panel>
        </div>
      </div>
    )
  }

  // Group B — the three native market-pulse tables
  const [tier, macro, breadthTable] = await Promise.all([
    getTierReturns().catch(() => ({ windows: [], smallcap_rs_z: null })),
    getMacroContext().catch(() => ({ rows: [], as_of: null })),
    getBreadthTable().catch(() => ({ rows: [], as_of: null })),
  ])

  // Spotlight = highest-leadership name today (ties → higher strength)
  const spotlight = [...stocksList]
    .filter((r) => r.lead != null)
    .sort((a, b) => b.lead - a.lead || (b.strength ?? 0) - (a.strength ?? 0))[0] ?? null

  // Group C — the spotlight stock's full lens read + real numbers
  const [spotDecile, spotEvidence] = spotlight
    ? await Promise.all([getStockDecile(spotlight.symbol).catch(() => null), getStockEvidence(spotlight.symbol).catch(() => null)])
    : [null, null]
  const ladder = spotDecile ? stockToLadder(spotDecile, spotEvidence) : null

  // Sector leadership — real, derived from per-stock strength (≥5 names per sector)
  const bySector = new Map<string, { sum: number; n: number; leaders: number }>()
  for (const r of stocksList) {
    if (!r.sector || r.strength == null) continue
    const e = bySector.get(r.sector) ?? { sum: 0, n: 0, leaders: 0 }
    e.sum += r.strength
    e.n += 1
    if (r.lead >= 2) e.leaders += 1
    bySector.set(r.sector, e)
  }
  const sectors: SectorRollup[] = [...bySector.entries()]
    .filter(([, e]) => e.n >= 5)
    .map(([name, e]) => ({ name, avg: e.sum / e.n, n: e.n, leaders: e.leaders }))
    .sort((a, b) => b.avg - a.avg)
  const topSectors = sectors.slice(0, 5)
  const weakSectors = sectors.slice(-5).reverse()

  // Stat tiles (real breadth counts; clickable → filtered lists)
  const b = breadthSeries.length ? breadthSeries[breadthSeries.length - 1] : null
  const deploymentPct = Number.isFinite(parseFloat(String(regime.deployment_multiplier)))
    ? Math.round(parseFloat(String(regime.deployment_multiplier)) * 100)
    : null
  const asOf = fmtDate(regime.date) ?? (b ? b.date : null)
  const pctOf = (count: number, total: number) => (total ? Math.round((count / total) * 100) : null)

  return (
    <div className="min-h-screen bg-surface-base font-sans text-txt-1">
      <div className="mx-auto max-w-[1280px] px-6 py-7">
        {/* header band */}
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-num text-[10px] uppercase tracking-[0.2em] text-txt-3">Market Pulse · NSE</p>
            <h1 className="mt-1.5 font-display text-[32px] font-bold leading-none tracking-tight text-txt-1">Markets Today</h1>
            {asOf && <p className="mt-2 font-num text-[11px] tabular-nums text-txt-3">as of {asOf}</p>}
          </div>
          <RegimeChip state={regime.regime_state} deploymentPct={deploymentPct} />
        </header>

        {/* stat grid */}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {b && (
            <>
              {([['Above 21-EMA', b.above_21, 21], ['Above 50-EMA', b.above_50, 50], ['Above 200-EMA', b.above_200, 200]] as const).map(([label, count, ema]) => {
                const pct = pctOf(count, b.n_members)
                return (
                  <StatCard key={ema} label={label} value={fmtInt(count)} tone={pctTone(pct)} href={`/stocks?ema=${ema}`}
                    sub={`${pct ?? '—'}% of ${fmtInt(b.n_members)}`} />
                )
              })}
              <StatCard label="Golden cross" value={fmtInt(b.gc_50_200)} tone="brand" sub="50-EMA > 200-EMA" href="/stocks?gc=1" />
              <StatCard label="Net new highs" value={fmtSigned(b.net_new_highs)} tone={b.net_new_highs >= 0 ? 'pos' : 'neg'} sub="52-week H − L" href="/stocks?nh=1" />
            </>
          )}
          <StatCard label="Smallcap RS" value={tier.smallcap_rs_z == null ? '—' : `${tier.smallcap_rs_z >= 0 ? '+' : ''}${tier.smallcap_rs_z.toFixed(1)}`} unit="σ"
            tone={tier.smallcap_rs_z == null ? 'neutral' : tier.smallcap_rs_z >= 0 ? 'pos' : 'neg'} sub="vs large-cap · 1y" />
        </div>

        {/* sector leadership */}
        {topSectors.length > 0 && (
          <div className="mb-6"><SectorLeadershipPanel top={topSectors} weak={weakSectors} /></div>
        )}

        {/* breadth + cap-tier */}
        <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
          {breadthTable.rows.length > 0 && <BreadthTablePanel rows={breadthTable.rows} asOf={breadthTable.as_of} />}
          {tier.windows.length > 0 && <TierReturnsPanel data={tier} />}
        </div>

        {/* breadth participation history — §3.e */}
        {breadthSeries.length > 1 && (
          <div className="mb-6"><MarketPulseBreadthCharts series={breadthSeries} /></div>
        )}

        {/* conviction spotlight — the signature Decile Ladder, real data */}
        {ladder && spotlight && (
          <div className="mb-6">
            <Panel
              eyebrow="Highest conviction today"
              title={spotlight.symbol}
              action={<Link href={`/stocks/${spotlight.symbol}`} className="font-num text-[11px] text-brand hover:underline">Open stock →</Link>}
            >
              <p className="mb-4 font-sans text-[12px] text-txt-2">{spotlight.name ?? spotlight.symbol} · {ladder.cohortLabel}{spotlight.sector ? ` · ${spotlight.sector}` : ''}</p>
              <DecileLadder
                lenses={ladder.lenses}
                strength={ladder.strength}
                leadership={ladder.leadership}
                cohortLabel={ladder.cohortLabel}
                defaultOpenKey={ladder.topLensKey ?? undefined}
                note={<>Each lens is a <strong className="text-txt-1">decile within its cap cohort</strong> (D10 = top 10%) — no black-box composite. Expand a lens for the real numbers behind the score.</>}
              />
            </Panel>
          </div>
        )}

        {/* macro */}
        {macro.rows.length > 0 && <MacroPanel rows={macro.rows} asOf={macro.as_of} />}
      </div>
    </div>
  )
}
