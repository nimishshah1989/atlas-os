// StockFundamentalsTable — Screener.in-style historical financials for the v4 stock
// detail page. Replaces the unhelpful TradingView "Financials" widget. Metrics as ROWS,
// quarters as COLUMNS (oldest→newest, left→right) so the trend reads naturally.
// Pure presentational server component — data already fetched via getStockFundamentals().
import type { StockQuarter } from '@/lib/queries/v6/stock_lens'

// Two-digit calendar month → short name. String-keyed so we never coerce via Number().
const MON: Record<string, string> = {
  '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
  '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}

// 'YYYY-MM-DD' (fiscal quarter end) → "Mar '26". Parsed by field, no Date() / tz drift.
function quarterLabel(periodEnd: string): string {
  const [y, m] = periodEnd.split('-')
  return `${MON[m] ?? m} '${y.slice(2)}`
}

// ₹-crore values: thousands separators, no decimals (e.g. 7,587). null → '—'.
function crore(v: number | null): string {
  if (v == null) return '—'
  return Math.round(v).toLocaleString('en-IN')
}
// margins already a PERCENT (e.g. 33.7) → "33.7%".
function pct1(v: number | null): string {
  return v == null ? '—' : `${v.toFixed(1)}%`
}
// EPS → 2 decimals (e.g. 12.65).
function eps2(v: number | null): string {
  return v == null ? '—' : v.toFixed(2)
}
// Debt/Equity ratio → 2 decimals or '—' (quarterly XBRL rarely carries it).
function ratio2(v: number | null): string {
  return v == null ? '—' : v.toFixed(2)
}

type Row = { label: string; fmt: (q: StockQuarter) => string }
const ROWS: Row[] = [
  { label: 'Revenue (₹cr)', fmt: (q) => crore(q.revenue) },
  { label: 'EBITDA (₹cr)', fmt: (q) => crore(q.ebitda) },
  { label: 'EBITDA margin', fmt: (q) => pct1(q.ebitda_margin) },
  { label: 'PAT (₹cr)', fmt: (q) => crore(q.pat) },
  { label: 'Net margin', fmt: (q) => pct1(q.net_margin) },
  { label: 'EPS (₹)', fmt: (q) => eps2(q.eps) },
  { label: 'D/E', fmt: (q) => ratio2(q.debt_equity) },
]

// YoY chip — colored by sign (green ≥0, red <0). null → muted "n/a".
function YoYChip({ label, value }: { label: string; value: number | null }) {
  if (value == null) {
    return (
      <span className="inline-flex items-center gap-1 rounded-tile border border-edge-hair px-2 py-1 font-num text-[11px] tabular-nums text-txt-3">
        {label} <span>n/a</span>
      </span>
    )
  }
  const up = value >= 0
  const cls = up
    ? 'border-sig-pos/30 bg-sig-pos/10 text-sig-pos'
    : 'border-sig-neg/30 bg-sig-neg/10 text-sig-neg'
  return (
    <span className={`inline-flex items-center gap-1 rounded-tile border px-2 py-1 font-num text-[11px] tabular-nums ${cls}`}>
      {label} <span>{up ? '+' : ''}{value.toFixed(1)}% YoY</span>
    </span>
  )
}

function Heading() {
  return (
    <div className="mb-[18px]">
      <h2 className="font-display text-[26px] font-normal tracking-tight text-txt-1">Quarterly financials</h2>
      <p className="mt-1 max-w-[760px] font-sans text-[13px] leading-[1.45] text-txt-3">
        Last 8 quarters from the company&rsquo;s filings (₹ crore) — revenue, profit, margins and the growth trend.
      </p>
    </div>
  )
}

export function StockFundamentalsTable({ quarters }: { quarters: StockQuarter[] }) {
  if (quarters.length === 0) {
    return (
      <section className="border-b border-edge-hair px-8 py-9" aria-label="Quarterly financials">
        <Heading />
        <p className="font-sans text-[13px] text-txt-3">No quarterly financials available.</p>
      </section>
    )
  }

  // Incoming newest-first; reverse for display so the trend reads oldest→newest (left→right).
  const cols = [...quarters].reverse()
  const newest = quarters[0] // newest quarter drives the YoY chips

  return (
    <section className="border-b border-edge-hair px-8 py-9" aria-label="Quarterly financials">
      <Heading />
      <div className="overflow-hidden rounded-tile border border-edge-hair bg-surface-panel">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-surface-panel px-4 py-[11px] text-left font-num text-[9px] font-semibold uppercase tracking-[0.18em] text-txt-3 border-b border-edge-rule">
                  Metric
                </th>
                {cols.map((q) => (
                  <th
                    key={q.period_end}
                    className="bg-surface-panel px-4 py-[11px] text-right font-num text-[11px] font-semibold tabular-nums text-txt-2 border-b border-edge-rule"
                  >
                    {quarterLabel(q.period_end)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.label}>
                  <td className="sticky left-0 z-10 bg-surface-panel px-4 py-[10px] text-left font-sans text-[12px] font-medium text-txt-2 border-b border-edge-hair">
                    {row.label}
                  </td>
                  {cols.map((q) => {
                    const text = row.fmt(q)
                    return (
                      <td
                        key={q.period_end}
                        className="px-4 py-[10px] text-right font-num text-[12px] tabular-nums text-txt-1 border-b border-edge-hair"
                      >
                        {text === '—' ? <span className="text-txt-3">—</span> : text}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-edge-hair bg-surface-panel px-4 py-3">
          <span className="font-num text-[10px] uppercase tracking-wider text-txt-3">
            YoY growth · {quarterLabel(newest.period_end)}
          </span>
          <YoYChip label="Revenue" value={newest.rev_yoy} />
          <YoYChip label="PAT" value={newest.pat_yoy} />
        </div>
      </div>
    </section>
  )
}
