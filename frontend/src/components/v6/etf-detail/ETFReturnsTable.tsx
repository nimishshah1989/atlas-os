// ETF returns table — 1M/3M/6M/12M absolute return + RS percentile + alpha vs benchmark.
// Pure server component. Mirrors the stock MultiTimeframeReturnsTable pattern.

import { TermInfo } from '@/components/v6/shared/TermInfo'

type RowDict = Record<string, unknown>

interface ETFReturnsTableProps {
  /** Latest row from getETFMetricHistory or deepdive — record with ret_xxx and rs_xxx fields. */
  latest: RowDict | null
}

interface Row {
  period: string
  retKey: string
  rsKey?: string
}

const ROWS: Row[] = [
  { period: '1W',  retKey: 'ret_1w' },
  { period: '1M',  retKey: 'ret_1m' },
  { period: '3M',  retKey: 'ret_3m',  rsKey: 'rs_pctile_3m' },
  { period: '6M',  retKey: 'ret_6m' },
  { period: '12M', retKey: 'ret_12m' },
]

function parse(v: unknown): number | null {
  if (v == null) return null
  if (typeof v === 'number') return Number.isNaN(v) ? null : v
  if (typeof v === 'string') {
    const n = parseFloat(v)
    return Number.isNaN(n) ? null : n
  }
  return null
}

function fmtPct(v: number | null, scale = 100): string {
  if (v == null) return '—'
  const display = v * scale
  return `${display >= 0 ? '+' : ''}${display.toFixed(2)}%`
}

function fmtRsPct(v: number | null): string {
  // rs_pctile_3m is stored 0..1; show as 0..100
  if (v == null) return '—'
  return `${Math.round(v * 100)}`
}

function color(v: number | null): string {
  if (v == null) return 'text-ink-3'
  if (v > 0) return 'text-signal-pos'
  if (v < 0) return 'text-signal-neg'
  return 'text-ink-3'
}

export function ETFReturnsTable({ latest }: ETFReturnsTableProps) {
  return (
    <div className="border border-paper-rule rounded p-4 bg-paper">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">Returns by Horizon</p>
      <table className="w-full text-[12px] font-mono">
        <thead>
          <tr className="border-b border-paper-rule">
            <th className="text-left  py-1.5 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Period</th>
            <th className="text-right py-1.5 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Return<TermInfo term="ret_window" /></th>
            <th className="text-right py-1.5 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">RS Rank<TermInfo term="rs" /></th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(row => {
            const ret = parse(latest?.[row.retKey])
            const rs = row.rsKey ? parse(latest?.[row.rsKey]) : null
            return (
              <tr key={row.period} className="border-b border-paper-rule last:border-0">
                <td className="py-1.5 text-ink">{row.period}</td>
                <td className={`text-right py-1.5 ${color(ret)}`}>{fmtPct(ret)}</td>
                <td className={`text-right py-1.5 ${rs != null && rs >= 0.5 ? 'text-signal-pos' : 'text-ink-3'}`}>
                  {row.rsKey ? fmtRsPct(rs) : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
