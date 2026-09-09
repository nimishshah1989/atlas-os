// src/components/entity/ScoreSection.tsx — the glass box, as Atlas India draws it: the DecileLadder.
//
// WHAT CHANGED AND WHY. This section used to print every sub-score as a <dt>/<dd> pair and repeat
// "overlay — displayed, not blended" on every row, under a six-line paragraph explaining what a
// weight is. Same facts, four times the height. The ladder keeps ALL of them — composite, decile,
// the rank sentence, conviction tier, lens count, coverage, every weight, every sub-score, the
// evidence — and moves them into three header tiles and one collapsible row per lens. The two
// methodology decisions a reader must know to read the number are behind the InfoTip on the title
// row; nothing else is said in prose.
//
// A LENS WITH NO PRODUCER IS AN EMPTY TRACK AND THE WORDS "not yet measured", NEVER A ZERO
// (rule #0). Weights come from `atlas_global.atlas_thresholds` (rule #1) — the Weight column IS
// the weights in force, so if the FM changes one the picture changes with it.
import { CompositeNumeral } from '@/components/ui/CompositeNumeral'
import { DecileLadder, type LadderTile } from '@/components/ui/DecileLadder'
import { DecileMeter } from '@/components/ui/DecileMeter'
import { InfoTip } from '@/components/ui/InfoTip'
import { LeaderMark } from '@/components/ui/DecileChip'
import { Section } from '@/components/ui/Section'
import type { AssetClass } from '@/lib/facts'
import { formatIsoDate, formatPct } from '@/lib/format'
import { scoreToLadder, topLens } from '@/lib/ladder'
import type { ScoreDetail } from '@/lib/queries/scores'
import { lensesLabel, peerGroupLabel, rankSentence, tierLabel } from '@/lib/scores'

function HowToRead() {
  return (
    <InfoTip title="How to read this">
      An empty track is a lens with no producer yet: it is counted in neither the composite nor the
      conviction tier — a name is not weak at something nobody has measured. The tier ladder needs
      several independent lenses to agree before its top tiers open, so conviction is agreement
      between separate reads, not one high number.
    </InfoTip>
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
          No score journal row for {symbol} this session — outside the board’s universe, or the
          scorer has not reached it.
        </p>
      </Section>
    )
  }

  const lenses = scoreToLadder(assetClass, s)
  const rank = rankSentence(s.peer_rank, s.peer_n, s.peer_group)
  const stamp =
    eod && s.scored_on !== eod
      ? `scored ${formatIsoDate(s.scored_on)}, prices ${formatIsoDate(eod)}`
      : `at EOD ${formatIsoDate(s.scored_on)}`

  const tiles: LadderTile[] = [
    {
      label: 'Composite',
      value: <CompositeNumeral value={s.values.composite ?? null} size="md" />,
      sub: lensesLabel(s.lenses_active, s.lenses.length),
    },
    {
      label: 'Decile',
      value: (
        <>
          <span className={s.decile == null ? 'text-txt-3' : undefined}>
            {s.decile == null ? '—' : `D${s.decile}`}
          </span>
          <DecileMeter decile={s.decile} title={rank} />
          <LeaderMark decile={s.decile} />
        </>
      ),
      sub: rank,
    },
    {
      label: 'Conviction',
      value: <span className="font-sans text-[17px]">{tierLabel(s.conviction_tier)}</span>,
      sub: s.coverage_factor == null ? undefined : `coverage ${formatPct(s.coverage_factor, 0)}`,
    },
  ]

  return (
    <Section title="Score" note={stamp} aside={<HowToRead />}>
      <DecileLadder
        lenses={lenses}
        tiles={tiles}
        cohortLabel={peerGroupLabel(s.peer_group)}
        defaultOpenKey={topLens(lenses)}
      />
    </Section>
  )
}
