// src/components/countries/CountryPicks.tsx — the two or three funds that are a decision, above
// the twenty that are a list. Server-rendered: it reads rows and links, it holds no state.
import Link from 'next/link'
import { DecileMeter } from '@/components/ui/DecileMeter'
import { formatUsdCompact } from '@/lib/format'
import type { Pick } from '@/lib/countryPicks'
import { decileColour } from '@/lib/scores'
import { whyNotOffered } from '@/lib/universe'

/** What a reader must see on the card itself rather than one page deeper: the currency call, and
 *  any rule that would stop the FM buying this one. */
function flags(p: Pick): string | null {
  const f = p.fund
  const on = [f.hedged ? 'currency-hedged' : null, whyNotOffered(f.exclusion_reason)]
  const set = on.filter((x): x is string => typeof x === 'string' && x.length > 0)
  return set.length ? set.join(' · ') : null
}

function Card({ pick }: { pick: Pick }) {
  const f = pick.fund
  const composite = f.composite == null ? null : Number(f.composite)
  const structure = flags(pick)
  return (
    <div className="rounded-tile border border-edge-hair bg-surface-raised px-4 py-3.5 shadow-tile">
      <div className="text-meta uppercase tracking-[0.14em] text-ink-3">{pick.label}</div>

      <div className="mt-2 flex items-baseline justify-between gap-3">
        <Link
          href={`/etfs/${encodeURIComponent(f.symbol)}`}
          className="num text-[22px] font-semibold leading-none tracking-tight text-ink no-underline hover:text-accent"
        >
          {f.symbol}
        </Link>
        <span className="num text-[22px] font-semibold leading-none" style={{ color: decileColour(f.decile) ?? undefined }}>
          {composite == null ? '—' : composite.toFixed(0)}
        </span>
      </div>

      <div className="mt-1.5 flex items-baseline justify-between gap-3">
        <span className="text-meta text-ink-2">{f.name}</span>
        <span className="whitespace-nowrap text-meta text-ink-3">
          {f.rank == null ? 'unranked' : `rank ${f.rank}`}
        </span>
      </div>

      <div className="mt-2.5">
        <DecileMeter decile={f.decile} title="Within this market's ranked funds" />
      </div>

      <p className="mt-3 text-meta leading-relaxed text-ink-2">{pick.note}</p>

      <div className="mt-3 border-t border-hair pt-2 text-meta text-ink-3">
        {formatUsdCompact(f.adv_usd_60d_median)} traded a day
        {f.aum_usd ? ` · ${formatUsdCompact(f.aum_usd)} held` : ''}
        {structure ? ` · ${structure}` : ''}
      </div>
    </div>
  )
}

export function CountryPicks({ picks, rest }: { picks: Pick[]; rest: string | null }) {
  if (picks.length === 0) {
    return (
      <p className="text-body text-ink-2">
        No fund covering this market is a plain, ranked way to own it — every one is geared, inverse or
        below the liquidity floor. The full list is below.
      </p>
    )
  }
  return (
    <>
      <div className="grid gap-3 md:grid-cols-3">
        {picks.map((p) => (
          <Card key={p.kind} pick={p} />
        ))}
      </div>
      {rest && <p className="mt-2 text-meta text-ink-3">{rest}</p>}
    </>
  )
}
