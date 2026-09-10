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
import { DecileMeter } from '@/components/ui/DecileMeter'
import { LensBar } from '@/components/ui/LensBar'
import { instrumentPath, type AssetClass, type InstrumentRow } from '@/lib/facts'
import { formatDecimal, formatPct, formatUsd, formatUsdCompact } from '@/lib/format'
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
    <Link href={instrumentPath(assetClass, r.symbol)} className="dt-symbol">
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
  width: 124,
  align: 'right',
  title: 'The blended score, 0–100, with its decile within the peer group',
  sortValue: (r) => orderBy(r.composite),
  // One em dash, not two: an unscored row says "nothing here" once. The chip joins the numeral
  // only when there is a rank to show, because a decile without a composite is not a thing.
  //
  // The METER under the numeral is the glyph India's board uses everywhere a decile appears, and
  // it is what makes a two-thousand-row table scannable: a reader finds the full bars without
  // reading a single number. The chip beside the numeral keeps the digit, so the column still
  // reads in greyscale and in a screenshot.
  render: (r) =>
    r.composite == null ? (
      <span className="num text-ink-3">—</span>
    ) : (
      <span className="flex flex-col items-end gap-0.5">
        <span className="flex items-center gap-1.5">
          <span className="num text-section font-medium text-ink" data-composite="">
            {formatDecimal(r.composite, 0)}
          </span>
          <DecileChip decile={r.composite_decile} title={rankSentence(r.peer_rank, r.peer_n, r.peer_group)} />
        </span>
        <DecileMeter decile={r.composite_decile} title={rankSentence(r.peer_rank, r.peer_n, r.peer_group)} />
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
  // COUNTED, never asserted: this used to say "four of five have no producer yet", which was true
  // the week it was written and wrong the week a lens landed. The denominator is the weight table's.
  title: `How many of the blend’s ${ctx.lensTotal} lenses this composite was built from.`,
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
  // 64 px held "+8.4%" and ellipsised everything longer, so a column of relative strengths read
  // "+8… +26… +47…" — the FM: "look at these numbers and how they are getting cut. I can't even
  // make sense of it." A signed percentage with a tenth is up to seven characters ("+129.4%").
  width: 82,
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
  width: 76,
  align: 'right',
  title: 'Median daily traded value over 60 sessions — the liquidity the universe floor is set on',
  sortValue: (r) => orderBy(r.adv_usd),
  // COMPACT, and narrower than it was. "$129,145,821" needs about 85 px of text and was rendering
  // as "$129,1…"; "$129M" needs 40 and can be compared against "$1.8B" at a glance, which two
  // truncations cannot. The exact figure is the cell's own title, one hover away.
  render: (r) => (
    <span title={r.adv_usd == null ? undefined : formatUsd(r.adv_usd, 0)}>
      {formatUsdCompact(r.adv_usd)}
    </span>
  ),
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


// ── what the fund COSTS and how big it is ───────────────────────────────────

const THEME_COL: Column<InstrumentRow> = {
  key: 'theme_col',
  label: 'Theme',
  width: 150,
  title: 'What the fund is a bet ON, from the name. Opens every other fund making the same bet.',
  sortValue: (r) => r.theme ?? '',
  render: (r) =>
    // A word that goes nowhere is a label; a word that goes somewhere is the drill-down the FM
    // asked for. A fund with no theme is not a gap — most of the listed universe is a bet on
    // nothing narrower than the market — so it reads as words rather than an em dash.
    r.theme && r.theme_id ? (
      <Link href={`/themes/${encodeURIComponent(r.theme_id)}`} className="text-ink hover:underline" title={r.theme}>
        {r.theme}
      </Link>
    ) : (
      <span className="text-ink-3">no theme in the name</span>
    ),
}

const EXPENSE: Column<InstrumentRow> = {
  key: 'expense',
  label: 'Fee',
  width: 62,
  align: 'right',
  title:
    'Annual expense ratio. The one cost that is certain before you own it, and the one number ' +
    'that compounds against you every year you do.',
  sortValue: (r) => orderBy(r.expense_ratio),
  // A fee is a fraction (0.0075 = 0.75 percent), and two decimals because the difference between
  // 0.03 and 0.09 percent is a threefold difference in what it costs to hold.
  render: (r) => formatPct(r.expense_ratio, 2),
}

const AUM: Column<InstrumentRow> = {
  key: 'aum',
  label: 'Assets',
  width: 76,
  align: 'right',
  title: 'Fund assets under management, with its as-of date on the fund’s own page',
  sortValue: (r) => orderBy(r.aum_usd),
  render: (r) => (
    <span title={r.aum_usd == null ? undefined : formatUsd(r.aum_usd, 0)}>
      {formatUsdCompact(r.aum_usd)}
    </span>
  ),
}

const TREND: Column<InstrumentRow> = {
  key: 'trend',
  label: '200d',
  width: 52,
  align: 'right',
  title:
    'Above its own 200-day average. Blank means the instrument has fewer than 200 sessions — ' +
    'it has not FAILED a test nobody could run on it (rule #0).',
  sortValue: (r) => (r.above_ema_200 == null ? null : r.above_ema_200 ? 1 : 0),
  render: (r) =>
    r.above_ema_200 == null ? (
      <span className="text-ink-3" title="Fewer than 200 sessions">
        —
      </span>
    ) : (
      // The glyph and the colour say the same thing twice, so the column reads in greyscale.
      <span style={{ color: r.above_ema_200 ? 'var(--color-pos)' : 'var(--color-neg)' }}>
        {r.above_ema_200 ? '▲' : '▼'}
      </span>
    ),
}

// ── every lens the blend carries, side by side ──────────────────────────────

/** One lens as a 0–100 number with its own decile behind it. The FM, on two funds an inch apart
 *  on composite: the lens columns are what says one is cheap and liquid and the other is not. */
const lensColumn = (key: 'risk' | 'cost_liquidity' | 'flow' | 'quality' | 'fundamental' | 'valuation' | 'catalyst', label: string, title: string): Column<InstrumentRow> => ({
  key: `lens_${key}`,
  label,
  width: 66,
  align: 'right',
  title,
  sortValue: (r) => orderBy(r[key]),
  // Null renders as an em dash, never 0: a fund is not bad at a lens nobody measured (rule #0).
  render: (r) => formatDecimal(r[key], 0),
})

const ETF_LENS_COLUMNS = [
  lensColumn('risk', 'Risk', 'Volatility, drawdown and beta within the asset group. An OVERLAY: displayed, not blended.'),
  lensColumn('cost_liquidity', 'Cost', 'Expense ratio, traded value, assets and concentration, each as a percentile within the asset group.'),
  lensColumn('flow', 'Flow', 'Change in shares outstanding — creations and redemptions — centred at 50.'),
  lensColumn('quality', 'Quality', 'The holdings looked through to their own stock scores. Present only where enough of the fund is scoreable.'),
]

const STOCK_LENS_COLUMNS = [
  lensColumn('fundamental', 'Fundamental', 'Profitability, margins, growth, balance sheet and operating leverage from the filings.'),
  lensColumn('valuation', 'Valuation', 'Multiples against the sector cross-section. An OVERLAY: displayed, not blended.'),
  lensColumn('catalyst', 'Catalyst', '8-K item codes with recency decay — what the registrant itself filed.'),
  lensColumn('flow', 'Flow', 'Short interest and its change, from FINRA’s twice-monthly settlement.'),
]

// ── the column sets ─────────────────────────────────────────────────────────

const SCORE_COLUMNS = (ctx: ColumnContext) => [COMPOSITE, CONVICTION, lenses(ctx), technical(ctx)]
const PRICE_COLUMNS = [rs('rs_3m_spy', 'RS 3m'), rs('rs_6m_spy', 'RS 6m'), rs('rs_12m_spy', 'RS 12m'), POS_52W, ADV]
const RISK_COLUMNS = [VOL, MDD]

/** WHICH QUESTION THE TABLE IS ANSWERING RIGHT NOW.
 *
 *  The FM asked for two things that pull against each other in the same breath: "the table can be
 *  so much richer… we need some more important columns here", and "I don't want this platform to
 *  be more crowded than I'm asking you to." Thirty columns at once satisfies the first and breaks
 *  the second. Three named views satisfy both: the data is all here, and the reader says which
 *  question they are asking rather than reading past twenty answers to the ones they are not.
 *
 *  Identity never changes between views, so a row stays the same row when the view does. */
export const VIEWS = ['ranking', 'lenses', 'cost'] as const
export type BoardView = (typeof VIEWS)[number]

export const VIEW_LABEL: Record<BoardView, string> = {
  ranking: 'Ranking',
  lenses: 'Lenses',
  cost: 'Cost & size',
}

export const VIEW_NOTE: Record<BoardView, string> = {
  ranking: 'The score, what it is made of, and the price evidence behind it.',
  lenses: 'Every lens side by side — where two near-identical scores actually differ.',
  cost: 'What it is a bet on, what it costs to hold, how big it is and whether it is trending.',
}

export function isBoardView(v: string | null | undefined): v is BoardView {
  return v != null && (VIEWS as readonly string[]).includes(v)
}

/** The board's columns for this market and view, with the score block dropped entirely when
 *  nothing is scored yet — a wall of em dashes is not a state, it is a shrug. */
export function boardColumns(ctx: ColumnContext, scored: boolean, view: BoardView = 'ranking'): Column<InstrumentRow>[] {
  const etf = ctx.assetClass === 'etf'
  const identity = etf ? [symbol('etf'), NAME, PEER] : [symbol('stock'), NAME, SECTOR_COL, COHORT]

  // Nothing scored: the lens view has nothing to show, so it falls back rather than rendering a
  // grid of dashes the reader has to interpret.
  if (!scored) return [...identity, ...PRICE_COLUMNS, ...RISK_COLUMNS]

  if (view === 'lenses') {
    return [...identity, COMPOSITE, lenses(ctx), technical(ctx), ...(etf ? ETF_LENS_COLUMNS : STOCK_LENS_COLUMNS)]
  }
  if (view === 'cost') {
    // A company has no expense ratio and no fund assets, so on the stock board this view is what
    // it can honestly be: the sector, the trend and the liquidity.
    return etf
      ? [...identity, COMPOSITE, THEME_COL, EXPENSE, AUM, ADV, TREND, POS_52W]
      : [...identity, COMPOSITE, ADV, TREND, POS_52W, VOL, MDD]
  }
  return [...identity, ...SCORE_COLUMNS(ctx), ...PRICE_COLUMNS, ...RISK_COLUMNS]
}
