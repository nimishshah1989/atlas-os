// ── MARKET PULSE (the "Graphite Terminal" language) ──
// A self-explanatory market summary: an index strip (where the market is), breadth as real
// counts (today vs a week / month ago), and a concise Sector Leadership split (the 5 strongest
// vs 5 weakest sectors, with why). The heatmap + RRG rotation live on the sector page, not here.
// Server component; queries batched for the session pooler.
import { getCurrentRegime } from '@/lib/queries/regime'
import { getBreadthSeries } from '@/lib/queries/v6/breadth'
import { getTierReturns, getIndexStrip } from '@/lib/queries/v6/market_pulse'
import { getStocksDecileList, LEAD_DECILE } from '@/lib/queries/v6/stock_lens'
import { StatCard, type Tone } from '../ui/StatCard'
import { Panel } from '../ui/Panel'
import { RegimeChip, BreadthTablePanel, TierReturnsPanel, SectorLeadershipPanel, type SectorRollup, type StockLensRow, type BreadthCountRow } from './MarketPulsePanels'
import { IndexStrip } from './IndexStrip'
import { MarketPulseBreadthCharts } from './MarketPulseBreadthCharts'

const fmtInt = (n: number | null | undefined) => (n == null ? '—' : Math.round(n).toLocaleString('en-IN'))
const fmtSigned = (n: number | null | undefined) => (n == null ? '—' : `${n >= 0 ? '+' : ''}${Math.round(n).toLocaleString('en-IN')}`)
const pctTone = (pct: number | null): Tone => (pct == null ? 'neutral' : pct >= 50 ? 'pos' : 'neg')
function fmtDate(d: unknown): string | null {
  if (!d) return null
  return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10)
}

export async function MarketPulseV4() {
  // Regime first (alone) so we can early-return without holding other connections.
  const regime = await getCurrentRegime().catch(() => null)
  if (!regime) {
    return (
      <div className="min-h-screen bg-surface-base font-sans text-txt-1">
        <div className="mx-auto max-w-[1280px] px-6 py-10">
          <Panel title="No regime data"><p className="font-sans text-[13px] text-txt-2">Run the nightly pipeline first.</p></Panel>
        </div>
      </div>
    )
  }

  // The scored universe is the heavy query (~2k rows) — fetch it ALONE so it never
  // holds a connection alongside the others, keeping Market Pulse within the dev
  // session pooler's 15-client cap under concurrent browser load.
  const stocksList = await getStocksDecileList().catch(() => [])

  // The remaining native-fs panels — light, batched together.
  const [breadthSeries, tier, indexStrip] = await Promise.all([
    getBreadthSeries(10).catch(() => []),
    getTierReturns().catch(() => ({ windows: [], smallcap_rs_z: null })),
    getIndexStrip().catch(() => []),
  ])

  // Sector leadership — average conviction per sector (≥5 names). A stock "leads" a lens when
  // it sits in the top three deciles of its cap cohort (D≥8). Split into 5 strongest / weakest.
  const LEAD_D = LEAD_DECILE
  const bySector = new Map<string, { sum: number; n: number; tech: number; fund: number }>()
  const stocksBySector: Record<string, StockLensRow[]> = {}
  for (const r of stocksList) {
    if (!r.sector || r.strength == null) continue
    const e = bySector.get(r.sector) ?? { sum: 0, n: 0, tech: 0, fund: 0 }
    e.sum += r.strength
    e.n += 1
    if ((r.d_tech ?? 0) >= LEAD_D) e.tech += 1
    if ((r.d_fund ?? 0) >= LEAD_D) e.fund += 1
    bySector.set(r.sector, e)
    ;(stocksBySector[r.sector] ??= []).push({
      symbol: r.symbol, name: r.name,
      d_tech: r.d_tech, d_fund: r.d_fund, d_cat: r.d_cat, d_flow: r.d_flow, d_val: r.d_val,
      lead: r.lead, strength: r.strength,
    })
  }
  const sectors: SectorRollup[] = [...bySector.entries()]
    .filter(([, e]) => e.n >= 5)
    .map(([name, e]) => ({ name, avg: e.sum / e.n, n: e.n, techLeaders: e.tech, fundLeaders: e.fund }))
    .sort((a, b) => b.avg - a.avg)
  const topSectors = sectors.slice(0, 5)
  const weakSectors = sectors.slice(-5).reverse()

  // Market breadth as ABSOLUTE COUNTS at three points in time (today, a week ago, a month
  // ago) — straight from the Nifty-500 breadth series. The trend reads directly, no deltas.
  const bAgo = (k: number) => (breadthSeries.length > k ? breadthSeries[breadthSeries.length - 1 - k] : null)
  const bCountRow = (label: string, field: 'above_21' | 'above_50' | 'above_200' | 'gc_50_200' | 'net_new_highs'): BreadthCountRow => {
    const at = (row: ReturnType<typeof bAgo>) => (row ? (row[field] as number) : null)
    return { label, today: at(bAgo(0)), wkAgo: at(bAgo(5)), moAgo: at(bAgo(21)) }
  }

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

        {/* broad-market index strip */}
        {indexStrip.length > 0 && <IndexStrip quotes={indexStrip} />}

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

        {/* sector leadership — concise leading / lagging split */}
        {sectors.length > 0 && (
          <div className="mb-6"><SectorLeadershipPanel top={topSectors} weak={weakSectors} stocksBySector={stocksBySector} /></div>
        )}

        {/* breadth (absolute counts) + cap-tier returns */}
        <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
          {b && (
            <BreadthTablePanel
              rows={[
                bCountRow('Above 21-EMA', 'above_21'),
                bCountRow('Above 50-EMA', 'above_50'),
                bCountRow('Above 200-EMA', 'above_200'),
                bCountRow('Golden crosses', 'gc_50_200'),
                bCountRow('Net new highs', 'net_new_highs'),
              ]}
              total={b.n_members}
              asOf={b.date}
            />
          )}
          {tier.windows.length > 0 && <TierReturnsPanel data={tier} />}
        </div>

        {/* breadth participation history */}
        {breadthSeries.length > 1 && (
          <div className="mb-6"><MarketPulseBreadthCharts series={breadthSeries} /></div>
        )}

      </div>
    </div>
  )
}
