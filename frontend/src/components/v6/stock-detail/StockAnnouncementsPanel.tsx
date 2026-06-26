// StockAnnouncementsPanel — real corporate announcements for the v4 stock detail page.
// Replaces the empty TradingView "Top Stories" widget. Chronological list (newest-first)
// of exchange filings — capital actions, earnings, governance — each with a priority chip,
// bucket tag and the subject (linked to the NSE source when available).
// Pure presentational server component — data already fetched via getStockAnnouncements().
import type { StockFiling } from '@/lib/queries/v6/stock_lens'

// Two-digit calendar month → short name. String-keyed so we never coerce via Number().
const MON: Record<string, string> = {
  '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
  '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}

// 'YYYY-MM-DD' → "20 Jun '26". Parsed by field, no Date() / tz drift.
function filingDate(date: string): string {
  const [y, m, d] = date.split('-')
  const day = d.startsWith('0') ? d.slice(1) : d // drop leading zero without numeric coercion
  return `${day} ${MON[m] ?? m} '${y.slice(2)}`
}

// Priority chip styling. Unknown/null priority falls through to the muted LOW look.
function priorityClass(priority: string | null): string {
  switch ((priority ?? '').toUpperCase()) {
    case 'HIGH':
      return 'bg-sig-pos/10 text-sig-pos border-sig-pos/30'
    case 'MEDIUM':
      return 'bg-sig-warn/10 text-sig-warn border-sig-warn/30'
    default: // LOW or unknown
      return 'text-txt-3 border-edge-hair'
  }
}
function priorityLabel(priority: string | null): string {
  const p = (priority ?? '').toUpperCase()
  return p === 'HIGH' || p === 'MEDIUM' || p === 'LOW' ? p : 'LOW'
}

const MAX_VISIBLE = 15

// Plain-language gloss of WHAT a filing is (FM 2026-06-26: a one-line summary + expand,
// not just a raw link). Keyed by the catalyst category, then the bucket, then a generic
// fallback. Real categories only — nothing fabricated about the specific filing.
const CATEGORY_GLOSS: Record<string, string> = {
  order_win: 'A new order / contract win — real business momentum, routed to the high-weight earnings bucket of the Catalyst lens.',
  buyback: 'A share buyback — the company is returning cash and signalling the board sees the stock as undervalued.',
  bonus_split: 'A bonus issue or stock split — value-neutral, but often a confidence signal and it improves liquidity.',
  dividend: 'A dividend declaration — a cash return to shareholders.',
  earnings: 'A results / earnings filing — the most material category for the fundamental picture.',
  esop: 'An employee stock-option (ESOP) action — routine compensation / governance housekeeping.',
  litigation: 'A legal or regulatory matter — a potential governance risk or contingent liability.',
}
const BUCKET_GLOSS: Record<string, string> = {
  earnings_strategy: 'Business & earnings momentum — the highest-weight Catalyst bucket.',
  capital_action: 'A capital action (buyback / dividend / split) — how the company is managing its equity.',
  governance: 'A governance / disclosure filing — lower signal weight, context only.',
}
function glossFor(f: StockFiling): string {
  if (f.category && CATEGORY_GLOSS[f.category]) return CATEGORY_GLOSS[f.category]
  if (f.bucket && BUCKET_GLOSS[f.bucket]) return BUCKET_GLOSS[f.bucket]
  return 'An exchange filing — open the original disclosure on NSE for the full text.'
}

function Heading() {
  return (
    <div className="mb-[18px]">
      <h2 className="font-display text-[26px] font-normal tracking-tight text-txt-1">Corporate announcements</h2>
      <p className="mt-1 max-w-[760px] font-sans text-[13px] leading-[1.45] text-txt-3">
        Filings to the exchange — capital actions, earnings and governance. Most recent first.
      </p>
    </div>
  )
}

// One filing = a native <details>: the SUMMARY is the one-liner (date · chips · subject);
// expanding reveals the plain-language gloss + the link to the original NSE filing.
function FilingRow({ filing }: { filing: StockFiling }) {
  const subject = filing.subject ?? '—'
  return (
    <li className="border-b border-edge-hair last:border-b-0">
      <details className="group/f py-2">
        <summary className="flex cursor-pointer list-none select-none flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-3">
          <span className="shrink-0 font-num text-[11px] tabular-nums text-txt-3 sm:w-[88px]">
            {filingDate(filing.date)}
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-tile border px-1.5 py-0.5 font-num text-[9px] uppercase ${priorityClass(filing.priority)}`}>
                {priorityLabel(filing.priority)}
              </span>
              {filing.bucket && (
                <span className="font-num text-[10px] uppercase tracking-wider text-txt-3">{filing.bucket}</span>
              )}
            </div>
            <span className="font-sans text-[13px] text-txt-2">{subject}</span>
          </div>
          <span aria-hidden className="shrink-0 self-start font-num text-[12px] text-txt-3 transition-transform group-open/f:rotate-90 sm:self-center">›</span>
        </summary>
        <div className="mt-2 flex flex-col gap-2 pl-0 sm:pl-[100px]">
          <p className="font-sans text-[12.5px] leading-[1.5] text-txt-2">{glossFor(filing)}</p>
          {filing.url && (
            <a
              href={filing.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-num text-[11px] text-brand hover:underline"
            >
              View original filing on NSE ↗
            </a>
          )}
        </div>
      </details>
    </li>
  )
}

export function StockAnnouncementsPanel({ filings }: { filings: StockFiling[] }) {
  if (filings.length === 0) {
    return (
      <section className="border-b border-edge-hair px-8 py-9" aria-label="Corporate announcements">
        <Heading />
        <p className="font-sans text-[13px] text-txt-3">No recent corporate announcements.</p>
      </section>
    )
  }

  const visible = filings.slice(0, MAX_VISIBLE)
  const overflow = filings.length - visible.length

  return (
    <section className="border-b border-edge-hair px-8 py-9" aria-label="Corporate announcements">
      <Heading />
      <ul className="rounded-tile border border-edge-hair bg-surface-panel px-4">
        {visible.map((f, i) => (
          <FilingRow key={`${f.date}-${i}`} filing={f} />
        ))}
      </ul>
      {overflow > 0 && (
        <p className="mt-2 font-sans text-[11px] text-txt-3">…and {overflow} more.</p>
      )}
    </section>
  )
}
