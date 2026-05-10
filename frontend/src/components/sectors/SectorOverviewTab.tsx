// frontend/src/components/sectors/SectorOverviewTab.tsx
// allow-large: 8 metric charts with inline commentary functions — each chart+commentary pair is a cohesive unit; splitting would scatter related logic
import type { ReactNode } from 'react'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { BreadthWaterfallRow, SectorMetricHistoryRow, SectorStateRow } from '@/lib/queries/sectors'
import type { SectorBriefSnapshot } from '@/lib/queries/sector-deep-dive'
import type { SectorDecision } from '@/lib/sectors-decision'
import { SectorDrawerSnapshot } from './SectorDrawerSnapshot'
import { SectorDrawerStateStats } from './SectorDrawerStateStats'
import type { MarketRegimeRow } from '@/lib/queries/regime'
import { MarketRegimeBanner } from './MarketRegimeBanner'
import { BreadthWaterfall } from './BreadthWaterfall'

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
  breadthData,
}: {
  snapshot: SnapshotWithDecision
  metricHistory: SectorMetricHistoryRow[]
  stateHistory: SectorStateRow[]
  range: string
  regime: MarketRegimeRow | null
  breadthData: BreadthWaterfallRow[]
}) {
  const dateStr = (d: Date | string): string =>
    d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10)

  const rsData             = metricHistory.map(r => ({ date: dateStr(r.date), value: r.bottomup_rs_3m_nifty500 != null ? parseFloat(r.bottomup_rs_3m_nifty500) : null }))
  const tdRsData           = metricHistory.map(r => ({ date: dateStr(r.date), value: r.topdown_rs_3m_nifty500  != null ? parseFloat(r.topdown_rs_3m_nifty500)  : null }))
  const breadthChartData   = metricHistory.map(r => ({ date: dateStr(r.date), value: r.participation_50        != null ? parseFloat(r.participation_50)        : null }))
  const rsParticData       = metricHistory.map(r => ({ date: dateStr(r.date), value: r.participation_rs        != null ? parseFloat(r.participation_rs)        : null }))
  const rsParticPctData    = metricHistory.map(r => ({ date: dateStr(r.date), value: r.participation_rs_pct    != null ? parseFloat(r.participation_rs_pct)    : null }))
  const leaderConcentData  = metricHistory.map(r => ({ date: dateStr(r.date), value: r.leadership_concentration != null ? parseFloat(r.leadership_concentration) : null }))
  const ret3mData    = metricHistory.map(r => ({ date: dateStr(r.date), value: r.bottomup_ret_3m         != null ? parseFloat(r.bottomup_ret_3m)         : null }))
  const tdRet3mData  = metricHistory.map(r => ({ date: dateStr(r.date), value: r.topdown_ret_3m           != null ? parseFloat(r.topdown_ret_3m)           : null }))
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
        bottomup_ret_1w: snapshot.bottomup_ret_1w,
        bottomup_ret_1m: snapshot.bottomup_ret_1m,
        bottomup_ret_3m: snapshot.bottomup_ret_3m,
        bottomup_ret_6m: snapshot.bottomup_ret_6m,
        bottomup_rs_3m_nifty500: snapshot.bottomup_rs_3m_nifty500,
        rs_momentum: snapshot.rs_momentum,
        participation_50: snapshot.participation_50,
        participation_rs: snapshot.participation_rs,
        leadership_concentration: snapshot.leadership_concentration,
        sector_state: snapshot.sector_state,
        bottomup_state: snapshot.bottomup_state,
        topdown_state: snapshot.topdown_state,
        divergence_flag: snapshot.divergence_flag,
        bottomup_rs_state: snapshot.bottomup_rs_state,
        bottomup_momentum_state: snapshot.bottomup_momentum_state,
        bottomup_risk_state: snapshot.bottomup_risk_state,
        bottomup_volume_state: snapshot.bottomup_volume_state,
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
                data={breadthChartData}
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

            {/* Top-down RS vs Bottom-up RS */}
            {tdRsData.some(d => d.value != null) && (
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
                <IndicatorChart
                  title="Top-Down RS (NSE Index) vs Bottom-Up RS (Constituents)"
                  description="Compares the index ETF/proxy relative strength (top-down) against the median constituent RS (bottom-up). When both are positive and converging, the signal is highest-conviction. Divergence flags disagreement between index and stock-level momentum."
                  currentValue={pctStr(latest?.topdown_rs_3m_nifty500)}
                  isBullish={latest?.topdown_rs_3m_nifty500 != null ? parseFloat(latest.topdown_rs_3m_nifty500) > 0 : null}
                  data={tdRsData}
                  refLine={0}
                  refLabel="0"
                  variant="area"
                  yFormat="pct"
                />
                <Commentary title={`Top-Down RS · ${pctStr(latest?.topdown_rs_3m_nifty500)} (BU: ${pctStr(latest?.bottomup_rs_3m_nifty500)})`}>
                  {(() => {
                    const td = latest?.topdown_rs_3m_nifty500 != null ? parseFloat(latest.topdown_rs_3m_nifty500) * 100 : null
                    const bu = latest?.bottomup_rs_3m_nifty500 != null ? parseFloat(latest.bottomup_rs_3m_nifty500) * 100 : null
                    if (td == null || bu == null) return <p>No top-down RS data available.</p>
                    const agree = (td > 0 && bu > 0) || (td < 0 && bu < 0)
                    const gap = Math.abs(td - bu).toFixed(1)
                    if (agree && td > 0) return (
                      <>
                        <p>Index ({td.toFixed(1)}pp) and constituents ({bu.toFixed(1)}pp) <span className="text-signal-pos font-semibold">both outperforming</span>.</p>
                        <p>Agreement between top-down and bottom-up RS is the strongest confirmation of genuine sector leadership. {gap}pp spread — {parseFloat(gap) < 5 ? 'tight, high confidence' : 'wide, leadership may be concentrated'}.</p>
                      </>
                    )
                    if (agree && td < 0) return (
                      <>
                        <p>Both index ({td.toFixed(1)}pp) and constituents ({bu.toFixed(1)}pp) <span className="text-signal-neg font-semibold">underperforming</span>.</p>
                        <p>Broad weakness confirmed at both levels. No divergence to exploit — avoid.</p>
                      </>
                    )
                    if (td > 0 && bu < 0) return (
                      <>
                        <p><span className="text-signal-warn font-semibold">Divergence:</span> Index outperforming ({td.toFixed(1)}pp) but constituent stocks lagging ({bu.toFixed(1)}pp).</p>
                        <p>Index strength may be driven by index-heavies masking weak breadth. Check leadership concentration.</p>
                      </>
                    )
                    return (
                      <>
                        <p><span className="text-signal-warn font-semibold">Divergence:</span> Stocks outperforming ({bu.toFixed(1)}pp) but index lagging ({td.toFixed(1)}pp).</p>
                        <p>Stock-level improvement not yet reflected in the index. May indicate early accumulation not captured by index weighting.</p>
                      </>
                    )
                  })()}
                </Commentary>
              </div>
            )}

            {/* Leadership Concentration */}
            {leaderConcentData.some(d => d.value != null) && (
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
                <IndicatorChart
                  title="Leadership Concentration — Top-3 Stock RS Share"
                  description="Share of the sector's total RS score held by the top 3 performing stocks. High concentration (>60%) means sector RS is driven by 2-3 names, making it fragile. Low concentration means breadth-supported leadership."
                  currentValue={latest?.leadership_concentration != null
                    ? `${(parseFloat(latest.leadership_concentration) * 100).toFixed(0)}%`
                    : '—'}
                  isBullish={latest?.leadership_concentration != null ? parseFloat(latest.leadership_concentration) < 0.5 : null}
                  data={leaderConcentData}
                  refLine={0.5}
                  refLabel="50%"
                  variant="area"
                />
                <Commentary title={`Concentration · ${latest?.leadership_concentration != null ? (parseFloat(latest.leadership_concentration) * 100).toFixed(0) + '%' : '—'} top-3 share`}>
                  {(() => {
                    if (latest?.leadership_concentration == null) return <p>No concentration data.</p>
                    const c = parseFloat(latest.leadership_concentration) * 100
                    if (c >= 70) return (
                      <>
                        <p>Top 3 stocks hold <span className="text-signal-neg font-semibold">{c.toFixed(0)}%</span> of sector RS — extreme concentration.</p>
                        <p>Sector performance depends almost entirely on 2-3 names. Leadership is fragile; if these rotate out, the sector signal collapses fast.</p>
                      </>
                    )
                    if (c >= 50) return (
                      <>
                        <p>Top 3 stocks hold <span className="text-signal-warn font-medium">{c.toFixed(0)}%</span> of sector RS — moderate concentration.</p>
                        <p>A few leaders are doing the heavy lifting. Viable, but watch whether concentration is rising or falling — rising concentration is a warning sign.</p>
                      </>
                    )
                    return (
                      <>
                        <p>Top 3 stocks hold <span className="text-signal-pos font-semibold">{c.toFixed(0)}%</span> of RS — broad-based leadership.</p>
                        <p>Sector strength is distributed across many names. Durable, institutionally-driven moves typically show this pattern.</p>
                      </>
                    )
                  })()}
                </Commentary>
              </div>
            )}

            {/* RS Participation % (stocks outperforming Nifty500) */}
            {rsParticPctData.some(d => d.value != null) && (
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
                <IndicatorChart
                  title="RS Participation — % Stocks Outperforming Nifty 500"
                  description="Percentage of sector constituents that are individually outperforming the Nifty 500 index on a 3-month RS basis. Differs from participation_rs (which uses an internal benchmark) by using the market-wide benchmark — more demanding."
                  currentValue={latest?.participation_rs_pct != null
                    ? `${(parseFloat(latest.participation_rs_pct) * 100).toFixed(0)}%`
                    : '—'}
                  isBullish={latest?.participation_rs_pct != null ? parseFloat(latest.participation_rs_pct) > 0.4 : null}
                  data={rsParticPctData}
                  refLine={0.4}
                  refLabel="40%"
                  variant="area"
                  yFormat="pct"
                />
                <Commentary title={`Nifty500 Beaters · ${latest?.participation_rs_pct != null ? (parseFloat(latest.participation_rs_pct) * 100).toFixed(0) + '%' : '—'} of stocks`}>
                  {(() => {
                    if (latest?.participation_rs_pct == null) return <p>No data available.</p>
                    const p = parseFloat(latest.participation_rs_pct) * 100
                    if (p >= 60) return (
                      <>
                        <p><span className="text-signal-pos font-semibold">{p.toFixed(0)}%</span> of sector stocks are beating Nifty 500 individually.</p>
                        <p>Broad outperformance — this is not just a few stocks pulling up the average. High-conviction signal for sector allocation.</p>
                      </>
                    )
                    if (p >= 40) return (
                      <>
                        <p><span className="text-signal-pos font-medium">{p.toFixed(0)}%</span> of stocks beat Nifty 500 — moderate market-wide participation.</p>
                        <p>Enough stocks are outperforming to justify sector exposure, but not peak participation. Monitor for trend.</p>
                      </>
                    )
                    if (p >= 25) return (
                      <>
                        <p>Only <span className="text-signal-warn font-medium">{p.toFixed(0)}%</span> beat Nifty 500 — weak market-wide participation.</p>
                        <p>Sector RS may be driven by a minority. Leadership is narrow — wait for broader participation before adding.</p>
                      </>
                    )
                    return (
                      <>
                        <p>Only <span className="text-signal-neg font-semibold">{p.toFixed(0)}%</span> of stocks beat Nifty 500 — sector is lagging broadly.</p>
                        <p>Few individual stocks can overcome market headwinds. Avoid sector exposure until this crosses 35%+.</p>
                      </>
                    )
                  })()}
                </Commentary>
              </div>
            )}

            {/* Top-down 3M Return vs Bottom-up 3M Return */}
            {tdRet3mData.some(d => d.value != null) && (
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
                <IndicatorChart
                  title="Top-Down 3M Return (Index) vs Bottom-Up 3M Return (Stocks)"
                  description="Compares the NSE sector index's 3-month return (top-down) against the average return of constituent stocks (bottom-up). Divergences reveal index-construction distortions — e.g. when the index outperforms because of one heavy-weight but most stocks are flat."
                  currentValue={pctStr(latest?.topdown_ret_3m)}
                  isBullish={latest?.topdown_ret_3m != null ? parseFloat(latest.topdown_ret_3m) > 0 : null}
                  data={tdRet3mData}
                  refLine={0}
                  refLabel="0"
                  variant="area"
                  yFormat="pct"
                />
                <Commentary title={`Index Return · ${pctStr(latest?.topdown_ret_3m)} (Stocks: ${pctStr(latest?.bottomup_ret_3m)})`}>
                  {(() => {
                    const td = latest?.topdown_ret_3m != null ? parseFloat(latest.topdown_ret_3m) * 100 : null
                    const bu = latest?.bottomup_ret_3m != null ? parseFloat(latest.bottomup_ret_3m) * 100 : null
                    if (td == null) return <p>No top-down return data.</p>
                    const spread = bu != null ? (bu - td).toFixed(1) : null
                    if (spread != null && Math.abs(parseFloat(spread)) > 10) return (
                      <>
                        <p>Large gap between index ({td.toFixed(1)}%) and stocks ({bu!.toFixed(1)}%) — <span className="text-signal-warn font-semibold">{Math.abs(parseFloat(spread)).toFixed(1)}pp spread</span>.</p>
                        <p>Index-level data may be misleading. Prefer the bottom-up view for portfolio decisions in this sector.</p>
                      </>
                    )
                    return (
                      <>
                        <p>Index return ({td.toFixed(1)}%) and stock average {bu != null ? `(${bu.toFixed(1)}%)` : ''} are broadly aligned.</p>
                        <p>No significant index-construction distortion. Both signals are reliable for sector decisions.</p>
                      </>
                    )
                  })()}
                </Commentary>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Breadth History waterfall */}
      <div className="mt-6">
        <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Breadth History
        </h3>
        <BreadthWaterfall data={breadthData} sectorName={snapshot.sector_name} />
      </div>
    </div>
    </div>
  )
}
