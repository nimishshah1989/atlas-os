// src/components/entity/StrengthSection.tsx — what the instrument has DONE, against itself and
// against SPY, out of the nightly technicals.
//
// THE LADDER IS THE POINT. One return tells you nothing; six windows side by side tell you whether
// a move is a week old or a two-year trend, and whether the instrument is beating SPY at every
// horizon or only the flattering one. That comparison is the whole product, so it is a table with
// the horizons as rows, not six numbers scattered through prose.
//
// RELATIVE STRENGTH IS THE RELATIVE FORM (ADR-0002): (1 + r) / (1 + b) − 1, not r − b. Over two
// years the difference is material, and it is the form compute_technicals.py writes and the form
// the return calculator answers in, so no two surfaces of this board can disagree about what
// "beating SPY" means.
//
// A NULL IS AN EM DASH. A fund listed eight months ago has no 12-month return; printing 0 would
// say it went nowhere for a year it did not exist (rule #0).
import { Section } from '@/components/ui/Section'
import { formatIsoDate, formatPct } from '@/lib/format'
import type { TechnicalRead } from '@/lib/queries/series'
import { rsTint } from '@/lib/scores'
import { emaStack } from '@/lib/series'
import { FactList, type Fact } from './FactList'

const WINDOWS = [
  { label: '1 week', ret: 'ret_1w', rs: 'rs_1w_spy' },
  { label: '1 month', ret: 'ret_1m', rs: 'rs_1m_spy' },
  { label: '3 months', ret: 'ret_3m', rs: 'rs_3m_spy' },
  { label: '6 months', ret: 'ret_6m', rs: 'rs_6m_spy' },
  { label: '12 months', ret: 'ret_12m', rs: 'rs_12m_spy' },
  { label: '24 months', ret: 'ret_24m', rs: 'rs_24m_spy' },
] as const satisfies readonly { label: string; ret: keyof TechnicalRead; rs: keyof TechnicalRead }[]

const str = (t: TechnicalRead, k: keyof TechnicalRead): string | null => {
  const v = t[k]
  return typeof v === 'string' ? v : null
}

function Pct({ value, decimals = 1 }: { value: string | null; decimals?: number }) {
  if (value == null) return <span className="text-ink-3">—</span>
  return <span className="num">{formatPct(value, decimals)}</span>
}

export function StrengthSection({ technical, symbol }: { technical: TechnicalRead | null; symbol: string }) {
  if (!technical) {
    return (
      <Section title="Strength" note="technical_daily">
        <p className="panel px-4 py-3 text-body text-ink-2">
          compute_technicals.py has not written a row for {symbol}. Returns, relative strength and
          the risk measures arrive with it; none is shown until it has.
        </p>
      </Section>
    )
  }

  const t = technical
  const stack = emaStack(t.ema_21, t.ema_50, t.ema_200)
  const asOf = formatIsoDate(t.date)

  const trend: Fact[] = [
    {
      label: 'Moving averages',
      value: stack ? (
        <span className={stack.tone === 'pos' ? 'text-pos' : stack.tone === 'neg' ? 'text-neg' : 'text-ink'}>{stack.label}</span>
      ) : (
        <span className="text-ink-2">not enough history for all three</span>
      ),
      source: 'EMA 21 / 50 / 200 on split-adjusted closes',
    },
    {
      label: 'Above its averages',
      value: (
        <span className="num">
          {[t.above_ema_21, t.above_ema_50, t.above_ema_200].filter((b) => b === true).length} of 3
        </span>
      ),
      source: '21, 50 and 200-day',
    },
    { label: '52-week position', value: <Pct value={t.pos_52w} decimals={0} />, source: '0 at the low, 100 at the high' },
    { label: 'RSI 14', value: t.rsi_14 == null ? <span className="text-ink-3">—</span> : <span className="num">{Number(t.rsi_14).toFixed(1)}</span>, source: 'on split-adjusted closes' },
    { label: 'Daily range', value: <Pct value={t.atr_14_pct} decimals={2} />, source: 'ATR-14 as a share of price' },
    { label: 'Volume', value: t.vol_ratio_30d == null ? <span className="text-ink-3">—</span> : <span className="num">{Number(t.vol_ratio_30d).toFixed(2)}×</span>, source: 'against its own 30-day average' },
  ]

  const risk: Fact[] = [
    { label: 'Volatility', value: <Pct value={t.vol_252d_ann} />, source: 'annualised, 252 sessions, on total return' },
    { label: 'Volatility, 63d', value: <Pct value={t.vol_63d_ann} />, source: 'annualised' },
    { label: 'Worst 12m fall', value: <Pct value={t.mdd_12m} />, source: 'peak to trough' },
    { label: 'Worst 36m fall', value: <Pct value={t.mdd_36m} />, source: 'peak to trough' },
    { label: 'Beta to SPY', value: t.beta_spy_252 == null ? <span className="text-ink-3">—</span> : <span className="num">{Number(t.beta_spy_252).toFixed(2)}</span>, source: '252 sessions' },
    { label: 'Sharpe, 12m', value: t.sharpe_12m == null ? <span className="text-ink-3">—</span> : <span className="num">{Number(t.sharpe_12m).toFixed(2)}</span>, source: 'risk-free from FRED DTB3' },
  ]

  return (
    <Section title="Strength" note={`technical_daily at ${asOf}`}>
      <div className="panel overflow-x-auto">
        <table className="tbl">
          <thead>
            <tr>
              <th>Over</th>
              <th className="text-right">Total return</th>
              <th className="text-right">Against SPY</th>
            </tr>
          </thead>
          <tbody>
            {WINDOWS.map((w) => {
              const rs = str(t, w.rs)
              return (
                <tr key={w.label}>
                  <td className="text-ink">{w.label}</td>
                  <td className="num text-right">
                    <Pct value={str(t, w.ret)} />
                  </td>
                  <td className="num text-right" style={{ background: rsTint(rs) }}>
                    <Pct value={rs} />
                  </td>
                </tr>
              )
            })}
            <tr>
              <td className="text-ink">Year to date</td>
              <td className="num text-right">
                <Pct value={t.ret_ytd} />
              </td>
              <td className="text-ink-3">—</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-meta text-ink-3">
        Returns include dividends. “Against SPY” is the relative form — what a dollar in this did
        for every dollar in SPY, not the difference of two percentages.
      </p>

      <div className="detail mt-5">
        <div>
          <p className="mb-1 text-meta text-ink-3">Trend</p>
          <FactList facts={trend} />
        </div>
        <div>
          <p className="mb-1 text-meta text-ink-3">Risk</p>
          <FactList facts={risk} />
        </div>
      </div>
    </Section>
  )
}
