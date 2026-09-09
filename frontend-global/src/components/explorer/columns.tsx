'use client'
// src/components/explorer/columns.tsx — what a row of the ranked board says, and how wide it says
// it. Two column sets, one shape: identity, then where the fund is ranked, then the ranking, then
// the price evidence behind it, then — behind a hairline — the risk overlay, which is displayed
// and not blended.
//
// EVERY WIDTH IS A PROMISE. `table-layout: fixed` gives sized columns their width and hands the
// rest to the one unsized column, so a column with no floor is a column that disappears. The name
// column carries `minWidth` for exactly that reason: it is counted into the table's own min-width,
// so a fund name has 280 px at any viewport instead of the 160 px leftover that rendered every
// name in this list as an ellipsis.
//
// NOTHING HERE INVENTS A NUMBER. A null score renders as an em dash, never 0 — a fund is not bad
// at a lens nobody measured (rule #0) — and every composite is printed beside the count of lenses
// it was actually built from, so a two-lens score cannot be read as a full one.
import Link from 'next/link'
import { Chip } from '@/components/ui/Chip'
import { DecileChip, LeaderMark } from '@/components/ui/DecileChip'
import { LensBar } from '@/components/ui/LensBar'
import type { AssetClass, InstrumentRow } from '@/lib/facts'
import { formatDecimal, formatPct, formatUsd } from '@/lib/format'
import {
  lensesLabel,
  lensesShort,
  orderBy,
  peerGroupLabel,
  peerGroupOf,
  rankSentence,
  rsTint,
  tierLabel,
} from '@/lib/scores'
import type { Column } from './DataTable'

/** What the columns need from the page: which market, how many lenses the blend has weights for,
 *  and the technical lens's own weight (the bar's one segment). */
export type ColumnContext = { assetClass: AssetClass; lensTotal: number; technicalWeight: number }

// ── identity ────────────────────────────────────────────────────────────────

const symbol = (assetClass: AssetClass): Column<InstrumentRow> => ({
  key: 'symbol',
  label: 'Symbol',
  width: 72,
  sortValue: (r) => r.symbol,
  render: (r) => (
    <Link href={`/${assetClass}s/${encodeURIComponent(r.symbol)}`} className="dt-symbol">
      {r.symbol}
    </Link>
  ),
})

const NAME: Column<InstrumentRow> = {
  key: 'name',
  label: 'Name',
  width: 0,
  minWidth: 280,
  sortValue: (r) => r.name,
  render: (r) => (
    <span className="text-ink" title={r.name ?? undefined}>
      {r.name ?? '—'}
    </span>
  ),
}

// ── where it is ranked ──────────────────────────────────────────────────────

const PEER: Column<InstrumentRow> = {
  key: 'peer',
  label: 'Peer group',
  width: 150,
  title: 'Asset class × strategy — the funds this one is ranked against',
  sortValue: (r) => peerGroupLabel(peerGroupOf(r)),
  render: (r) => {
    const group = peerGroupOf(r)
    return <Chip title={rankSentence(r.peer_rank, r.peer_n, r.peer_group)}>{peerGroupLabel(group)}</Chip>
  },
}

const SECTOR_COL: Column<InstrumentRow> = {
  key: 'sector',
  label: 'GICS sector',
  width: 150,
  sortValue: (r) => r.sector,
  render: (r) => (r.sector ? <Chip>{r.sector}</Chip> : <span className="text-ink-3">—</span>),
}

const COHORT: Column<InstrumentRow> = {
  key: 'cohort',
  label: 'Cohort',
  width: 92,
  title: 'SPY-weight tercile — the population the decile is cut within',
  sortValue: (r) => peerGroupLabel(r.peer_group),
  render: (r) =>
    r.peer_group ? (
      <Chip title={rankSentence(r.peer_rank, r.peer_n, r.peer_group)}>{peerGroupLabel(r.peer_group)}</Chip>
    ) : (
      <span className="text-ink-3">—</span>
    ),
}

// ── the ranking ─────────────────────────────────────────────────────────────

const COMPOSITE: Column<InstrumentRow> = {
  key: 'composite',
  label: 'Composite',
  width: 100,
  align: 'right',
  title: 'The blended score, 0–100, with its decile within the peer group',
  sortValue: (r) => orderBy(r.composite),
  // One em dash, not two: an unscored row says "nothing here" once. The chip joins the numeral
  // only when there is a rank to show, because a decile without a composite is not a thing.
  render: (r) =>
    r.composite == null ? (
      <span className="num text-ink-3">—</span>
    ) : (
      <span className="flex items-center justify-end gap-1.5">
        <span className="num text-section font-medium text-ink" data-composite="">
          {formatDecimal(r.composite, 0)}
        </span>
        <DecileChip decile={r.composite_decile} title={rankSentence(r.peer_rank, r.peer_n, r.peer_group)} />
      </span>
    ),
}

const CONVICTION: Column<InstrumentRow> = {
  key: 'tier',
  label: 'Conviction',
  width: 124,
  title:
    'The tier ladder’s verdict. Its own minimum-layer rule needs several independent lenses to ' +
    'agree before the top tiers open — conviction is agreement between independent reads, so a ' +
    'fund with few active lenses cannot reach them. Leader = top decile in the peer group.',
  sortValue: (r) => tierLabel(r.conviction_tier),
  render: (r) => (
    <span className="flex items-center gap-2">
      <span className={r.conviction_tier ? 'text-ink' : 'text-ink-3'}>{tierLabel(r.conviction_tier)}</span>
      <LeaderMark decile={r.composite_decile} />
    </span>
  ),
}

