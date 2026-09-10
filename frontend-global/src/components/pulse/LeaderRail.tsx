// LeaderRail — the instruments at both edges of a board, with what puts them there.
//
// The strips above rank GROUPS; this ranks the things you can actually buy. Same discipline: the
// rows come from the SAME cached list /etfs and /stocks render, so the pulse cannot name a leader
// the board does not, and every row is a link into its own page.
//
// THE DECILE IS THE COLOUR, and it is the one this board already cuts — ntile(10) within the
// instrument's own peer group, on read, from `etf_scores_daily` (queries/scores.ts). Nothing here
// invents a band: `decileColour` reads the D1→D10 ramp declared in globals.css, the same ramp
// Atlas India uses, so a decile means one thing on both boards the FM reads side by side.
import Link from 'next/link'
import { DecileChip } from '@/components/ui/DecileChip'
import { instrumentPath, type AssetClass, type InstrumentRow } from '@/lib/facts'
import { formatDecimal, formatPct } from '@/lib/format'
import { rsTint } from '@/lib/scores'

/** Scored rows only, strongest first. An unscored instrument is not the weakest one — it is one
 *  the scorer never looked at (rule #0) — so it has no place in a ranking of scores at all. */
function ranked(rows: readonly InstrumentRow[]): InstrumentRow[] {
  return rows.filter((r) => r.composite != null).sort((a, b) => Number(b.composite) - Number(a.composite))
}

function Row({ r, assetClass, place }: { r: InstrumentRow; assetClass: AssetClass; place: number }) {
  // A fund's theme is what it is a BET ON; a company's GICS sector is what it IS. Neither is a
  // score, and both are the context that stops a bare ticker being a bare ticker.
  const context = assetClass === 'etf' ? r.theme : r.sector
  return (
    <li className="flex items-center gap-2 border-t border-hair px-3 py-1.5 first:border-t-0 hover:bg-raised">
      <span className="w-5 shrink-0 text-right font-num text-[11px] tabular-nums text-ink-3">{place}</span>
      <Link
        href={instrumentPath(assetClass, r.symbol)}
        className="dt-symbol w-[52px] shrink-0 hover:underline"
      >
        {r.symbol}
      </Link>
      <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-2" title={r.name ?? undefined}>
        {context ?? r.name ?? '—'}
      </span>
      <DecileChip decile={r.composite_decile} />
      <span className="w-[34px] shrink-0 text-right font-display text-[12.5px] font-semibold tabular-nums text-ink">
        {formatDecimal(r.composite, 0)}
      </span>
      <span
        className="w-[58px] shrink-0 rounded-tile px-1 py-px text-right font-num text-[12px] tabular-nums"
        style={{ background: rsTint(r.rs_3m_spy) }}
        title="Against the S&P 500 over three months — zero is the index"
      >
        {r.rs_3m_spy == null ? <span className="text-ink-3">—</span> : formatPct(r.rs_3m_spy, 1, { sign: true })}
      </span>
    </li>
  )
}

export function LeaderRail({
  title,
  href,
  assetClass,
  rows,
  show = 5,
}: {
  title: string
  href: string
  assetClass: AssetClass
  rows: readonly InstrumentRow[]
  show?: number
}) {
  const list = ranked(rows)
  const lead = list.slice(0, show)
  const lag = list.slice(Math.max(show, list.length - show))
  const hidden = list.length - lead.length - lag.length

  return (
    <section className="panel overflow-hidden">
      <header className="flex items-baseline justify-between gap-2 border-b border-hair px-3 py-2">
        <h3 className="font-display text-[13.5px] font-semibold text-ink">{title}</h3>
        <Link href={href} className="font-num text-[11px] text-ink-3 hover:text-ink hover:underline">
          all {list.length} scored →
        </Link>
      </header>
      {list.length === 0 ? (
        <p className="px-3 py-3 text-[12.5px] text-ink-3">Nothing on this board carries a score yet.</p>
      ) : (
        <ul>
          {lead.map((r, i) => (
            <Row key={r.symbol} r={r} assetClass={assetClass} place={i + 1} />
          ))}
          {hidden > 0 && (
            <li className="border-t border-edge-strong bg-raised px-3 py-1 text-center font-num text-[10.5px] uppercase tracking-[0.08em] text-ink-3">
              {hidden} between
            </li>
          )}
          {lag.map((r, i) => (
            <Row key={r.symbol} r={r} assetClass={assetClass} place={list.length - lag.length + i + 1} />
          ))}
        </ul>
      )}
    </section>
  )
}
