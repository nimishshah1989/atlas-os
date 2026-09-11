// RankStrip — one ranked group, leading and lagging, every row a door.
//
// The FM: "the pulse needs to be more like summary representations of everything that's there,
// and it needs to be complete… proper red, amber, green representation, clickable pulse, or none
// of these pages should be independent."
//
// ONE COMPONENT, EVERY POPULATION. Sectors, themes and markets are three different questions with
// one shape — a ranked list of groups, each with a score and a distance from the S&P — so they get
// one component. That is what makes the colour on a theme row mean the same thing as the colour on
// a country row, which is the consistency a reader needs to compare them at all.
//
// LEADING AND LAGGING, NEVER JUST LEADING. A summary that only shows the top of a list tells an
// FM where to buy and never where the risk is. The two blocks are the same columns, divided by a
// rule and by how many rows were left out between them.
import Link from 'next/link'
import { formatDecimal, formatPct } from '@/lib/format'
import { rsTint } from '@/lib/scores'
import { rangeTint } from '@/lib/tone'

export type RankItem = {
  id: string
  name: string
  href: string
  /** The group's 0–100 score — its members' median. Null where nothing under it is scored. */
  score: string | null
  /** Distance from the S&P 500 in the relative form, the tint's stated baseline of zero. */
  rs: string | null
  /** The right-hand context: how many members, or which market. Never a number needing a unit. */
  meta: string | null
}

function Rows({ items, best, worst, from }: { items: RankItem[]; best: number; worst: number; from: number }) {
  return (
    <>
      {items.map((it, i) => (
        <li key={it.id} className="flex items-center gap-2 border-t border-hair px-3 py-1.5 first:border-t-0 hover:bg-raised">
          <span className="w-5 shrink-0 text-right font-num text-[11px] tabular-nums text-ink-3">{from + i}</span>
          <Link href={it.href} className="min-w-0 flex-1 truncate text-[13px] text-ink hover:underline" title={it.name}>
            {it.name}
          </Link>
          {it.meta && <span className="shrink-0 font-num text-[11px] text-ink-3">{it.meta}</span>}
          <span
            className="w-[42px] shrink-0 rounded-tile px-1 py-px text-right font-display text-[12.5px] font-semibold tabular-nums text-ink"
            style={{ background: rangeTint(it.score, worst, best) }}
            title="Median member score, 0–100"
          >
            {it.score == null ? '—' : formatDecimal(it.score, 0)}
          </span>
          <span
            className="w-[58px] shrink-0 rounded-tile px-1 py-px text-right font-num text-[12px] tabular-nums"
            style={{ background: rsTint(it.rs) }}
            title="Against the S&P 500 over three months — zero is the index"
          >
            {it.rs == null ? <span className="text-ink-3">—</span> : formatPct(it.rs, 1, { sign: true })}
          </span>
        </li>
      ))}
    </>
  )
}

export function RankStrip({
  title,
  note,
  href,
  items,
  show = 5,
}: {
  title: string
  note: string
  /** The full board this strip is a window onto. */
  href: string
  /** Already ranked, strongest first. */
  items: RankItem[]
  show?: number
}) {
  const scored = items.filter((i) => i.score != null)
  const values = scored.map((i) => Number(i.score))
  const best = values.length ? Math.max(...values) : 0
  const worst = values.length ? Math.min(...values) : 0
  const lead = scored.slice(0, show)
  const lag = scored.slice(Math.max(show, scored.length - show))
  const hidden = scored.length - lead.length - lag.length

  return (
    <section className="panel overflow-hidden">
      <header className="flex items-baseline justify-between gap-2 border-b border-hair px-3 py-2">
        <h3 className="font-display text-[13.5px] font-semibold text-ink">{title}</h3>
        <Link href={href} className="font-num text-[11px] text-ink-3 hover:text-ink hover:underline">
          all {items.length} →
        </Link>
      </header>
      {scored.length === 0 ? (
        <p className="px-3 py-3 text-[12.5px] text-ink-3">Nothing here carries a score yet.</p>
      ) : (
        <ul>
          <Rows items={lead} best={best} worst={worst} from={1} />
          {hidden > 0 && (
            <li className="border-t border-edge-strong bg-raised px-3 py-1 text-center font-num text-[10.5px] uppercase tracking-[0.08em] text-ink-3">
              {hidden} between
            </li>
          )}
          {lag.length > 0 && (
            <Rows items={lag} best={best} worst={worst} from={scored.length - lag.length + 1} />
          )}
        </ul>
      )}
      <p className="border-t border-hair px-3 py-1.5 text-[11px] text-ink-3">{note}</p>
    </section>
  )
}