const lenses = (ctx: ColumnContext): Column<InstrumentRow> => ({
  key: 'lenses',
  label: 'Lenses',
  width: 70,
  align: 'right',
  title: 'How many of the blend’s lenses this composite was built from. Four of five have no producer yet.',
  sortValue: (r) => r.lenses_active,
  render: (r) => (
    <span className={r.lenses_active == null ? 'text-ink-3' : 'text-ink-2'} title={lensesLabel(r.lenses_active, ctx.lensTotal)}>
      {lensesShort(r.lenses_active, ctx.lensTotal)}
    </span>
  ),
})

const technical = (ctx: ColumnContext): Column<InstrumentRow> => ({
  key: 'technical',
  label: 'Technical',
  width: 96,
  title: 'The technical lens, 0–100: trend, relative strength vs SPY, relative strength vs peers, structure',
  sortValue: (r) => orderBy(r.technical),
  render: (r) => (
    <span className="flex items-center gap-2">
      <span className={`num w-6 shrink-0 text-right ${r.technical == null ? 'text-ink-3' : 'text-ink'}`}>
        {formatDecimal(r.technical, 0)}
      </span>
      <LensBar
        className="min-w-0"
        segments={[
          {
            key: 'technical',
            label: 'Technical',
            weight: ctx.technicalWeight,
            score: r.technical == null ? null : Number(r.technical),
          },
        ]}
      />
    </span>
  ),
})

// ── the price evidence ──────────────────────────────────────────────────────

type RsKey = 'rs_3m_spy' | 'rs_6m_spy' | 'rs_12m_spy'

// Tinted the way the country grid tints, and for the same reason: the tint shows the SHAPE of a
// row at a glance and carries nothing the printed value does not. Readable in greyscale.
const rs = (key: RsKey, label: string): Column<InstrumentRow> => ({
  key,
  label,
  width: 64,
  align: 'right',
  title: `Relative strength vs SPY, ${label} — (1+r_fund)/(1+r_SPY) − 1, what is left after the index`,
  sortValue: (r) => orderBy(r[key]),
  cellStyle: (r) => {
    const background = rsTint(r[key])
    return background ? { background } : undefined
  },
  render: (r) => formatPct(r[key], 1, { sign: true }),
})

const POS_52W: Column<InstrumentRow> = {
  key: 'pos_52w',
  label: '52w',
  width: 54,
  align: 'right',
  title: 'Position in the 52-week range, 0 to 100',
  sortValue: (r) => orderBy(r.pos_52w),
  render: (r) => formatDecimal(r.pos_52w, 0),
}

const ADV: Column<InstrumentRow> = {
  key: 'adv',
  label: 'ADV$',
  width: 88,
  align: 'right',
  title: 'Median daily traded value over 60 sessions — the liquidity the universe floor is set on',
  sortValue: (r) => orderBy(r.adv_usd),
  render: (r) => formatUsd(r.adv_usd, 0),
}

// ── the risk overlay (displayed, not blended) ───────────────────────────────

const VOL: Column<InstrumentRow> = {
  key: 'vol',
  label: 'Vol',
  width: 62,
  align: 'right',
  divider: true,
  title: 'Annualised volatility over 252 sessions. Risk is an OVERLAY: shown, not blended, until the FM sets its weight.',
  sortValue: (r) => orderBy(r.vol_ann),
  render: (r) => formatPct(r.vol_ann, 0),
}

const MDD: Column<InstrumentRow> = {
  key: 'mdd',
  label: 'Max DD',
  width: 70,
  align: 'right',
  title: 'Deepest peak-to-trough fall over 12 months',
  sortValue: (r) => orderBy(r.mdd_12m),
  render: (r) => formatPct(r.mdd_12m, 0),
}

/** The universe verdict, shown only once the reader has asked for everything listed. */
export const universeColumn = (label: (r: InstrumentRow) => string): Column<InstrumentRow> => ({
  key: 'universe',
  label: 'Why it is out',
  width: 148,
  title: 'In the universe at EOD, or the reason the snapshot left the instrument out',
  sortValue: label,
  render: (r) => <span className={r.in_universe ? 'text-ink-3' : 'text-ink-2'}>{label(r)}</span>,
})

// ── the two column sets ─────────────────────────────────────────────────────

const SCORE_COLUMNS = (ctx: ColumnContext) => [COMPOSITE, CONVICTION, lenses(ctx), technical(ctx)]
const PRICE_COLUMNS = [rs('rs_3m_spy', 'RS 3m'), rs('rs_6m_spy', 'RS 6m'), rs('rs_12m_spy', 'RS 12m'), POS_52W, ADV]
const RISK_COLUMNS = [VOL, MDD]

/** The board's columns for this market, with the score block dropped entirely when nothing is
 *  scored yet — a wall of em dashes is not a state, it is a shrug. */
export function boardColumns(ctx: ColumnContext, scored: boolean): Column<InstrumentRow>[] {
  const identity =
    ctx.assetClass === 'etf'
      ? [symbol('etf'), NAME, PEER]
      : [symbol('stock'), NAME, SECTOR_COL, COHORT]
  return [...identity, ...(scored ? SCORE_COLUMNS(ctx) : []), ...PRICE_COLUMNS, ...RISK_COLUMNS]
}
