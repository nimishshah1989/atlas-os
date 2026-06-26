// TierReturnsTable — SC/MC/LC tier returns + spreads across windows (Markets Today).
// Native data from foundation_staging.index_prices via getTierReturns(). Server component.
import type { TierReturns } from '@/lib/queries/v6/market_pulse'

const pct = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)
const col = (v: number | null) =>
  v == null ? 'text-ink-tertiary' : v > 0 ? 'text-signal-pos' : v < 0 ? 'text-signal-neg' : 'text-ink-secondary'

export function TierReturnsTable({ data }: { data: TierReturns }) {
  const z = data.smallcap_rs_z
  return (
    <section className="px-6 py-5 border-b border-paper-rule">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Tier leadership · returns
        </h2>
        {z != null && (
          <span className="font-sans text-[10px] text-ink-tertiary">
            Smallcap RS z-score:{' '}
            <span className={`font-mono tabular-nums ${z > 0 ? 'text-signal-pos' : z < -1 ? 'text-signal-neg' : 'text-signal-warn'}`}>
              {z >= 0 ? '+' : ''}{z.toFixed(2)}
            </span>
          </span>
        )}
      </div>
      <table className="w-full text-right">
        <thead>
          <tr className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider border-b border-paper-rule">
            <th className="text-left py-1.5 font-medium">Window</th>
            <th className="py-1.5 font-medium">SC 250</th>
            <th className="py-1.5 font-medium">MC 150</th>
            <th className="py-1.5 font-medium">Nifty 100</th>
            <th className="py-1.5 font-medium">SC − LC</th>
            <th className="py-1.5 font-medium">MC − LC</th>
          </tr>
        </thead>
        <tbody>
          {data.windows.map(w => (
            <tr key={w.label} className="border-b border-paper-rule/40">
              <td className="text-left py-1.5 font-sans text-xs text-ink-secondary">{w.label}</td>
              <td className={`py-1.5 font-mono text-xs tabular-nums ${col(w.sc)}`}>{pct(w.sc)}</td>
              <td className={`py-1.5 font-mono text-xs tabular-nums ${col(w.mc)}`}>{pct(w.mc)}</td>
              <td className={`py-1.5 font-mono text-xs tabular-nums ${col(w.lc)}`}>{pct(w.lc)}</td>
              <td className={`py-1.5 font-mono text-xs tabular-nums ${col(w.sc_lc)}`}>{pct(w.sc_lc)}</td>
              <td className={`py-1.5 font-mono text-xs tabular-nums ${col(w.mc_lc)}`}>{pct(w.mc_lc)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="font-sans text-[10px] text-ink-tertiary/60 mt-2">
        SC = Nifty Smallcap 250 · MC = Nifty Midcap 150 · LC = Nifty 100. Spreads in pp. Source: index_prices.
      </div>
    </section>
  )
}
