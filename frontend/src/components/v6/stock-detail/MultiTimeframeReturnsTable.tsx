// Multi-timeframe returns table: 1W / 1M / 3M / 6M / 12M
// Shows absolute return + alpha vs Nifty (when available from metric history latest row).
// Pure server component.

// Accepts any latest-metric dict (the shape of the latest row from
// getStockMetricHistory may grow over time). Only fields needed by the
// table are parsed; missing fields render as "—".
type MetricLatest = Record<string, unknown>

interface MultiTimeframeReturnsTableProps {
  latest: MetricLatest | null
}

interface Row {
  period: string
  retKey: string
  alphaKey?: string
}

const ROWS: Row[] = [
  { period: '1W',  retKey: 'ret_1w' },
  { period: '1M',  retKey: 'ret_1m' },
  { period: '3M',  retKey: 'ret_3m',  alphaKey: 'alpha_3m' },
  { period: '6M',  retKey: 'ret_6m',  alphaKey: 'alpha_6m' },
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

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}

function color(v: number | null): string {
  if (v == null) return 'text-ink-3'
  if (v > 0) return 'text-signal-pos'
  if (v < 0) return 'text-signal-neg'
  return 'text-ink-3'
}

export function MultiTimeframeReturnsTable({ latest }: MultiTimeframeReturnsTableProps) {
  return (
    <div className="border border-paper-rule rounded p-4 bg-paper">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">Returns by Horizon</p>
      <table className="w-full text-[12px] font-mono">
        <thead>
          <tr className="border-b border-paper-rule">
            <th className="text-left py-1.5 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Period</th>
            <th className="text-right py-1.5 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Absolute</th>
            <th className="text-right py-1.5 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Alpha vs Nifty</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(row => {
            const ret = parse(latest?.[row.retKey])
            const alpha = row.alphaKey ? parse(latest?.[row.alphaKey]) : null
            return (
              <tr key={row.period} className="border-b border-paper-rule last:border-0">
                <td className="py-1.5 text-ink">{row.period}</td>
                <td className={`text-right py-1.5 ${color(ret)}`}>{fmtPct(ret)}</td>
                <td className={`text-right py-1.5 ${color(alpha)}`}>{alpha != null ? fmtPct(alpha) : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
