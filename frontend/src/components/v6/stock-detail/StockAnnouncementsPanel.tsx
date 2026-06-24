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
      return 'bg-signal-pos/10 text-signal-pos border-signal-pos/30'
    case 'MEDIUM':
      return 'bg-signal-warn/10 text-signal-warn border-signal-warn/30'
    default: // LOW or unknown
      return 'text-ink-tertiary border-paper-rule'
  }
}
function priorityLabel(priority: string | null): string {
  const p = (priority ?? '').toUpperCase()
  return p === 'HIGH' || p === 'MEDIUM' || p === 'LOW' ? p : 'LOW'
}

const MAX_VISIBLE = 15

function Heading() {
  return (
    <div className="mb-[18px]">
      <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary">Corporate announcements</h2>
      <p className="mt-1 max-w-[760px] font-sans text-[13px] leading-[1.45] text-ink-tertiary">
        Filings to the exchange — capital actions, earnings and governance. Most recent first.
      </p>
    </div>
  )
}

function Subject({ subject, url }: { subject: string | null; url: string | null }) {
  const text = subject ?? '—'
  if (url == null) {
    return <span className="font-sans text-[13px] text-ink-secondary">{text}</span>
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="font-sans text-[13px] text-ink-secondary hover:text-teal hover:underline"
    >
      {text}
      <span aria-hidden className="ml-0.5 text-ink-tertiary">↗</span>
    </a>
  )
}

function FilingRow({ filing }: { filing: StockFiling }) {
  return (
    <li className="flex flex-col gap-1 border-b border-paper-rule/50 py-2 last:border-b-0 sm:flex-row sm:items-baseline sm:gap-3">
      <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-tertiary sm:w-[88px]">
        {filingDate(filing.date)}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-[2px] border px-1.5 py-0.5 font-mono text-[9px] uppercase ${priorityClass(filing.priority)}`}>
            {priorityLabel(filing.priority)}
          </span>
          {filing.bucket && (
            <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{filing.bucket}</span>
          )}
        </div>
        <Subject subject={filing.subject} url={filing.url} />
      </div>
    </li>
  )
}

export function StockAnnouncementsPanel({ filings }: { filings: StockFiling[] }) {
  if (filings.length === 0) {
    return (
      <section className="border-b border-paper-rule px-8 py-9" aria-label="Corporate announcements">
        <Heading />
        <p className="font-sans text-[13px] text-ink-tertiary">No recent corporate announcements.</p>
      </section>
    )
  }

  const visible = filings.slice(0, MAX_VISIBLE)
  const overflow = filings.length - visible.length

  return (
    <section className="border-b border-paper-rule px-8 py-9" aria-label="Corporate announcements">
      <Heading />
      <ul className="rounded-[2px] border border-paper-rule bg-paper px-4">
        {visible.map((f, i) => (
          <FilingRow key={`${f.date}-${i}`} filing={f} />
        ))}
      </ul>
      {overflow > 0 && (
        <p className="mt-2 font-sans text-[11px] text-ink-tertiary">…and {overflow} more.</p>
      )}
    </section>
  )
}
