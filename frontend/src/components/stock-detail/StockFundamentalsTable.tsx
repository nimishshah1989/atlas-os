// StockFundamentalsTable — Screener.in-style historical financials for the v4 stock
// detail page. Replaces the unhelpful TradingView "Financials" widget. Metrics as ROWS,
// quarters as COLUMNS (oldest→newest, left→right) so the trend reads naturally.
// Pure presentational server component — data already fetched via getStockFundamentals().
import type { StockQuarter } from '@/lib/queries/stock_lens'
import { TermInfo } from '@/components/shared/TermInfo'

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

// Sequential (quarter-on-quarter) % change vs the prior column. Uses |prev| so a swing
// through a loss still reads with the right sign. null when either side is missing/zero.
function qoq(cur: number | null, prev: number | null): number | null {
  if (cur == null || prev == null || prev === 0) return null
  return ((cur - prev) / Math.abs(prev)) * 100
}
function qoqStr(cur: number | null, prev: number | null): string {
  const v = qoq(cur, prev)
  return v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

// `delta` rows are the %-change lines (FM 2026-06-26): rendered indented + sign-coloured.
type Row = {
  label: string
  fmt: (q: StockQuarter, prev: StockQuarter | null) => string
  delta?: (q: StockQuarter, prev: StockQuarter | null) => number | null
  indent?: boolean
  term?: string
}
const ROWS: Row[] = [
  { label: 'Revenue (₹cr)', fmt: (q) => crore(q.revenue), term: 'revenue' },
  { label: '↳ change QoQ', indent: true, fmt: (q, p) => qoqStr(q.revenue, p?.revenue ?? null), delta: (q, p) => qoq(q.revenue, p?.revenue ?? null), term: 'qoq_change' },
  { label: 'EBITDA (₹cr)', fmt: (q) => crore(q.ebitda), term: 'ebitda' },
  { label: 'EBITDA margin', fmt: (q) => pct1(q.ebitda_margin), term: 'ebitda_margin' },
  { label: 'PAT (₹cr)', fmt: (q) => crore(q.pat), term: 'pat' },
  { label: '↳ change QoQ', indent: true, fmt: (q, p) => qoqStr(q.pat, p?.pat ?? null), delta: (q, p) => qoq(q.pat, p?.pat ?? null), term: 'qoq_change' },
  { label: 'Net margin', fmt: (q) => pct1(q.net_margin), term: 'net_margin' },
  { label: 'EPS (₹)', fmt: (q) => eps2(q.eps), term: 'eps' },
  { label: 'D/E', fmt: (q) => ratio2(q.debt_equity), term: 'debt_equity' },
]

// YoY chip — colored by sign (green ≥0, red <0). null → muted "n/a".
function YoYChip({ label, value, term }: { label: string; value: number | null; term?: string }) {
  if (value == null) {
    return (
      <span className="inline-flex items-center gap-1 rounded-tile border border-edge-hair px-2 py-1 font-num text-[11px] tabular-nums text-txt-3">
        {label}{term && <TermInfo term={term} />} <span>n/a</span>
      </span>
    )
  }
  const up = value >= 0
  const cls = up
    ? 'border-sig-pos/30 bg-sig-pos/10 text-sig-pos'
    : 'border-sig-neg/30 bg-sig-neg/10 text-sig-neg'
  return (
    <span className={`inline-flex items-center gap-1 rounded-tile border px-2 py-1 font-num text-[11px] tabular-nums ${cls}`}>
      {label}{term && <TermInfo term={term} />} <span>{up ? '+' : ''}{value.toFixed(1)}% YoY</span>
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
          <table className="tbl-centered w-full border-collapse">
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
              {ROWS.map((row, ri) => (
                <tr key={`${row.label}-${ri}`}>
                  <td className={`sticky left-0 z-10 bg-surface-panel px-4 ${row.indent ? 'py-[7px] pl-7 font-sans text-[11px] text-txt-3' : 'py-[10px] font-sans text-[12px] font-medium text-txt-2'} text-left border-b border-edge-hair`}>
                    {row.label}{row.term && <TermInfo term={row.term} />}
                  </td>
                  {cols.map((q, i) => {
                    const prev = i > 0 ? cols[i - 1] : null
                    const text = row.fmt(q, prev)
                    const dv = row.delta ? row.delta(q, prev) : null
                    const tone = row.delta
                      ? (dv == null ? 'text-txt-3' : dv >= 0 ? 'text-sig-pos' : 'text-sig-neg')
                      : 'text-txt-1'
                    return (
                      <td
                        key={q.period_end}
                        className={`px-4 ${row.indent ? 'py-[7px] text-[11px]' : 'py-[10px] text-[12px]'} text-right font-num tabular-nums ${tone} border-b border-edge-hair`}
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
          <YoYChip label="Revenue" value={newest.rev_yoy} term="rev_growth" />
          <YoYChip label="PAT" value={newest.pat_yoy} term="eps_growth" />
        </div>
      </div>
    </section>
  )
}
