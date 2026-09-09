// src/components/entity/BarsProvenance.tsx — what ohlcv_daily holds for the instrument, per
// (source, adjustment source): first and last bar, the session count, and whether the bars carry
// adjusted and total-return closes. Unlabelled adjustments are said in words, coloured as a warning.
import { describeBars, type BarsRow } from '@/lib/facts'
import { formatIsoDate } from '@/lib/format'
import { FactList } from './FactList'

export function BarsProvenance({ bars, symbol }: { bars: BarsRow[]; symbol: string }) {
  if (bars.length === 0) {
    return (
      <p className="text-body text-ink-2" data-testid="no-bars" title="Bars arrive with the price spine.">
        No row in ohlcv_daily for {symbol} yet.
      </p>
    )
  }
  return (
    <div className="space-y-6">
      {bars.map((b) => {
        const t = describeBars(b)
        return (
          <FactList
            key={`${b.source}-${b.adjustment_source}`}
            facts={[
              { label: 'Source', value: t.source },
              { label: 'First bar', value: formatIsoDate(b.first_date) },
              { label: 'Last bar', value: formatIsoDate(b.last_date) },
              { label: 'Sessions', value: <span className="num">{t.sessions}</span> },
              { label: 'Adjustment', value: t.adjustment },
              { label: 'Adjusted closes', value: <span className={b.adjusted === 0 ? 'text-warn' : undefined}>{t.adjusted}</span> },
              { label: 'Total-return closes', value: <span className={b.total_return === 0 ? 'text-warn' : undefined}>{t.totalReturn}</span> },
            ]}
          />
        )
      })}
    </div>
  )
}
