// Leaderboard — straight numbers, side by side, with self-explaining eye icons:
// per-window (1Y / 3Y / 5Y) CAGR + Max DD + Calmar for every book on its
// meaningful record (backtest for strategies, live-only for agent desks ◆),
// NIFTY 500 as a plain row. Every row carries an eye describing what the book
// actually does; every column group carries an eye defining the metrics.
import { getLeaderboard } from '@/lib/queries/portfolios'
import type { WindowMetrics } from '@/lib/portfolioMetrics'
import { Panel } from '@/components/ui/Panel'
import { InfoTip } from '@/components/ui/InfoTip'

const pct = (v: number | null, dp = 1) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(dp)}%`
const num = (v: number | null, dp = 2) => (v == null ? '—' : v.toFixed(dp))
const tone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

function WindowCells({ w }: { w: WindowMetrics }) {
  return (
    <>
      <td className={`px-2 py-2 text-right font-num text-[12px] font-semibold tabular-nums ${tone(w.cagr)}`}>{pct(w.cagr)}</td>
      <td className="px-2 py-2 text-right font-num text-[11.5px] tabular-nums text-sig-neg">{pct(w.maxDd)}</td>
      <td className="border-r border-edge-hair px-2 py-2 text-right font-num text-[11.5px] tabular-nums text-txt-1">{num(w.calmar)}</td>
    </>
  )
}

function WindowHead() {
  return (
    <>
      <th className="px-2 py-2 text-right font-num text-[10px] uppercase tracking-wider text-txt-3">CAGR</th>
      <th className="px-2 py-2 text-right font-num text-[10px] uppercase tracking-wider text-txt-3">Max DD</th>
      <th className="border-r border-edge-hair px-2 py-2 text-right font-num text-[10px] uppercase tracking-wider text-txt-3">Calmar</th>
    </>
  )
}

const METRIC_DEF = (
  <>
    <strong>CAGR</strong> — annualized compound return over exactly this window (what ₹1 grew to, per year).{' '}
    <strong>Max DD</strong> — worst peak-to-trough fall <em>within the same window</em>.{' '}
    <strong>Calmar</strong> — CAGR ÷ |Max DD|: return earned per unit of worst pain; above 1 means the climb outweighed the deepest fall.
    A window shows &ldquo;—&rdquo; unless the book&rsquo;s record covers that full span — no 3Y number invented from 2 years of data.
  </>
)

export async function Leaderboard() {
  const rows = await getLeaderboard()
  if (rows.length < 2) return null
  return (
    <Panel
      eyebrow="The numbers, side by side"
      title="Risk & return — every book"
      info={{ body: 'Each book’s metrics are computed on its meaningful record: the long backtest for rule-based and rank strategies, the live paper-track for agent desks (◆ — forward-only by design; their windows fill in as the live record grows). NIFTY 500 is just another row. Hover any eye for definitions; click a book for its full page.' }}
      bodyClassName="overflow-x-auto"
    >
      <table className="w-full min-w-[980px]">
        <thead>
          <tr className="border-b border-edge-hair">
            <th colSpan={2} />
            {(['1 year', '3 years', '5 years'] as const).map((label) => (
              <th key={label} colSpan={3} className="border-r border-edge-hair px-2 pb-1 pt-2 text-center">
                <span className="inline-flex items-center gap-1.5 font-num text-[10px] uppercase tracking-[0.14em] text-txt-2">
                  {label} <InfoTip title={`Metrics · ${label}`}>{METRIC_DEF}</InfoTip>
                </span>
              </th>
            ))}
            <th colSpan={2} />
          </tr>
          <tr className="border-b border-edge-rule">
            <th className="px-3 py-2 text-left font-num text-[10px] uppercase tracking-wider text-txt-3">Book</th>
            <th className="px-2 py-2 text-right font-num text-[10px] uppercase tracking-wider text-txt-3">Record</th>
            <WindowHead />
            <WindowHead />
            <WindowHead />
            <th className="px-2 py-2 text-right font-num text-[10px] uppercase tracking-wider text-txt-3">
              <span className="inline-flex items-center gap-1">
                Live
                <InfoTip title="Live">
                  The actual paper-track since this book&rsquo;s inception — real EOD fills, costs in NAV. Not annualized; young books swing hard.
                </InfoTip>
              </span>
            </th>
            <th className="px-2 py-2 text-right font-num text-[10px] uppercase tracking-wider text-txt-3">Pos.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id ?? 'n500'}
              className={`border-b border-edge-hair transition-colors hover:bg-surface-raised/50 ${r.category === 'benchmark' ? 'bg-surface-raised/40' : ''}`}
            >
              <td className="px-3 py-2">
                <span className="inline-flex items-center gap-1.5">
                  {r.id ? (
                    <a href={`/portfolios/${r.id}`} className="font-sans text-[12.5px] font-semibold text-txt-1 no-underline hover:text-brand hover:underline">
                      {r.isDesk ? '◆ ' : ''}{r.name}
                    </a>
                  ) : (
                    <span className="font-sans text-[12.5px] font-semibold text-txt-2">{r.name}</span>
                  )}
                  <InfoTip title={r.name}>{r.blurb}</InfoTip>
                </span>
              </td>
              <td className="px-2 py-2 text-right font-sans text-[10.5px] text-txt-3">{r.record}</td>
              <WindowCells w={r.windows.w1} />
              <WindowCells w={r.windows.w3} />
              <WindowCells w={r.windows.w5} />
              <td className={`px-2 py-2 text-right font-num text-[12px] tabular-nums ${tone(r.livePct != null ? r.livePct / 100 : null)}`}>
                {r.livePct == null ? '—' : `${r.livePct > 0 ? '+' : ''}${r.livePct.toFixed(2)}%`}
              </td>
              <td className="px-2 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{r.nPositions ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 pb-1 pt-2 font-sans text-[11px] text-txt-3">
        Agent desks (◆) are never backtested — a language model already “knows” history, so a replayed past would flatter it dishonestly. Their windows fill in from the live record alone. Create an FM basket and it joins this table automatically.
      </p>
    </Panel>
  )
}
