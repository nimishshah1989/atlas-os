// src/lib/scores.ts — the pure half of the ranked board: how a score, a decile, a peer group and
// a conviction tier become something on a screen. No React, no database, no arithmetic on money.
//
// THREE RULES THIS FILE EXISTS TO KEEP.
//
// 1. A missing lens is NOT a zero (rule #0). Every helper here maps null to an em dash or to a
//    sentence naming what has not been measured — never to 0, which would tell a reader the fund
//    is bad at something nobody looked at.
// 2. A composite must always say what it is made of. `lensesLabel` is printed beside every
//    composite on every surface, so a one-lens score can never be mistaken for a full one. The
//    denominator is the number of lenses `atlas_global.atlas_thresholds` carries a weight for —
//    read from the database, never written down here (rule #1).
// 3. Colour is the SECOND channel, never the only one. Every tinted cell also prints its value,
//    so the board reads in greyscale, to a colour-blind reader, and in a pasted screenshot.
//    Same discipline as the country grid's RS cells.
import { signedTint } from '@/lib/tone'

/** Leader = top decile within the peer group (docs/global/phase2.md P2-C, the cut India's
 *  v_stock_leader makes within cap cohort). It is a rank, not a score. */
export const LEADER_DECILE = 10

/** The decile ramp lives in globals.css as `--decile-1 … --decile-10`, theme-scoped. A value
 *  outside 1–10, or none at all, has no colour: the caller prints an em dash instead. */
export function decileColour(decile: number | string | null | undefined): string | null {
  const n = decile == null || decile === '' ? NaN : Math.round(Number(decile))
  if (!Number.isInteger(n) || n < 1 || n > 10) return null
  return `var(--decile-${n})`
}

export const isLeader = (decile: number | null | undefined) => decile === LEADER_DECILE

// ── relative strength tint ──────────────────────────────────────────────────

/** |RS| at which the tint saturates — beyond ±20 percent, more is not louder. Every surface that
 *  tints a relative strength (the board, the country grid, the sector heatmap, the pulse) goes
 *  through this one function, so no two of them can disagree about what ±20 looks like. */
const FULL_TINT = 0.2

/** The cell background for a relative-strength value, or undefined when there is nothing to tint.
 *  The ramp and its ceiling live in src/lib/tone.ts: a text cell never goes darker than the
 *  decile chip does, and a two-point lead is visible rather than a wash. */
export function rsTint(value: string | null | undefined): string | undefined {
  return signedTint(value, FULL_TINT)
}

// ── lenses ──────────────────────────────────────────────────────────────────

/** One lens of the blend: its name, and the weight `atlas_thresholds` carries for it. Weight 0 is
 *  a real answer — the ETF risk lens is an overlay today, displayed and not blended. */
export type LensWeight = { key: string; weight: number }

export const LENS_LABEL: Record<string, string> = {
  technical: 'Technical',
  risk: 'Risk',
  cost_liquidity: 'Cost & liquidity',
  flow: 'Flow',
  quality: 'Quality',
  fundamental: 'Fundamental',
  valuation: 'Valuation',
  catalyst: 'Catalyst',
  policy: 'Policy',
}

export const lensLabel = (key: string) => LENS_LABEL[key] ?? key.replace(/_/g, ' ')

/** "2 of 5 lenses" — printed beside EVERY composite. A null count is not zero lenses: it is a row
 *  the scorer has not reached, and it says so. With no weight table to count, the denominator is
 *  dropped rather than guessed. */
export function lensesLabel(active: number | null | undefined, total: number): string {
  if (active == null) return 'not yet scored'
  // "1 of 5 lenses", not "1 of 5 lens": the noun counts the DENOMINATOR, which is the whole point
  // of printing it. docs/global/phase2.md P2-C spells the sentence.
  return total > 0 ? `${active} of ${total} lenses` : `${active} lenses`
}

/** The same fact at table density: "2/5", with the sentence above as its tooltip. */
export function lensesShort(active: number | null | undefined, total: number): string {
  if (active == null) return '—'
  return total > 0 ? `${active}/${total}` : String(active)
}

