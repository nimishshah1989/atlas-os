'use client'
// src/components/explorer/InstrumentExplorer.tsx — /etfs and /stocks: which rows the board shows
// by default, how they are grouped, and what it says about what it cannot show yet.
//
// THE DEFAULT IS THE UNIVERSE, NOT THE DIRECTORY. `universe_snapshot.in_universe` already encodes
// the FM's cut — current S&P 500 members for stocks; for ETFs everything above the seeded
// liquidity floor that is neither leveraged nor inverse — and the board ignored it, so the first
// screen was five thousand funds in alphabetical order with blank metrics. It is applied here.
// NOTHING IS HIDDEN: "Everything listed" reveals the rest with each row's own exclusion reason
// beside it, and the geared / inverse toggles say how many funds they would add.
//
// GROUPS BEFORE ROWS. The peer-group strip sits above the table so thousands of funds read as two
// dozen jobs first — a gold-miners fund, a Treasury fund and an S&P tracker have nothing to say to
// each other, and a league table containing all three ranks nothing.
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useMemo } from 'react'
import { ALL, ON, type FacetGroup, type SortState } from '@/lib/explorer'
import {
  expandRows,
  hasClassification,
  hasPrices,
  hasScores,
  hasUniverse,
  universeLabel,
  universeValue,
  type AssetClass,
  type InstrumentRow,
} from '@/lib/facts'
import { formatIsoDate } from '@/lib/format'
import type { InstrumentList } from '@/lib/queries/scores'
import { lensesLabel, peerGroupLabel, peerGroupOf, TIER_LABEL } from '@/lib/scores'
import { boardColumns, universeColumn, type ColumnContext } from './columns'
import { Explorer } from './Explorer'
import { StrengthRiskBubble } from './StrengthRiskBubble'

// ── facets ──────────────────────────────────────────────────────────────────

// The one control that changes what the board IS. A radio, not a checkbox: the two states are
// exclusive and both are named, so nobody has to guess what the default was filtering out.
const UNIVERSE: FacetGroup<InstrumentRow> = {
  key: 'universe',
  label: 'Universe',
  kind: 'one',
  value: (r) => (r.in_universe === true ? 'in' : 'out'),
  options: ['in'],
  labels: { in: 'The board’s universe', [ALL]: 'Everything listed' },
  default: 'in',
}

const PEER: FacetGroup<InstrumentRow> = {
  key: 'peer',
  label: 'Peer group',
  kind: 'any',
  value: peerGroupOf,
  format: peerGroupLabel,
}

const COHORT: FacetGroup<InstrumentRow> = {
  key: 'cohort',
  label: 'Cap cohort',
  kind: 'any',
  value: (r) => r.peer_group ?? 'none',
  format: peerGroupLabel,
}

const SECTOR: FacetGroup<InstrumentRow> = {
  key: 'sector',
  label: 'GICS sector',
  kind: 'any',
  value: (r) => r.sector ?? 'none',
  labels: { none: 'No sector' },
}

// The FM's own words for why this facet exists: "if there is something like an ETF which is
// focused on AI, then creating that artificial intelligence … funds around gold and silver miners
// … water and food security". A fund with no theme is a fund whose name names none — usually a
// broad-market one — so it is labelled as that rather than as a gap in the data.
const THEME: FacetGroup<InstrumentRow> = {
  key: 'theme',
  label: 'Theme',
  kind: 'any',
  value: (r) => r.theme ?? 'none',
  labels: { none: 'No theme in the name' },
}

const COUNTRY: FacetGroup<InstrumentRow> = {
  key: 'country',
  label: 'Country',
  kind: 'any',
  value: (r) => r.country ?? 'none',
  labels: { none: 'Not a single-country fund' },
}

const REGION: FacetGroup<InstrumentRow> = {
  key: 'region',
  label: 'Region',
  kind: 'any',
  value: (r) => r.region ?? 'none',
  labels: { none: 'No region' },
}

// Ten radios in rank order, because a decile facet whose options reorder themselves by count is
// not a scale. `all` is appended by the rail.
const DECILE: FacetGroup<InstrumentRow> = {
  key: 'decile',
  label: 'Decile in peer group',
  kind: 'one',
  value: (r) => (r.composite_decile == null ? 'none' : String(r.composite_decile)),
  options: ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1'],
  format: (v) => (v === '10' ? 'Decile 10 — Leader' : `Decile ${v}`),
  default: ALL,
}

