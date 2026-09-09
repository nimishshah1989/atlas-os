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
      if (classified) g.push(PEER)
    } else {
      g.push(SECTOR)
      if (scored) g.push(COHORT)
    }
    if (scored) g.push(DECILE, TIER)
    if (etf && classified) g.push(COUNTRY, REGION, GEARED, INVERSE)
    return g
  }, [universe, etf, classified, scored])

  // Strongest first is the only ordering that answers "what is working"; unscored rows fall to the
  // bottom on their own (sortRows keeps nulls last in both directions). With no scores yet the
  // board leads with the most traded names rather than the alphabet.
  const defaultSort: SortState = useMemo(
    () => (scored ? { key: 'composite', dir: 'desc' } : { key: 'adv', dir: 'desc' }),
    [scored],
  )

  const session = list.eod ? formatIsoDate(list.eod) : 'any session'
  const notices: { lead: string; text: string }[] = []

  if (scored) {
    notices.push({
      lead: 'Every composite says how many lenses it is made of.',
      text:
        `The blend carries ${list.lenses.length} lenses and only the ones with a producer today ` +
        `contribute, so each row prints its own count — “${lensesLabel(1, list.lenses.length)}” — ` +
        `beside the score. While one lens is active the tier ladder’s own minimum-layer rule caps ` +
        `the result at MEDIUM however strong it is: conviction means agreement between independent ` +
        `reads, and there is one read. That is the methodology working, not a defect. Deciles are ` +
        `cut within the peer group, on read, over scored funds only; Leader is that group’s top decile.`,
    })
    if (list.scored_on && list.eod && list.scored_on !== list.eod) {
      notices.push({
        lead: `Scores are from ${formatIsoDate(list.scored_on)}, prices from ${session}.`,
        text: 'The scorer has not run for the latest session yet; the ranking below is the last one it wrote.',
      })
    }
  } else {
    notices.push({
      lead: 'Not scored yet — no ranking on this board.',
      text:
        etf
          ? `Composite, conviction, decile and the technical lens join this table once ` +
            `scripts/global_market/score_etfs.py has written ${session}. Nothing below is a score.`
          : `Composite, conviction, decile and the technical lens join this table once the stock ` +
            `scorer has written lens_scores_daily for ${session}. Nothing below is a score.`,
    })
  }
  if (etf && !classified) {
    notices.push({
      lead: 'Funds are not grouped yet.',
      text: 'The peer-group strip and the country, region and gearing facets appear once scripts/global_market/classify_etfs.py has run.',
    })
  }
  if (!universe) {
    notices.push({
      lead: 'Universe not marked yet.',
      text: `The board shows every listed instrument until the universe snapshot has run for ${session}: S&P 500 members for stocks, and ETFs above the liquidity floor that are neither leveraged nor inverse.`,
    })
  }
  if (!priced) {
    notices.push({
      lead: 'Prices not loaded yet.',
      text: `Relative strength, 52-week position, traded value, volatility and drawdown join this table once the price spine has run; no row carries one for ${session}.`,
    })
  }

  return (
    <>
      {notices.length > 0 && (
        <div className="notice text-body" role="status">
          <span aria-hidden="true" className="dot bg-warn" />
          <div className="space-y-1">
            {notices.map((m) => (
              <p key={m.lead}>
                <span className="font-medium text-ink">{m.lead}</span> {m.text}
              </p>
            ))}
          </div>
        </div>
      )}
      <Explorer
        rows={rows}
        columns={columns}
        groups={groups}
        defaultSort={defaultSort}
        rowKey={(r) => r.symbol}
        noun={NOUN[assetClass]}
        stripKey={etf ? PEER.key : SECTOR.key}
        empty={`No ${NOUN[assetClass]} match these filters. Clear a facet, widen the universe, or shorten the search.`}
      />
    </>
  )
}
