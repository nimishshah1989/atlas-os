import { Users } from 'lucide-react'
import { SectionHeader } from './SectionHeader'
import { CategorySummary } from './CategorySummary'
import { IndicatorChart } from './IndicatorChart'
import type { MarketRegimeRow, RegimeHistoryRow } from '@/lib/queries/regime'

type Props = {
  current: MarketRegimeRow
  history: RegimeHistoryRow[]
}

const dateStr = (row: RegimeHistoryRow): string =>
  row.date instanceof Date
    ? row.date.toISOString().slice(0, 10)
    : String(row.date).slice(0, 10)


export function ParticipationSection({ current, history }: Props) {
  const f = (s: string | null | undefined): number => (s == null ? 0 : parseFloat(s))

  const pctStrong = f(current.pct_in_strong_states)
  const pctWeinstein = f(current.pct_weinstein_pass)
  const pctEma50 = f(current.pct_above_ema_50)

  const bullishSignals = [
    pctStrong > 0.4,
    pctWeinstein > 0.4,
    pctEma50 > 0.45,
  ]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  const partLabel =
    bullishCount === 3 ? 'PARTICIPATION IS STRONG' :
    bullishCount === 2 ? 'PARTICIPATION IS MIXED' :
    'PARTICIPATION IS WEAK'
  const partSummary =
    `${(pctStrong * 100).toFixed(0)}% of Nifty 500 stocks are in strong momentum states. ` +
    `${(pctWeinstein * 100).toFixed(0)}% pass Weinstein Stage 2 (above rising 30-week MA). ` +
    `${(pctEma50 * 100).toFixed(0)}% are above their 50-day EMA. ` +
    `${bullishCount >= 2 ? 'Leadership is sufficiently broad to support the market.' : 'Participation is too thin — rally quality is suspect.'}`

  const strongData = history.map((row) => ({
    date: dateStr(row),
    value: row.pct_in_strong_states != null ? parseFloat(row.pct_in_strong_states) : null,
  }))
  const weinsteinData = history.map((row) => ({
    date: dateStr(row),
    value: row.pct_weinstein_pass != null ? parseFloat(row.pct_weinstein_pass) : null,
  }))
  const ema50Data = history.map((row) => ({
    date: dateStr(row),
    value: row.pct_above_ema_50 != null ? parseFloat(row.pct_above_ema_50) : null,
  }))

  return (
    <section className="border-b border-paper-rule">
      <SectionHeader
        icon={<Users className="w-4 h-4" strokeWidth={2} />}
        title="Participation"
        description="Participation quality tells us whether the market's strongest stocks are leading or whether it's random noise. High participation in strong technical states means the rally has depth — leadership is healthy. The Weinstein method classifies stocks by their stage (uptrend, topping, downtrend, base) — a high pass rate means most stocks are in Stage 2 uptrends."
        bullishCount={bullishCount}
        totalCount={totalCount}
      />

      <CategorySummary
        bullishCount={bullishCount}
        totalCount={totalCount}
        headline={partLabel}
        summary={partSummary}
      />

      <div className="px-6 pb-6">
        <div className="grid grid-cols-3 gap-4">
          <IndicatorChart
            title="% in Strong States"
            description="Fraction of the Nifty 500 classified as Leadership or Strong by our momentum model. Above 40% means quality participation is healthy. Below 20% means only a handful of stocks are driving any index gains — thin and unsustainable leadership."
            currentValue={`${(pctStrong * 100).toFixed(1)}%`}
            isBullish={pctStrong > 0.4}
            data={strongData}
            refLine={0.4}
            refLabel="40%"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="% Weinstein Pass"
            description="Applies Stan Weinstein's Stage Analysis: a stock passes when it's above its rising 30-week moving average (Stage 2). Above 40% means most of the universe is in a structural uptrend. Below 30% means the market is broadly in Stage 3 (topping) or Stage 4 (decline)."
            currentValue={`${(pctWeinstein * 100).toFixed(1)}%`}
            isBullish={pctWeinstein > 0.4}
            data={weinsteinData}
            refLine={0.4}
            refLabel="40%"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="Broad Participation (50D)"
            description="Percentage of the Nifty 500 above their 50-day EMA, interpreted as a participation quality measure. Shows whether the majority of stocks are in intermediate uptrends. Below 45% signals that participation is too narrow to sustain a healthy advance."
            currentValue={`${(pctEma50 * 100).toFixed(1)}%`}
            isBullish={pctEma50 > 0.45}
            data={ema50Data}
            refLine={0.45}
            refLabel="45%"
            variant="area"
            yFormat="pct"
          />
        </div>
      </div>
    </section>
  )
}
