// Leaderboard — straight numbers, side by side: CAGR / Vol / Sharpe / MaxDD /
// Calmar per book on its meaningful record (backtest for strategies, live for
// forward-only desks), NIFTY 500 as a plain row. No derived "excess" editorial —
// the reader compares. Server component, stored data only.
import { getLeaderboard } from '@/lib/queries/portfolios'
import { Panel } from '@/components/ui/Panel'

const pct = (v: number | null, dp = 1) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(dp)}%`
const num = (v: number | null, dp = 2) => (v == null ? '—' : v.toFixed(dp))
const tone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

export async function Leaderboard() {
  const rows = await getLeaderboard()
  if (rows.length < 2) return null
  return (
    <Panel
      eyebrow="The numbers, side by side"
      title="Risk & return — every book"
      info={{ body: 'CAGR annualized over each book’s record — the long backtest for strategy portfolios, the live paper-track for agent desks (◆, forward-only by design; their cells fill in as the live record reaches ~3 months). Vol = annualized daily volatility; Sharpe vs 6.5% risk-free; Calmar = CAGR ÷ |max drawdown|. NIFTY 500 is just another row.' }}
      bodyClassName="overflow-x-auto"
    >
      <table className="w-full min-w-[820px]">
        <thead>
          <tr className="border-b border-edge-rule">
            {['Book', 'Record', 'CAGR', 'Vol', 'Sharpe', 'Max DD', 'Calmar', 'Live', 'Pos.'].map((h, i) => (
              <th key={h} className={`px-3 py-2 font-num text-[10px] uppercase tracking-wider text-txt-3 ${i === 0 ? 'text-left' : 'text-right'}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id ?? 'n500'}
              className={`border-b border-edge-hair transition-colors hover:bg-surface-raised/50 ${r.category === 'benchmark' ? 'bg-surface-raised/40' : ''}`}
            >
              <td className="px-3 py-2">
                {r.id ? (
                  <a href={`/portfolios/${r.id}`} className="font-sans text-[12.5px] font-semibold text-txt-1 no-underline hover:text-brand hover:underline">
                    {r.isDesk ? '◆ ' : ''}{r.name}
                  </a>
                ) : (
                  <span className="font-sans text-[12.5px] font-semibold text-txt-2">{r.name}</span>
                )}
              </td>
              <td className="px-3 py-2 text-right font-sans text-[10.5px] text-txt-3">{r.record}</td>
              <td className={`px-3 py-2 text-right font-num text-[12.5px] font-semibold tabular-nums ${tone(r.metrics.cagr)}`}>{pct(r.metrics.cagr)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{pct(r.metrics.volAnn)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{num(r.metrics.sharpe)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-sig-neg">{pct(r.metrics.maxDd)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-1">{num(r.metrics.calmar)}</td>
              <td className={`px-3 py-2 text-right font-num text-[12px] tabular-nums ${tone(r.livePct != null ? r.livePct / 100 : null)}`}>
                {r.livePct == null ? '—' : `${r.livePct > 0 ? '+' : ''}${r.livePct.toFixed(2)}%`}
              </td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{r.nPositions ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 pb-1 pt-2 font-sans text-[11px] text-txt-3">
        Desk (◆) metrics are live-record only and fill in as their track reaches ~3 months — no backtests for agent books, by design. Create an FM basket and it joins automatically.
      </p>
    </Panel>
  )
}