const TIER: FacetGroup<InstrumentRow> = {
  key: 'tier',
  label: 'Conviction',
  kind: 'any',
  value: (r) => r.conviction_tier ?? 'none',
  labels: { ...TIER_LABEL, none: 'Not scored' },
}

// Off by default: geared and inverse funds are out of the universe by the FM's rule of 2026-09-07,
// are never scored, and cannot enter a ranking or a basket. The count beside each box says how
// many rows ticking it would add, so the exclusion is visible rather than silent.
const GEARED: FacetGroup<InstrumentRow> = {
  key: 'geared',
  label: 'Leveraged funds',
  kind: 'flag',
  value: (r) => (r.leveraged ? ON : 'off'),
  labels: { [ON]: 'Include leveraged' },
}

const INVERSE: FacetGroup<InstrumentRow> = {
  key: 'inverse',
  label: 'Inverse funds',
  kind: 'flag',
  value: (r) => (r.inverse ? ON : 'off'),
  labels: { [ON]: 'Include inverse' },
}

// ── the threshold rails ─────────────────────────────────────────────────────
//
// A facet list of categories answers "what kind is it". These answer "is it worth my time": a
// floor on liquidity, a ceiling on what it costs to hold, a floor on what it has actually done.
// They are `min`/`max` rails (src/lib/explorer.ts), so each option's count is how many funds it
// would KEEP, and a fund missing the number never passes — an unmeasured fund is not a calm one.

const money = (n: number) => (n >= 1e9 ? `$${n / 1e9}bn` : n >= 1e6 ? `$${n / 1e6}M` : `$${n / 1e3}k`)
const num = (s: string | null): number | null => (s == null || s === '' ? null : Number(s))

const ADV: FacetGroup<InstrumentRow> = {
  key: 'adv',
  label: 'Traded a day, at least',
  kind: 'min',
  value: (r) => r.adv_usd ?? 'none',
  numeric: (r) => num(r.adv_usd),
  options: ['1000000', '10000000', '50000000', '250000000'],
  format: (v) => money(Number(v)),
  labels: { [ALL]: 'Any' },
  default: ALL,
}

// Annualised volatility, as a fraction. The ceiling an FM sets before they look at a score.
const VOL: FacetGroup<InstrumentRow> = {
  key: 'vol',
  label: 'Volatility a year, at most',
  kind: 'max',
  value: (r) => r.vol_ann ?? 'none',
  numeric: (r) => num(r.vol_ann),
  options: ['0.15', '0.25', '0.40'],
  format: (v) => `${Math.round(Number(v) * 100)} percent`,
  labels: { [ALL]: 'Any' },
  default: ALL,
}

// mdd_12m is negative (a drawdown is a fall), so the rail compares its DEPTH and the option reads
// as the depth too: "at most 20 percent" keeps funds that fell no further than 20 percent.
const MDD: FacetGroup<InstrumentRow> = {
  key: 'mdd',
  label: 'Worst 12m fall, at most',
  kind: 'max',
  value: (r) => r.mdd_12m ?? 'none',
  numeric: (r) => {
    const v = num(r.mdd_12m)
    return v == null ? null : Math.abs(v)
  },
  options: ['0.10', '0.20', '0.35', '0.50'],
  format: (v) => `${Math.round(Number(v) * 100)} percent`,
  labels: { [ALL]: 'Any' },
  default: ALL,
}

const RS: FacetGroup<InstrumentRow> = {
  key: 'rs',
  label: 'Beating the S&P over 12m by',
  kind: 'min',
  value: (r) => r.rs_12m_spy ?? 'none',
  numeric: (r) => num(r.rs_12m_spy),
  options: ['0', '0.10', '0.25'],
  format: (v) => (Number(v) === 0 ? 'Any margin' : `${Math.round(Number(v) * 100)} points`),
  labels: { [ALL]: 'Any' },
  default: ALL,
}

const NOUN: Record<AssetClass, string> = { etf: 'ETFs', stock: 'stocks' }

// ── the surface ─────────────────────────────────────────────────────────────

