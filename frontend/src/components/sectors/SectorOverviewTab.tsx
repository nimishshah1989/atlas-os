// frontend/src/components/sectors/SectorOverviewTab.tsx
import type { ReactNode } from 'react'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { SectorMetricHistoryRow, SectorStateRow } from '@/lib/queries/sectors'
import type { SectorBriefSnapshot } from '@/lib/queries/sector-deep-dive'
import type { SectorDecision } from '@/lib/sectors-decision'
import { SectorDrawerSnapshot } from './SectorDrawerSnapshot'
import { SectorDrawerStateStats } from './SectorDrawerStateStats'
import type { MarketRegimeRow } from '@/lib/queries/regime'
import { MarketRegimeBanner } from './MarketRegimeBanner'

type SnapshotWithDecision = SectorBriefSnapshot & { decision: SectorDecision }

function pctStr(v: string | null | undefined, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function rawPct(v: string | null | undefined, digits = 0): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(digits)}%`
}

function Commentary({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col justify-center h-full px-5 py-4 bg-paper-rule/5 border border-paper-rule/40 rounded-sm">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
        {title}
      </div>
      <div className="font-sans text-xs text-ink-secondary leading-relaxed space-y-2">
        {children}
      </div>
    </div>
  )
}

function interpretRS(v: string | null | undefined): ReactNode {
  if (v == null) return <p>No RS data available for this period.</p>
  const n = parseFloat(v) * 100
  if (n >= 10) return (
    <>
      <p>This sector is <span className="text-signal-pos font-semibold">strongly outperforming</span> Nifty 500 by {n.toFixed(1)}pp over 3 months.</p>
      <p>Institutions are rotating money into this sector. Sustaining RS above +5% qualifies as a sector leadership position.</p>
    </>
  )
  if (n >= 2) return (
    <>
      <p>Sector is <span className="text-signal-pos font-medium">modestly leading</span> Nifty 500 by {n.toFixed(1)}pp over 3 months.</p>
      <p>Positive but not yet strong leadership. Watch for RS expanding above +5% to confirm a durable trend.</p>
    </>
  )
  if (n >= -2) return (
    <>
      <p>Sector is <span className="text-ink-secondary font-medium">roughly in line</span> with Nifty 500 ({pctStr(v)}).</p>
      <p>No meaningful edge vs. the index. Neutral positioning — wait for a directional breakout in RS.</p>
    </>
  )
  if (n >= -10) return (
    <>
      <p>Sector is <span className="text-signal-neg font-medium">underperforming</span> Nifty 500 by {Math.abs(n).toFixed(1)}pp.</p>
      <p>Capital is leaving this sector. Avoid new exposure until RS turns positive for at least 4–6 weeks.</p>
    </>
  )
  return (
    <>
      <p>Sector is <span className="text-signal-neg font-semibold">sharply lagging</span> Nifty 500 by {Math.abs(n).toFixed(1)}pp over 3 months.</p>
      <p>This level of underperformance signals structural selling. Do not try to pick bottoms here.</p>
    </>
  )
}

function interpretBreadth(v: string | null | undefined): ReactNode {
  if (v == null) return <p>No breadth data available.</p>
  const n = parseFloat(v) * 100
  if (n >= 80) return (
    <>
      <p><span className="text-signal-pos font-semibold">{n.toFixed(0)}% of stocks</span> in this sector are above their 50-day EMA.</p>
      <p>Nearly everyone is participating. Broad strength like this is durable — trends supported by wide participation don't break easily.</p>
    </>
  )
  if (n >= 60) return (
    <>
      <p><span className="text-signal-pos font-medium">{n.toFixed(0)}%</span> of stocks are above their 50-day EMA.</p>
      <p>Majority participation. A healthy setup, though not peak bullish. Sustained above 60% confirms sector strength.</p>
    </>
  )
  if (n >= 40) return (
    <>
      <p><span className="text-signal-warn font-medium">{n.toFixed(0)}%</span> of stocks are above their 50-day EMA — mixed breadth.</p>
      <p>The sector is split. Some stocks are fine, others aren't. Watch whether breadth dips below 40% (deterioration) or recovers to 60%+ (confirmation).</p>
    </>
  )
  if (n >= 20) return (
    <>
      <p><span className="text-signal-neg font-medium">Only {n.toFixed(0)}%</span> of stocks are above their 50-day EMA.</p>
      <p>Broad weakness. Even if the sector index hasn't collapsed, the underlying stocks are suffering. This is a late-cycle deterioration signal.</p>
    </>
  )
  return (
    <>
      <p><span className="text-signal-neg font-semibold">{n.toFixed(0)}% breadth</span> — nearly all stocks are below their 50-day EMA.</p>
      <p>Capitulation-level weakness. This is a capital preservation zone, not an entry point.</p>
    </>
  )
}

function interpretRSPartic(v: string | null | undefined): ReactNode {
  if (v == null) return <p>No RS participation data available.</p>
  const n = parseFloat(v) * 100
  if (n >= 70) return (
    <>
      <p><span className="text-signal-pos font-semibold">{n.toFixed(0)}%</span> of stocks in this sector are outperforming Nifty 500.</p>
      <p>Leadership is broad — the sector's RS is not just one or two names pulling the average. This is the most durable form of sector strength.</p>
    </>
  )
  if (n >= 50) return (
    <>
      <p><span className="text-signal-pos font-medium">{n.toFixed(0)}%</span> of stocks are outperforming Nifty 500.</p>
      <p>Majority of the sector is participating in the outperformance. Reasonably healthy — not all-clear, but conviction is building.</p>
    </>
  )
  if (n >= 30) return (
    <>
      <p><span className="text-signal-warn font-medium">{n.toFixed(0)}%</span> of stocks outperforming Nifty 500 — below the 50% threshold.</p>
      <p>Fewer than half the sector's stocks are earning their keep. The sector might look okay at the index level, but constituents are struggling.</p>
    </>
  )
  return (
    <>
      <p><span className="text-signal-neg font-semibold">Only {n.toFixed(0)}%</span> of stocks are outperforming Nifty 500.</p>
      <p>The few outperformers are masking widespread weakness. Check concentration — if it's high, one name is doing all the work.</p>
    </>
  )
}

function interpret3MReturn(v: string | null | undefined): ReactNode {
  if (v == null) return <p>No return data available.</p>
  const n = parseFloat(v) * 100
  if (n >= 15) return (
    <>
      <p>Average 3-month return of <span className="text-signal-pos font-semibold">+{n.toFixed(1)}%</span> — a strong absolute return.</p>
      <p>Remember: this is absolute performance, not relative. A sector can have strong absolute returns but still lag the market if Nifty ran harder. RS tells you if this gain is actually worth owning.</p>
    </>
  )
  if (n >= 5) return (
    <>
      <p>Average 3-month return of <span className="text-signal-pos font-medium">+{n.toFixed(1)}%</span> — moderate positive absolute return.</p>
      <p>Stocks are moving up on average. Compare to RS column to judge whether this gain beats the market or merely moves with it.</p>
    </>
  )
  if (n >= -5) return (
    <>
      <p>Average 3-month return of <span className="text-ink-secondary font-medium">{n.toFixed(1)}%</span> — roughly flat.</p>
      <p>Sector stocks have neither advanced nor declined meaningfully in absolute terms over this period. Opportunity cost applies unless RS is positive.</p>
    </>
  )
  return (
    <>
      <p>Average 3-month return of <span className="text-signal-neg font-semibold">{n.toFixed(1)}%</span> — negative absolute return.</p>
      <p>Sector stocks have lost money in absolute terms over 3 months. Unless this is bottoming action with improving RS, it warrants underweight positioning.</p>
    </>
  )
}

function interpretEMA(v10: string | null | undefined, v20: string | null | undefined): ReactNode {
  if (v10 == null) return <p>No EMA momentum data available for this period.</p>
  const r10 = (parseFloat(v10) - 1) * 100
  const r20 = v20 != null ? (parseFloat(v20) - 1) * 100 : null
  const aboveBoth = r10 > 0 && (r20 == null || r20 > 0)
  const belowBoth = r10 < 0 && (r20 == null || r20 < 0)
  const golden = r20 != null && r10 > r20

  if (aboveBoth && golden) return (
    <>
      <p>Stocks are <span className="text-signal-pos font-semibold">{r10.toFixed(1)}% above</span> their 10-day EMA and {r20!.toFixed(1)}% above the 20-day.</p>
      <p>The 10-day leading the 20-day confirms momentum building. This is the strongest EMA setup — price is extended above both short-term trend lines.</p>
    </>
  )
  if (aboveBoth) return (
    <>
      <p>Stocks are <span className="text-signal-pos font-medium">{r10.toFixed(1)}% above</span> their 10-day EMA.</p>
      <p>Above both trend lines but the 10-day is no longer leading — momentum may be cooling. Still constructive but watch for the 10d crossing below the 20d.</p>
    </>
  )
  if (!belowBoth && r10 > 0) return (
    <>
      <p>Stocks are <span className="text-signal-warn font-medium">{r10.toFixed(1)}% above</span> the 10-day EMA but {r20 != null ? Math.abs(r20).toFixed(1) + '% below' : 'near'} the 20-day.</p>
      <p>Mixed momentum — the sector is in transition. The 10-day crossing the 20-day from below would be the first meaningful bullish signal.</p>
    </>
  )
  if (belowBoth) return (
    <>
      <p>Stocks are <span className="text-signal-neg font-semibold">{Math.abs(r10).toFixed(1)}% below</span> their 10-day EMA.</p>
      <p>Broad technical deterioration. Stocks trading below both short-term EMAs are in a downtrend — do not chase bounces until both are recaptured.</p>
    </>
  )
  return <p>EMA signal mixed — {r10.toFixed(1)}% vs 10-day EMA.</p>
}

export function SectorOverviewTab({
  snapshot,
  metricHistory,
  stateHistory,
  range,
  regime,
}: {
  snapshot: SnapshotWithDecision
  metricHistory: SectorMetricHistoryRow[]
  stateHistory: SectorStateRow[]
  range: string
  regime: MarketRegimeRow | null
}) {
  const dateStr = (d: Date | string): string =>
    d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10)

  const rsData       = metricHistory.map(r => ({ date: dateStr(r.date), value: r.bottomup_rs_3m_nifty500 != null ? parseFloat(r.bottomup_rs_3m_nifty500) : null }))
  const breadthData  = metricHistory.map(r => ({ date: dateStr(r.date), value: r.participation_50        != null ? parseFloat(r.participation_50)        : null }))
  const rsParticData = metricHistory.map(r => ({ date: dateStr(r.date), value: r.participation_rs        != null ? parseFloat(r.participation_rs)        : null }))
  const ret3mData    = metricHistory.map(r => ({ date: dateStr(r.date), value: r.bottomup_ret_3m         != null ? parseFloat(r.bottomup_ret_3m)         : null }))
  const ema10Data    = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.bottomup_ema_10_ratio != null ? (parseFloat(r.bottomup_ema_10_ratio) - 1) * 100 : null,
  }))

  const latest = metricHistory[metricHistory.length - 1]

  return (
    <div>
      {regime && <MarketRegimeBanner regime={regime} />}
      <div className="px-6 py-6 space-y-6">
      {/* Snapshot tiles */}
      <SectorDrawerSnapshot snapshot={{
        sector_name: snapshot.sector_name,
        constituent_count: snapshot.constituent_count,
        bottomup_ret_1m: snapshot.bottomup_ret_1m,
        bottomup_ret_3m: snapshot.bottomup_ret_3m,
        bottomup_ret_6m: snapshot.bottomup_ret_6m,
        bottomup_rs_3m_nifty500: snapshot.bottomup_rs_3m_nifty500,
        participation_50: snapshot.participation_50,
        participation_rs: snapshot.participation_rs,
        leadership_concentration: snapshot.leadership_concentration,
        sector_state: snapshot.sector_state,
        bottomup_state: snapshot.bottomup_state,
        topdown_state: snapshot.topdown_state,
        divergence_flag: snapshot.divergence_flag,
        bottomup_rs_state: snapshot.bottomup_rs_state,
        bottomup_momentum_state: snapshot.bottomup_momentum_state,
        data_date: snapshot.data_date,
        bottomup_ema_10_ratio: snapshot.bottomup_ema_10_ratio,
        bottomup_ema_20_ratio: snapshot.bottomup_ema_20_ratio,
        topdown_ret_1m: snapshot.topdown_ret_1m,
        topdown_ret_3m: snapshot.topdown_ret_3m,
        topdown_rs_3m_nifty500: snapshot.topdown_rs_3m_nifty500,
        topdown_index_code: snapshot.topdown_index_code,
        participation_rs_pct: snapshot.participation_rs_pct,
        decision: snapshot.decision,
      }} />

      {/* State stats */}
      <SectorDrawerStateStats history={stateHistory} range={range} />

      {/* Charts + commentary — 2 column layout */}
      <div>
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-4">
          Metric History — {range}
        </div>

        {metricHistory.length === 0 ? (
          <p className="font-sans text-xs text-ink-tertiary">No metric history available for this range.</p>
        ) : (
          <div className="space-y-5">
            {/* RS vs Nifty 500 */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Relative Strength vs Nifty 500 (3M)"
                description="How this sector's stocks are performing relative to the broader Nifty 500 over a rolling 3-month window. Positive means leadership; negative means lagging."
                currentValue={pctStr(latest?.bottomup_rs_3m_nifty500)}
                isBullish={latest?.bottomup_rs_3m_nifty500 != null ? parseFloat(latest.bottomup_rs_3m_nifty500) > 0 : null}
                data={rsData}
                refLine={0}
                refLabel="0"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`RS Today · ${pctStr(latest?.bottomup_rs_3m_nifty500)}`}>
                {interpretRS(latest?.bottomup_rs_3m_nifty500)}
              </Commentary>
            </div>

            {/* Breadth */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Breadth — % Stocks Above 50-Day EMA"
                description="Percentage of stocks within this sector currently trading above their 50-day EMA. Above 50% means the majority of the sector is in a medium-term uptrend."
                currentValue={rawPct(latest?.participation_50)}
                isBullish={latest?.participation_50 != null ? parseFloat(latest.participation_50) > 0.5 : null}
                data={breadthData}
                refLine={0.5}
                refLabel="50%"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`Breadth Today · ${rawPct(latest?.participation_50)}`}>
                {interpretBreadth(latest?.participation_50)}
              </Commentary>
            </div>

            {/* RS Participation */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="RS Participation — % Stocks with Positive RS"
                description="Fraction of the sector's stocks outperforming Nifty 500. High = leadership is broad, not concentrated in 1-2 names."
                currentValue={rawPct(latest?.participation_rs)}
                isBullish={latest?.participation_rs != null ? parseFloat(latest.participation_rs) > 0.5 : null}
                data={rsParticData}
                refLine={0.5}
                refLabel="50%"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`RS Participation Today · ${rawPct(latest?.participation_rs)}`}>
                {interpretRSPartic(latest?.participation_rs)}
              </Commentary>
            </div>

            {/* 3M Return */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="3-Month Return (avg of constituents)"
                description="Average 3-month price return of stocks in the sector. Different from RS — this is absolute performance, not relative."
                currentValue={pctStr(latest?.bottomup_ret_3m)}
                isBullish={latest?.bottomup_ret_3m != null ? parseFloat(latest.bottomup_ret_3m) > 0 : null}
                data={ret3mData}
                refLine={0}
                refLabel="0"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`3M Return Today · ${pctStr(latest?.bottomup_ret_3m)}`}>
                {interpret3MReturn(latest?.bottomup_ret_3m)}
              </Commentary>
            </div>

            {/* EMA Momentum Quality */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="EMA Momentum Quality — Avg % Above 10-Day EMA"
                description="Average percentage by which sector stocks trade above (or below) their 10-day EMA. Positive = stocks trending up short-term. Negative = short-term downtrend. Complements RS by showing price momentum rather than relative strength."
                currentValue={latest?.bottomup_ema_10_ratio != null
                  ? `${((parseFloat(latest.bottomup_ema_10_ratio) - 1) * 100).toFixed(1)}%`
                  : '—'}
                isBullish={latest?.bottomup_ema_10_ratio != null
                  ? parseFloat(latest.bottomup_ema_10_ratio) > 1
                  : null}
                data={ema10Data}
                refLine={0}
                refLabel="0"
                variant="area"
              />
              <Commentary title={`EMA Quality · ${latest?.bottomup_ema_10_ratio != null
                ? ((parseFloat(latest.bottomup_ema_10_ratio) - 1) * 100).toFixed(1) + '% vs 10d'
                : '—'}`}>
                {interpretEMA(latest?.bottomup_ema_10_ratio, latest?.bottomup_ema_20_ratio)}
              </Commentary>
            </div>
          </div>
        )}
      </div>
    </div>
    </div>
  )
}