// ── conviction tiers ────────────────────────────────────────────────────────

// atlas.global_market.scoring.blend.DEFAULT_ORDER, in words. BELOW_THRESHOLD is what a scored row
// gets when it clears no tier — a verdict, not a missing value.
export const TIER_LABEL: Record<string, string> = {
  HIGHEST: 'Highest',
  HIGH: 'High',
  MEDIUM: 'Medium',
  WATCH: 'Watch',
  BELOW_THRESHOLD: 'Below threshold',
}

export const tierLabel = (tier: string | null | undefined) =>
  tier == null || tier === '' ? '—' : (TIER_LABEL[tier] ?? tier.toLowerCase().replace(/_/g, ' '))

// ── peer groups ─────────────────────────────────────────────────────────────

/** The token `score_etfs.py` writes: `<asset class>:<strategy>` when the strategy bucket is big
 *  enough to cut percentiles in, otherwise the bare asset class it fell back to. */
export const UNCLASSIFIED = 'unclassified'

const WORD: Record<string, string> = {
  equity: 'Equity',
  fixed_income: 'Fixed income',
  commodity: 'Commodity',
  currency: 'Currency',
  multi_asset: 'Multi-asset',
  alternative: 'Alternative',
  broad_market: 'Broad market',
  size_style: 'Size & style',
  factor: 'Factor',
  dividend_income: 'Dividend income',
  sector: 'Sector',
  thematic: 'Thematic',
  country: 'Country',
  region: 'Region',
  single_stock: 'Single stock',
  crypto: 'Crypto',
  defined_outcome: 'Defined outcome',
  options_income: 'Options income',
  unclassified: 'Unclassified',
  mega: 'Mega cap',
  large: 'Large cap',
  mid: 'Mid cap',
  none: 'No group',
}

const word = (token: string) => WORD[token] ?? token.replace(/_/g, ' ')

/** `equity:sector` → "Equity · Sector"; `fixed_income` → "Fixed income"; the unclassified token,
 *  on either axis, reads as "Unclassified" and never disappears. */
export function peerGroupLabel(value: string | null | undefined): string {
  if (value == null || value === '') return word(UNCLASSIFIED)
  const [asset, strategy] = value.split(':')
  if (!strategy || asset === strategy) return word(asset)
  if (strategy === UNCLASSIFIED) return `${word(asset)} · Unclassified`
  return `${word(asset)} · ${word(strategy)}`
}

/** Where a fund is ranked. The score row's own `peer_group` is the authority — it names the
 *  population the decile was cut in. A fund with no score row (out of universe, or the scorer has
 *  not run) still has a job, so its classification stands in and the decile column stays empty. */
export function peerGroupOf(r: {
  peer_group: string | null
  strategy?: string | null
  class_asset_class?: string | null
}): string {
  if (r.peer_group) return r.peer_group
  if (r.strategy) return `${r.class_asset_class ?? UNCLASSIFIED}:${r.strategy}`
  return UNCLASSIFIED
}

/** "ranked 4 of 34 in Equity · Sector" — the sentence a decile chip is shorthand for. */
export function rankSentence(rank: number | null, peerN: number | null, group: string | null): string {
  const where = `in ${peerGroupLabel(group)}`
  if (rank == null || peerN == null || peerN === 0) return `not ranked ${where}`
  return `ranked ${rank} of ${peerN} ${where}`
}

// ── the universe ────────────────────────────────────────────────────────────

/** The default board is the universe snapshot's own cut: current S&P 500 members for stocks, and
 *  for ETFs everything above the seeded liquidity floor that is neither leveraged nor inverse.
 *  A row the snapshot has not marked is `out` — and the explorer offers the toggle only once some
 *  row IS marked, so an unmarked session still shows everything. */
export const universeSide = (r: { in_universe: boolean | null }): 'in' | 'out' =>
  r.in_universe === true ? 'in' : 'out'

// ── sorting ─────────────────────────────────────────────────────────────────