export function InstrumentExplorer({ assetClass, list }: { assetClass: AssetClass; list: InstrumentList }) {
  const rows = useMemo(() => expandRows(list), [list])
  const scored = hasScores(rows)
  const priced = hasPrices(rows)
  const universe = hasUniverse(rows)
  const classified = hasClassification(rows)
  const etf = assetClass === 'etf'
  // "Everything listed" is the only view in which "why it is out" is a question, so the column
  // exists only there. In the default view every row would answer "in universe", which is 148 px
  // of a column saying nothing — the kind of column that made this table unreadable.
  const widened = useSearchParams().getAll(UNIVERSE.key).includes(ALL)

  const ctx: ColumnContext = useMemo(
    () => ({
      assetClass,
      lensTotal: list.lenses.length,
      technicalWeight: list.lenses.find((l) => l.key === 'technical')?.weight ?? 0,
    }),
    [assetClass, list.lenses],
  )

  const columns = useMemo(() => {
    const base = boardColumns(ctx, scored)
    return universe && widened ? [...base, universeColumn((r) => universeLabel(universeValue(r)))] : base
  }, [ctx, scored, universe, widened])

  const groups = useMemo(() => {
    const g: FacetGroup<InstrumentRow>[] = []
    if (universe) g.push(UNIVERSE)
    if (etf) {
      // Theme sits directly under the peer group: the peer group says what KIND of fund it is,
      // the theme says what it is a bet ON, and the FM reads them in that order.
      if (classified) g.push(PEER, THEME)
    } else {
      g.push(SECTOR)
      if (scored) g.push(COHORT)
    }
    if (scored) g.push(DECILE, TIER)
    if (etf && classified) g.push(COUNTRY, REGION)
    if (priced) g.push(ADV, RS, VOL, MDD)
    if (etf && classified) g.push(GEARED, INVERSE)
    return g
  }, [universe, etf, classified, scored, priced])

  // Strongest first is the only ordering that answers "what is working"; unscored rows fall to the
  // bottom on their own (sortRows keeps nulls last in both directions). With no scores yet the
  // board leads with the most traded names rather than the alphabet.
  const defaultSort: SortState = useMemo(
    () => (scored ? { key: 'composite', dir: 'desc' } : { key: 'adv', dir: 'desc' }),
    [scored],
  )

  const session = list.eod ? formatIsoDate(list.eod) : 'any session'

  // ── what the board says about itself, in clauses rather than paragraphs ────
  //
  // This block used to be five paragraphs explaining the blend, the tier ladder and the decile
  // cut on every visit. All of it was true and none of it was read: a screen a reader has to
  // wade through is a screen they stop reading, and the explanation belongs where someone goes
  // WHEN THEY ASK — /methodology — not in front of the ranking every time. What stays here is
  // only what changes with the data and would mislead if it were missing: how many lenses the
  // scores are actually made of, and which producers have not run.
  const activeLenses = rows.reduce((n, r) => Math.max(n, r.lenses_active ?? 0), 0)
  const notes: string[] = []
  if (scored) {
    notes.push(`Scores are ${lensesLabel(activeLenses, list.lenses.length)}`)
    if (list.scored_on && list.eod && list.scored_on !== list.eod) {
      notes.push(`scored ${formatIsoDate(list.scored_on)}, priced ${session}`)
    }
  } else {
    notes.push(`Not scored for ${session} — nothing below is a score`)
  }
  if (etf && !classified) notes.push('not grouped yet: no peer groups, no country or gearing filters')
  if (!universe) notes.push('universe not marked: every listed instrument is shown')
  if (!priced) notes.push('no prices: relative strength, volatility and traded value are empty')

  return (
    <>
      <p className="mb-3 text-meta text-ink-2" role="status">
        {notes.join(' · ')} ·{' '}
        <Link href="/methodology" className="underline">
          how a score is built
        </Link>
      </p>
      <Explorer
        rows={rows}
        columns={columns}
        groups={groups}
        defaultSort={defaultSort}
        rowKey={(r) => r.symbol}
        noun={NOUN[assetClass]}
        stripKey={etf ? PEER.key : SECTOR.key}
        empty={`No ${NOUN[assetClass]} match these filters. Clear a facet, widen the universe, or shorten the search.`}
        chart={
          scored && priced
            ? (shown) => <StrengthRiskBubble rows={shown} assetClass={assetClass} noun={NOUN[assetClass]} />
            : undefined
        }
      />
    </>
  )
}
