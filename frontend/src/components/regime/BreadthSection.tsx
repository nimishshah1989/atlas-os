import { BarChart2 } from 'lucide-react'
import { SectionHeader } from './SectionHeader'
import { CategorySummary } from './CategorySummary'
import { IndicatorChart } from './IndicatorChart'
import { HighsLowsChart } from './HighsLowsChart'
import type { MarketRegimeRow, RegimeHistoryRow } from '@/lib/queries/regime'

type Props = {
  current: MarketRegimeRow
  history: RegimeHistoryRow[]
}

const dateStr = (row: RegimeHistoryRow): string =>
  row.date instanceof Date
    ? row.date.toISOString().slice(0, 10)
    : String(row.date).slice(0, 10)

export function BreadthSection({ current, history }: Props) {
  const f = (s: string | null | undefined): number => (s == null ? 0 : parseFloat(s))

  const pctEma50  = f(current.pct_above_ema_50)
  const pctEma200 = f(current.pct_above_ema_200)
  const adRatio   = f(current.ad_ratio)
  const adLineBullish = f(current.ad_line_slope_21) > 0
  const highs     = current.new_52w_highs ?? 0
  const lows      = current.new_52w_lows ?? 0
  const hlRatio   = f(current.new_high_low_ratio)
  const highsLowsBullish = highs > lows

  const bullishSignals = [
    pctEma50 > 0.5,
    pctEma200 > 0.5,
    adRatio > 1,
    adLineBullish,
    highsLowsBullish,
    hlRatio > 1,
  ]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  // Summary verdict
  const pct50str  = `${(pctEma50 * 100).toFixed(0)}%`
  const pct200str = `${(pctEma200 * 100).toFixed(0)}%`
  const adStr     = adRatio.toFixed(2)
  const breadthLabel =
    bullishCount >= 5 ? 'BREADTH IS EXPANDING' :
    bullishCount >= 3 ? 'BREADTH IS MIXED' :
    'BREADTH IS CONTRACTING'
  const breadthSummary =
    `${pct50str} of Nifty 500 stocks are above their 50-day EMA and ${pct200str} above the 200-day. ` +
    `A/D ratio at ${adStr} — ${adRatio > 1 ? 'more stocks advancing than declining' : 'more stocks declining than advancing'}. ` +
    `${highs} stocks at new 52-week highs vs ${lows} at new lows — ${highsLowsBullish ? 'internal health is intact' : 'internal conditions are deteriorating'}.`

  const POS = '#22c55e'
  const NEG = '#ef4444'

  const ema50Data  = history.map((row) => ({ date: dateStr(row), value: row.pct_above_ema_50  != null ? parseFloat(row.pct_above_ema_50)  : null }))
  const ema200Data = history.map((row) => ({ date: dateStr(row), value: row.pct_above_ema_200 != null ? parseFloat(row.pct_above_ema_200) : null }))
  const adRatioData    = history.map((row) => ({ date: dateStr(row), value: row.ad_ratio           != null ? parseFloat(row.ad_ratio)           : null }))
  const adLineData     = history.map((row) => ({ date: dateStr(row), value: row.ad_line            != null ? parseFloat(row.ad_line)            : null }))
  const highLowRatioData = history.map((row) => ({ date: dateStr(row), value: row.new_high_low_ratio != null ? parseFloat(row.new_high_low_ratio) : null }))
  const highsLowsData = history.map((row) => ({
    date: dateStr(row),
    highs: row.new_52w_highs ?? 0,
    lows:  row.new_52w_lows  ?? 0,
  }))

  return (
    <section>
      <SectionHeader
        icon={<BarChart2 className="w-4 h-4" strokeWidth={2} />}
        title="Breadth"
        description="Breadth measures how many stocks are participating in the market's movement. A rally driven by a handful of large-cap names while most stocks decline is fragile and unsustainable. When breadth is strong — the majority of stocks above their moving averages, advances outnumbering declines — the trend has genuine depth. Breadth typically peaks before price does, making it one of the most reliable early-warning indicators of regime change."
        bullishCount={bullishCount}
        totalCount={totalCount}
      />

      <CategorySummary
        bullishCount={bullishCount}
        totalCount={totalCount}
        headline={breadthLabel}
        summary={breadthSummary}
      />

      <div className="px-6 pb-6 pt-4 space-y-4">
        {/* Row 1: EMA participation comparison */}
        <div className="grid grid-cols-2 gap-4">
          <IndicatorChart
            title="% Above 50-day EMA"
            description="The benchmark breadth indicator. Above 50% means the majority of the Nifty 500 universe is in a medium-term uptrend. When this falls below 40%, market health is narrowing — reduce exposure."
            currentValue={`${(pctEma50 * 100).toFixed(1)}%`}
            isBullish={pctEma50 > 0.5}
            data={ema50Data}
            refLine={0.5}
            refLabel="50%"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="% Above 200-day EMA"
            description="Long-term participation quality. When most stocks are above their 200-day average, the market cycle is in a healthy expansion. Below 40% defines a structural bear environment regardless of where the index trades."
            currentValue={`${(pctEma200 * 100).toFixed(1)}%`}
            isBullish={pctEma200 > 0.5}
            data={ema200Data}
            refLine={0.5}
            refLabel="50%"
            variant="area"
            yFormat="pct"
          />
        </div>

        {/* Row 2: A/D indicators */}
        <div className="grid grid-cols-2 gap-4">
          <IndicatorChart
            title="Advance/Decline Ratio"
            description="Daily ratio of advancing to declining stocks across the 750-stock universe. Above 1 means more stocks gained than declined. Sustained readings below 1 while the index holds its level are a classic divergence warning — the index mask is hiding broad weakness."
            currentValue={adRatio.toFixed(2)}
            isBullish={adRatio > 1}
            data={adRatioData}
            refLine={1}
            refLabel="1.0"
            variant="bar"
            yFormat="ratio"
          />
          <IndicatorChart
            title="A/D Line (Cumulative)"
            description="Running cumulative total of daily net advances — think of it as the market's internal health EKG. It should trend upward with the index. When the index makes new highs but the A/D line diverges downward, the rally is being driven by fewer and fewer stocks."
            currentValue={f(current.ad_line).toFixed(0)}
            isBullish={adLineBullish}
            data={adLineData}
            variant="line"
            yFormat="large"
          />
        </div>

        {/* Row 3: New highs/lows */}
        <div className="grid grid-cols-2 gap-4">
          <div className="border border-paper-rule rounded-sm p-5 flex flex-col">
            <div className="flex items-start justify-between mb-2">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary">
                New 52-Week Highs vs Lows
              </span>
              <span className={`font-sans text-[10px] font-medium ${highsLowsBullish ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {highsLowsBullish ? 'BULLISH' : 'BEARISH'}
              </span>
            </div>
            <p className="font-sans text-xs text-ink-tertiary leading-relaxed mb-3">
              Counts how many stocks hit a new annual high vs new annual low each day. When highs far outnumber lows, internal market conditions are healthy even if the index is choppy. Persistent lows &gt; highs historically defines bear markets.
            </p>
            <div className="flex items-baseline gap-4 mb-4">
              <span className="font-mono text-lg font-semibold" style={{ color: POS }}>
                {highs} new highs
              </span>
              <span className="font-mono text-lg font-semibold" style={{ color: lows > 0 ? NEG : '#94a3b8' }}>
                {lows} new lows
              </span>
            </div>
            <div className="mt-auto">
              <HighsLowsChart data={highsLowsData} />
            </div>
          </div>

          <IndicatorChart
            title="High/Low Ratio"
            description="Normalizes new annual highs relative to new annual lows over a rolling window. Above 1 means more stocks at highs than lows. A sustained reading below 1 historically aligns with bear market internal conditions."
            currentValue={hlRatio > 0 ? hlRatio.toFixed(2) : '–'}
            isBullish={hlRatio > 1}
            data={highLowRatioData}
            refLine={1}
            refLabel="1.0"
            variant="line"
            yFormat="ratio"
          />
        </div>
      </div>
    </section>
  )
}
