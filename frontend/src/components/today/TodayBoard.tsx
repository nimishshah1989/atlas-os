// ── TODAY — the Pulse change-feed ──
// "What changed since last close", conviction-first. A re-framing of last night's
// pipeline output (atlas_lens_scores_daily / lens_filings / ohlcv_stock) — no new
// tables, ingestion, or cron. Sibling to the unchanged Market Pulse page at /.
// Server component; queries batched in two small waves for the session pooler.
import Link from 'next/link'
import { getCurrentRegime } from '@/lib/queries/regime'
import { getBreadthSeries } from '@/lib/queries/breadth'
import { getConvictionMoves, getTodayMovers, getAnnouncements, getUpcomingEvents } from '@/lib/queries/today'
import { RegimeChip } from '../market-pulse/MarketPulsePanels'
import { StatCard, type Tone } from '../ui/StatCard'
import { ConvictionMovesPanel, MoversPanel } from './TodayModules'
import { Announcements } from './Announcements'
import { UpcomingEvents } from './UpcomingEvents'

const MON = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function longDate(d: string | null): string | null {
  if (!d) return null
  const [y, m, day] = d.split('-')
  return `${day.replace(/^0/, '')} ${MON[Number(m)] ?? m} ${y}`
}
const pctTone = (pct: number | null): Tone => (pct == null ? 'neutral' : pct >= 50 ? 'pos' : 'neg')

export async function TodayBoard() {
  // Wave 1 — the two universe-wide reads (lens diff + ohlcv delta).
  const [conviction, movers] = await Promise.all([
    getConvictionMoves().catch(() => ({ asOf: null, prevOf: null, entered: [], fellOut: [], jumps: [] })),
    getTodayMovers().catch(() => ({ gainers: [], losers: [], asOf: null })),
  ])
  // Wave 2 — the light context reads.
  const [regime, breadth, catalysts, events] = await Promise.all([
    getCurrentRegime().catch(() => null),
    getBreadthSeries(1).catch(() => []),
    getAnnouncements().catch(() => ({ catalysts: [], today: null, total: 0 })),
    getUpcomingEvents().catch(() => ({ today: null, events: [] })),
  ])

  const asOf = conviction.asOf ?? movers.asOf
  const b = breadth.length ? breadth[breadth.length - 1] : null
  const deploymentPct = regime && Number.isFinite(parseFloat(String(regime.deployment_multiplier)))
    ? Math.round(parseFloat(String(regime.deployment_multiplier)) * 100)
    : null
  const pctOf = (count: number, total: number) => (total ? Math.round((count / total) * 100) : null)
  const p50 = b ? pctOf(b.above_50, b.n_members) : null
  const p200 = b ? pctOf(b.above_200, b.n_members) : null

  return (
    <div className="min-h-screen bg-surface-base font-sans text-txt-1">
      <div className="mx-auto max-w-[1680px] px-6 py-7">
        {/* header */}
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-num text-[10px] uppercase tracking-[0.2em] text-txt-3">Markets · Today</p>
            <h1 className="mt-1.5 font-display text-[32px] font-bold leading-none tracking-tight text-txt-1">Movers &amp; Shakers</h1>
            {asOf && (
              <p className="mt-2 font-num text-[11px] tabular-nums text-txt-3">
                as of {longDate(asOf)}
                {conviction.prevOf && <span className="text-txt-3"> · vs prior close {longDate(conviction.prevOf)}</span>}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {regime && <RegimeChip state={regime.regime_state} deploymentPct={deploymentPct} />}
            <Link href="/" className="font-num text-[11px] text-txt-3 hover:text-brand">Full Market Pulse →</Link>
          </div>
        </header>

        {/* market context strip */}
        {b && (
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Above 50-EMA" value={`${p50 ?? '—'}%`} tone={pctTone(p50)} sub={`of ${b.n_members.toLocaleString('en-IN')}`} href="/stocks?ema=50" />
            <StatCard label="Above 200-EMA" value={`${p200 ?? '—'}%`} tone={pctTone(p200)} sub={`of ${b.n_members.toLocaleString('en-IN')}`} href="/stocks?ema=200" />
            <StatCard label="Golden crosses" value={b.gc_50_200.toLocaleString('en-IN')} tone="brand" sub="50-EMA > 200-EMA" href="/stocks?gc=1" />
            <StatCard label="Net new highs" value={`${b.net_new_highs >= 0 ? '+' : ''}${b.net_new_highs.toLocaleString('en-IN')}`} tone={b.net_new_highs >= 0 ? 'pos' : 'neg'} sub="52-week H − L" href="/stocks?nh=1" />
          </div>
        )}

        {/* the week ahead — upcoming events calendar */}
        {events.events.length > 0 && (
          <div className="mb-6"><UpcomingEvents events={events.events} today={events.today} /></div>
        )}

        {/* flagship — conviction moves */}
        <div className="mb-6"><ConvictionMovesPanel data={conviction} /></div>

        {/* movers + announcements */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <MoversPanel gainers={movers.gainers} losers={movers.losers} />
          <Announcements catalysts={catalysts.catalysts} today={catalysts.today} />
        </div>
      </div>
    </div>
  )
}
