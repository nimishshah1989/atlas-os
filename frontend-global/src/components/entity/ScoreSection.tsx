// src/components/entity/ScoreSection.tsx — the glass box: what this instrument scored, where that
// puts it, and what the number is made of, down to the sub-scores the scorer actually computed.
//
// The composite is never shown alone. Beside it stand the decile and the sentence it is shorthand
// for ("ranked 4 of 34 in Equity · Sector"), the conviction tier, and the count of lenses the blend
// had — so a two-lens score cannot be read as a five-lens one. A lens with no producer is an empty
// track and the words "not yet measured", never a zero (rule #0): a fund is not bad at something
// nobody looked at.
//
// Weights come from `atlas_global.atlas_thresholds` (rule #1) — the bar's segment widths ARE the
// weights in force, so if the FM changes one the picture changes with it.
import { CompositeNumeral } from '@/components/ui/CompositeNumeral'
import { DecileChip, LeaderMark } from '@/components/ui/DecileChip'
import { LensBar, type LensSegment } from '@/components/ui/LensBar'
import { Section } from '@/components/ui/Section'
import type { AssetClass } from '@/lib/facts'
import { formatIsoDate, formatNum } from '@/lib/format'
import type { ScoreDetail } from '@/lib/queries/scores'
import { lensesLabel, lensLabel, lensSubs, rankSentence, subLabel, tierLabel } from '@/lib/scores'

const score = (v: string | null | undefined) => (v == null ? null : Number(v))

/** A sub-score is out of 25 by construction (a lens is the mean of its present subs × 4); a lens
 *  is out of 100. Both print the denominator so neither can be read as the other. */
function SubRow({ name, value }: { name: string; value: string | null }) {
  const n = score(value)
  return (
    <div className="fact">
      <dt className="text-meta text-ink-3">{subLabel(name)}</dt>
      <dd className={`num text-body ${n == null ? 'text-ink-3' : 'text-ink'}`}>
        {n == null ? 'not yet measured' : `${formatNum(n, 1)} / 25`}
      </dd>
      <dd className="fact-src text-meta text-ink-3">{name}</dd>
    </div>
  )
}

function LensBlock({
  assetClass,
  lens,
  weight,
  values,
}: {
  assetClass: AssetClass
  lens: string
  weight: number
  values: Record<string, string | null>
}) {
  const n = score(values[lens])
  const subs = lensSubs(assetClass, lens)
  return (
    <div className="slot">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <p className="font-medium text-body text-ink">{lensLabel(lens)}</p>
        <p className="num text-body text-ink-2">
          {n == null ? <span className="text-ink-3">not yet measured</span> : `${formatNum(n, 1)} / 100`}
          <span className="ml-2 text-meta text-ink-3">
            {weight > 0 ? `weight ${formatNum(weight * 100)}%` : 'overlay — displayed, not blended'}
          </span>
        </p>
      </div>
      {subs.length > 0 && (
        <dl className="facts mt-1">
          {subs.map((s) => (
            <SubRow key={s} name={s} value={values[s] ?? null} />
          ))}
        </dl>
      )}
    </div>
  )
}

export function ScoreSection({
  assetClass,
  symbol,
  score: s,
  eod,
}: {
  assetClass: AssetClass
  symbol: string
  score: ScoreDetail | null
  /** The price session the rest of the page is anchored to; the score may be from an earlier one. */
  eod: string | null
}) {
  if (!s) {
    return (
      <Section title="Score" note="not scored yet">
        <p className="text-body text-ink-2">
          {symbol} carries no row in the score journal for this session. It is either outside the
          board’s universe — geared, inverse, below the liquidity floor, or not an index member —
          or the scorer has not reached it. Nothing on this page is a score until it does.
        </p>
      </Section>
    )
  }

  const segments: LensSegment[] = s.lenses.map((l) => ({
    key: l.key,
    label: lensLabel(l.key),
    weight: l.weight,
    score: score(s.values[l.key]),
  }))
  const stamp =
    eod && s.scored_on !== eod
      ? `scored ${formatIsoDate(s.scored_on)}, prices ${formatIsoDate(eod)}`
      : `at EOD ${formatIsoDate(s.scored_on)}`

  return (
    <Section title="Score" note={stamp}>
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <CompositeNumeral value={s.values.composite ?? null} />
        <div className="flex flex-col gap-1">
          <span className="flex items-center gap-2">
            <DecileChip decile={s.decile} title={rankSentence(s.peer_rank, s.peer_n, s.peer_group)} />
            <span className="text-body text-ink-2">{rankSentence(s.peer_rank, s.peer_n, s.peer_group)}</span>
            <LeaderMark decile={s.decile} />
          </span>
          <span className="text-body text-ink-2">
            <span className="text-ink">{tierLabel(s.conviction_tier)}</span> conviction, from{' '}
            {lensesLabel(s.lenses_active, s.lenses.length)}
            {s.coverage_factor != null && ` · coverage ${formatNum(Number(s.coverage_factor) * 100)}%`}
          </span>
        </div>
      </div>

      <LensBar className="mt-5" segments={segments} size="lg" animate />

      <p className="mt-4 max-w-[72ch] text-body text-ink-2">
        Each segment’s width is that lens’s weight in the blend and its fill is the score. An empty
        track is a lens with no producer yet — it contributes nothing and is counted in neither the
        composite nor the conviction tier. The tier ladder&rsquo;s own minimum-layer rule needs
        several independent lenses to agree before the top tiers open: conviction is agreement
        between independent reads, not a high number from one of them.
      </p>

      <div className="slots mt-4">
        {s.lenses.map((l) => (
          <LensBlock key={l.key} assetClass={assetClass} lens={l.key} weight={l.weight} values={s.values} />
        ))}
      </div>
    </Section>
  )
}
