// Leaderboard — the head-to-head the whole portfolio layer exists to answer:
// every live book (agent desks, their deterministic twins, rule strategies, FM
// baskets) vs NIFTY 500 over its own life. Excess is the score; FM baskets join
// automatically as they're created. Server component, stored data only.
import { getLeaderboard } from '@/lib/queries/portfolios'
import { Panel } from '@/components/ui/Panel'

const pct = (v: number | null, dp = 1) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(dp)}%`
const tone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const KIND_LABEL: Record<string, string> = {
  rule: 'Rule',
  system: 'System',
  basket: 'FM',
}

export async function Leaderboard() {
  const rows = await getLeaderboard()
  if (rows.length < 2) return null
  return (
    <Panel
      eyebrow="Live head-to-head"
      title="Leaderboard — everyone vs NIFTY 500"
      info={{ body: 'Each book’s LIVE paper-track since its own inception vs NIFTY 500 over the same window (post-cost). Excess is the score. Agent desks are marked ◆ — the standing question is whether they beat their deterministic twins and the fund manager. Backtests don’t play here; this table is forward record only.' }}
      bodyClassName="overflow-x-auto"
    >
      <table className="w-full min-w-[760px]">
        <thead>
          <tr className="border-b border-edge-rule">
            {['Portfolio', 'Type', 'Since', 'Live', 'NIFTY 500', 'Excess', 'Max DD', 'Pos.'].map((h, i) => (
              <th key={h} className={`px-3 py-2 font-num text-[10px] uppercase tracking-wider text-txt-3 ${i === 0 ? 'text-left' : 'text-right'}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-edge-hair transition-colors hover:bg-surface-raised/50">
              <td className="px-3 py-2">
                <a href={`/portfolios/${r.id}`} className="font-sans text-[12.5px] font-semibold text-txt-1 no-underline hover:text-brand hover:underline">
                  {r.isDesk ? '◆ ' : ''}{r.name}
                </a>
              </td>
              <td className="px-3 py-2 text-right font-sans text-[10.5px] uppercase tracking-wider text-txt-3">
                {r.isDesk ? 'Desk' : KIND_LABEL[r.category]}
              </td>
              <td className="px-3 py-2 text-right font-num text-[11.5px] tabular-nums text-txt-3">{r.inception}</td>
              <td className={`px-3 py-2 text-right font-num text-[12.5px] font-semibold tabular-nums ${tone(r.livePct)}`}>{pct(r.livePct, 2)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{pct(r.n500Pct, 2)}</td>
              <td className={`px-3 py-2 text-right font-num text-[12.5px] font-semibold tabular-nums ${tone(r.excessPp)}`}>
                {r.excessPp == null ? '—' : `${r.excessPp > 0 ? '+' : ''}${r.excessPp.toFixed(2)}pp`}
              </td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{pct(r.maxDdPct)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{r.nPositions ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 pb-1 pt-2 font-sans text-[11px] text-txt-3">
        Forward record only — young books swing hard; judge after months, not days. Create an FM basket and it joins this table automatically.
      </p>
    </Panel>
  )
}