/** A NUMERIC string as a double, FOR ORDERING ONLY — nothing is computed from it, and a null stays
 *  null so `sortRows` puts unscored rows last whichever way the column is sorted. */
export const orderBy = (s: string | number | null | undefined): number | null =>
  s == null || s === '' ? null : Number(s)

// ── the derivation tree ─────────────────────────────────────────────────────

// Which sub-score columns each lens is the mean of. These are COLUMN NAMES out of
// scripts/global_market/ddl/05_scores.sql — the journal's own shape, not a methodology choice —
// in the order the scorer fills them. Same role as India's SUBS map in stock_lens.ts.
export const ETF_LENS_SUBS: Record<string, string[]> = {
  technical: ['tech_trend', 'tech_rs_spy', 'tech_rs_peer', 'tech_structure'],
  risk: ['risk_vol', 'risk_mdd', 'risk_downside', 'risk_beta'],
  cost_liquidity: ['cost_expense', 'cost_adv', 'cost_aum', 'cost_concentration'],
  flow: ['flow_so_21d', 'flow_so_63d'],
  quality: ['quality_composite', 'quality_leaders'],
}

export const STOCK_LENS_SUBS: Record<string, string[]> = {
  technical: ['tech_trend', 'tech_rs', 'tech_vol_contraction', 'tech_volume'],
  fundamental: ['fund_profitability', 'fund_margin', 'fund_growth', 'fund_balance_sheet', 'fund_op_leverage'],
  valuation: ['val_pe_vs_sector', 'val_absolute_pe', 'val_pb', 'val_ev_ebitda', 'val_52w_position'],
  catalyst: ['cat_earnings_strategy', 'cat_capital_action', 'cat_governance'],
  flow: ['flow_promoter', 'flow_institutional', 'flow_smart_money'],
  policy: ['policy_tailwind'],
}

export const SUB_LABEL: Record<string, string> = {
  tech_trend: 'Trend',
  tech_rs_spy: 'Relative strength vs SPY',
  tech_rs_peer: 'Relative strength vs peers',
  tech_structure: 'Moving-average structure',
  tech_rs: 'Relative strength',
  tech_vol_contraction: 'Volatility contraction',
  tech_volume: 'Volume',
  risk_vol: 'Volatility',
  risk_mdd: 'Max drawdown',
  risk_downside: 'Downside deviation',
  risk_beta: 'Beta band',
  cost_expense: 'Expense ratio',
  cost_adv: 'Traded value',
  cost_aum: 'Assets under management',
  cost_concentration: 'Concentration',
  flow_so_21d: 'Shares outstanding, 21 days',
  flow_so_63d: 'Shares outstanding, 63 days',
  quality_composite: 'Holdings-weighted composite',
  quality_leaders: 'Weight in Leaders',
  fund_profitability: 'Profitability',
  fund_margin: 'Margin',
  fund_growth: 'Growth',
  fund_balance_sheet: 'Balance sheet',
  fund_op_leverage: 'Operating leverage',
  val_pe_vs_sector: 'PE vs sector',
  val_absolute_pe: 'Absolute PE',
  val_pb: 'Price / book',
  val_ev_ebitda: 'EV / EBITDA',
  val_52w_position: '52-week position',
  cat_earnings_strategy: 'Earnings & strategy',
  cat_capital_action: 'Capital action',
  cat_governance: 'Governance',
  flow_promoter: 'Promoter',
  flow_institutional: 'Institutional',
  flow_smart_money: 'Smart money',
  policy_tailwind: 'Policy tailwind',
}

export const subLabel = (key: string) => SUB_LABEL[key] ?? key.replace(/_/g, ' ')

/** The sub-score columns of a lens, by market. An unknown lens has none — it is still shown, with
 *  its own score, so a lens the journal grows later cannot silently vanish from the tree. */
export const lensSubs = (assetClass: 'etf' | 'stock', lens: string): string[] =>
  (assetClass === 'etf' ? ETF_LENS_SUBS : STOCK_LENS_SUBS)[lens] ?? []
